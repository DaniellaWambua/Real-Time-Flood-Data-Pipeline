"""
Tests for the LSTM screen's own endpoints (backend/routes_anomalies.py): the model
card, where each catchment stands, the queryable scores list, the month calendar and
a single day. The database and the saved model are replaced by stand-ins, so these
check routing, auth, the filters that get built and the JSON shape, not real SQL.
"""
import datetime
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402

MODEL = "lstm_raw v1"


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="disaster_management_agency"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test-user"
        sess["role"] = role


def test_scores_requires_login():
    assert _client().get("/api/anomalies/scores").status_code == 401


def test_model_card_reads_config_and_evaluation():
    client = _client()
    _login(client)
    live = {
        "days_scored": 2193,
        "flagged": 118,
        "first_day": datetime.date(2024, 1, 1),
        "last_day": datetime.date(2025, 12, 31),
    }
    with patch("routes_anomalies.db.query_one", return_value=dict(live)):
        resp = client.get("/api/anomalies/model")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == MODEL
    assert body["threshold"] == 0.555
    assert len(body["features"]) == 15
    assert body["live"]["last_day"] == "2025-12-31"
    # the evaluation travels with the weights, so the page always shows this version's own figures
    assert body["evaluation"]["precision"] > 0
    assert body["evaluation"]["model"] == MODEL


def test_scores_filters_by_catchment_date_range_and_flagged():
    client = _client()
    _login(client)
    seen = {}

    def fake_all(sql, params):
        seen["sql"], seen["params"] = sql, params
        return []

    with patch("routes_anomalies.db.query_one", return_value={"count": 0}), patch(
        "routes_anomalies.db.query_all", side_effect=fake_all
    ):
        resp = client.get(
            "/api/anomalies/scores?catchment=Ngong&from=2024-05-01&to=2024-05-31&flagged=true&limit=10&offset=5"
        )
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 0
    assert "AND ca.name = %s" in seen["sql"] and "AND ar.is_anomalous" in seen["sql"]
    assert seen["params"] == (MODEL, "Ngong", datetime.date(2024, 5, 1), datetime.date(2024, 5, 31), 10, 5)


def test_scores_ignores_an_unparseable_date():
    client = _client()
    _login(client)
    seen = {}

    with patch("routes_anomalies.db.query_one", return_value={"count": 0}), patch(
        "routes_anomalies.db.query_all", side_effect=lambda sql, params: seen.update(params=params) or []
    ):
        resp = client.get("/api/anomalies/scores?from=not-a-date")
    assert resp.status_code == 200
    assert seen["params"] == (MODEL, 50, 0)


def test_calendar_defaults_to_the_last_month_scored():
    client = _client()
    _login(client)
    bounds = {"first_day": datetime.date(2024, 1, 1), "last_day": datetime.date(2025, 12, 31)}
    with patch(
        "routes_anomalies.db.query_one",
        side_effect=[{"day": datetime.date(2025, 12, 31)}, dict(bounds)],
    ), patch("routes_anomalies.db.query_all", return_value=[]):
        resp = client.get("/api/anomalies/calendar?catchment=Ngong")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["month"] == "2025-12"
    assert body["scored_range"] == {"first_day": "2024-01-01", "last_day": "2025-12-31"}


def test_day_returns_the_score_with_its_inputs():
    client = _client()
    _login(client)
    row = {
        "id": 7,
        "day": datetime.date(2024, 5, 1),
        "catchment": "Nairobi River",
        "catchment_id": 1,
        "anomaly_score": 0.893,
        "threshold_used": 0.555,
        "is_anomalous": True,
        "hydro_data_record_id": 42,
        "alert_id": 3,
        "alert_severity": "high",
        "alert_status": "active",
    }
    reading = {"rainfall_mm": 64.2, "soil_1": 0.41}
    with patch("routes_anomalies.db.query_one", side_effect=[dict(row), dict(reading)]):
        resp = client.get("/api/anomalies/day?catchment=Nairobi%20River&date=2024-05-01")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["day"] == "2024-05-01" and body["alert_severity"] == "high"
    labels = {i["label"]: i["value"] for i in body["inputs"]}
    assert labels["Rain (CHIRPS)"] == 64.2
    assert labels["Soil 0 to 7 cm"] == 0.41
    # a column the reading does not carry still appears, as a blank
    assert labels["Pressure"] is None


def test_day_needs_both_arguments_and_404s_when_unscored():
    client = _client()
    _login(client)
    assert client.get("/api/anomalies/day?catchment=Ngong").status_code == 400
    with patch("routes_anomalies.db.query_one", return_value=None):
        resp = client.get("/api/anomalies/day?catchment=Ngong&date=2030-01-01")
    assert resp.status_code == 404


def test_saved_evaluation_matches_the_saved_threshold():
    """The page quotes evaluation.json as this version's own result, so the two
    files have to agree on which threshold was measured."""
    model_dir = Path(__file__).resolve().parent.parent / "models" / "flood_lstm"
    config = json.loads((model_dir / "config.json").read_text())
    evaluation = json.loads((model_dir / "evaluation.json").read_text())
    assert evaluation["threshold"] == config["threshold"]
    assert evaluation["model"].endswith(config["version"])
    counts = evaluation["true_positives"] + evaluation["false_negatives"]
    assert counts == evaluation["flood_days"]


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"\n{len(tests)} passed")
