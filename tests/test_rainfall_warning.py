"""Tests for the Open-Meteo rainfall warning (ingestion/forecast.py, consumer and producer
forecast handling, and GET /api/forecast)."""
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
INGESTION = str(ROOT / "ingestion")
NAMES = ("config", "db", "validation", "earth_engine", "forecast", "producer", "consumer")


def _load(module):
    """Import an ingestion module with ingestion's own config and db, not backend's modules of the same name."""
    saved = {n: sys.modules.pop(n) for n in NAMES if n in sys.modules}
    sys.path.insert(0, INGESTION)
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(INGESTION)
        for n in NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


producer = _load("producer")
forecast = producer.forecast
consumer = _load("consumer")

CATCHMENTS = [("Mathare", 36.87, -1.25), ("Ngong", 36.79, -1.31)]
REPLY = [  # Open-Meteo returns a list when several locations are asked for
    {"daily": {"time": ["2026-11-10", "2026-11-11"], "precipitation_sum": [3.2, 61.5]}},
    {"daily": {"time": ["2026-11-10", "2026-11-11"], "precipitation_sum": [0.0, 12.0]}},
]


def test_one_request_asks_for_every_catchment_point():
    url = forecast.build_url([(36.87, -1.25), (36.79, -1.31)])
    assert "latitude=-1.2500%2C-1.3100" in url and "longitude=36.8700%2C36.7900" in url
    assert "daily=precipitation_sum" in url and "forecast_days=3" in url


def test_the_reply_becomes_one_message_per_catchment():
    messages = forecast.to_messages(REPLY, CATCHMENTS, "2026-11-10T06:00:00+00:00")
    assert [m["catchment"] for m in messages] == ["Mathare", "Ngong"]
    assert messages[0]["days"][1] == {"date": "2026-11-11", "precipitation_mm": 61.5}
    assert messages[0]["source"] == "open-meteo"


def test_a_reply_missing_a_location_is_refused():
    with pytest.raises(ValueError):
        forecast.to_messages(REPLY[:1], CATCHMENTS, "now")


def _forecast_message(mm):
    return {"catchment": "Mathare", "source": "open-meteo", "issued_at": "2026-11-10T06:00:00+00:00",
            "days": [{"date": "2026-11-11", "precipitation_mm": mm}]}


def test_invalid_forecasts_are_rejected():
    ids = {"Mathare": 2}
    assert consumer.check_forecast(_forecast_message(12.0), ids) is None
    assert "invalid rainfall" in consumer.check_forecast(_forecast_message(-1.0), ids)
    assert "invalid rainfall" in consumer.check_forecast(_forecast_message(None), ids)
    assert "unknown" in consumer.check_forecast({**_forecast_message(1.0), "catchment": "Motoine"}, ids)


def _handle(mm, already_warning=False):
    counts = {"rejected": 0, "forecasts": 0, "warnings": 0}
    with patch.object(consumer.db, "query_one", return_value={"is_warning": already_warning}), \
         patch.object(consumer.db, "execute") as execute, patch.object(consumer, "reject") as reject, \
         patch.object(consumer, "post_internal", return_value={"notified": 1}) as notify:
        consumer.handle_forecast(_forecast_message(mm), {"Mathare": 2}, counts)
    _handle.notify = notify
    return counts, execute, reject


def test_a_forecast_at_or_above_50_mm_is_stored_as_a_warning_and_logged():
    counts, execute, _ = _handle(61.5)
    upsert = execute.call_args_list[0].args
    assert "INSERT INTO rainfall_forecasts" in upsert[0] and upsert[1][4] is True
    log = execute.call_args_list[1].args
    assert "rainfall_warning" in log[0] and "61.5 mm forecast for 2026-11-11" in log[1][0]
    assert counts == {"rejected": 0, "forecasts": 1, "warnings": 1}


def test_a_warning_is_logged_only_once_when_the_forecast_is_refreshed():
    counts, execute, _ = _handle(70.0, already_warning=True)
    assert len(execute.call_args_list) == 1 and counts["warnings"] == 0


def test_a_new_warning_asks_the_backend_to_email_it_and_a_refresh_does_not():
    _handle(61.5)
    _handle.notify.assert_called_once()
    url, payload = _handle.notify.call_args.args
    assert url.endswith("/notify-warning")
    assert payload == {"catchment_id": 2, "date": "2026-11-11", "precipitation_mm": 61.5, "threshold_mm": 50.0}
    _handle(70.0, already_warning=True)
    _handle.notify.assert_not_called()


def test_light_rain_is_stored_without_a_warning():
    counts, execute, _ = _handle(12.0)
    assert execute.call_args_list[0].args[1][4] is False and counts["warnings"] == 0


def _run_forecast(fetch):
    with patch.object(producer, "forecast_catchments", return_value=CATCHMENTS), \
         patch.object(forecast, "fetch", side_effect=fetch), \
         patch.object(producer, "publish", return_value=2) as publish, \
         patch.object(producer, "record_status") as status, \
         patch.object(producer.time, "sleep"):
        code = producer.run_forecast()
    return code, publish, status


def test_a_forecast_run_publishes_on_the_forecast_topic_and_records_success():
    code, publish, status = _run_forecast(lambda c, t: forecast.to_messages(REPLY, CATCHMENTS, t))
    assert code == 0
    assert publish.call_args.kwargs["topic"] == "hydro-forecasts"
    assert status.call_args.args[0] is True and "highest 61.5 mm" in status.call_args.args[1]
    assert status.call_args.kwargs["source"] == "open-meteo"


def test_an_unreachable_forecast_service_is_recorded_as_disconnected():
    def down(c, t):
        raise ConnectionError("Open-Meteo unreachable")
    code, publish, status = _run_forecast(down)
    assert code == 1
    publish.assert_not_called()
    assert status.call_args.args[0] is False and status.call_args.kwargs["source"] == "open-meteo"


def test_the_forecast_endpoint_needs_login_and_returns_the_outlook():
    sys.path.insert(0, str(ROOT / "backend"))
    import app as app_module
    client = app_module.create_app().test_client()
    assert client.get("/api/forecast").status_code == 401
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = 1, "officer", "government_official"
    rows = [{"catchment": "Mathare", "wards": ["Mathare", "Huruma"], "forecast_date": "2026-11-11",
             "precipitation_mm": 61.5, "threshold_mm": 50.0, "is_warning": True, "issued_at": "2026-11-10T06:00:00+00:00"}]
    with patch("routes_dashboard.db.query_all", return_value=rows) as query:
        resp = client.get("/api/forecast")
    assert resp.status_code == 200 and resp.get_json() == rows
    assert "rainfall_forecasts" in query.call_args.args[0]
