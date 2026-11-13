"""
NFR-03: list endpoints never return more than 500 records per request, and the
scores list is paged. A request for 1,000 records is sent to each list; the
database is replaced by a stand-in that records the LIMIT it was asked for.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test-user"
        sess["role"] = "disaster_management_agency"
    return client


def _limit_asked(module, url, query_one=None):
    """Call url with limit=1000 and return the parameters passed to query_all."""
    calls = []

    def fake_query_all(sql, params=None):
        calls.append(params)
        return []

    with patch(f"{module}.db.query_all", side_effect=fake_query_all), \
         patch(f"{module}.db.query_one", return_value=query_one or {"count": 0}), \
         patch("flood_detection.shown_model_names", return_value=["lstm_raw v2"]):
        resp = _client().get(url)
    assert resp.status_code == 200
    return calls[-1], resp.get_json()


def test_recent_readings_are_capped_at_500():
    params, _ = _limit_asked("routes_dashboard", "/api/readings/recent?catchment=Mathare&limit=1000")
    assert params[-1] == 500


def test_recent_scores_are_capped_at_500():
    params, _ = _limit_asked("routes_dashboard", "/api/anomalies/recent?limit=1000")
    assert params[-1] == 500


def test_alert_incidents_are_capped_at_500():
    params, _ = _limit_asked("routes_incidents", "/api/incidents?limit=1000")
    assert params["limit"] == 500


def test_the_scores_list_is_capped_and_paged():
    params, body = _limit_asked("routes_anomalies", "/api/anomalies/scores?limit=1000&offset=500",
                                query_one={"count": 2193})
    assert params[-2:] == (500, 500)
    assert body["limit"] == 500 and body["offset"] == 500 and body["total"] == 2193
