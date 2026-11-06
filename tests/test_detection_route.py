"""
Tests for the internal detection endpoint (backend/routes_detection.py).
The model is replaced by a stand-in here; tests/test_flood_detection.py covers it.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import config  # noqa: E402

HEADERS = {"X-Internal-Token": config.INTERNAL_API_TOKEN}
BODY = {"catchment_id": 2, "date": "2024-04-29"}


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_detect_refuses_a_missing_or_wrong_token():
    client = _client()
    assert client.post("/internal/detect", json=BODY).status_code == 403
    assert client.post("/internal/detect", json=BODY, headers={"X-Internal-Token": "wrong"}).status_code == 403


def test_detect_refuses_a_bad_date():
    resp = _client().post("/internal/detect", json={"catchment_id": 2, "date": "29/04/2024"}, headers=HEADERS)
    assert resp.status_code == 400


def test_detect_passes_the_request_to_the_module():
    result = {"scored": True, "id": 5, "score": 0.75, "threshold": 0.555, "flagged": True, "model": "lstm_raw v1"}
    with patch("routes_detection.flood_detection.detect", return_value=result) as mock_detect:
        resp = _client().post("/internal/detect", json={**BODY, "hydro_data_record_id": 99}, headers=HEADERS)
    assert resp.status_code == 200 and resp.get_json() == result
    mock_detect.assert_called_once_with(2, datetime.date(2024, 4, 29), 99)


def test_detect_reports_a_day_it_could_not_score():
    result = {"scored": False, "reason": "need 14 consecutive days ending 2024-04-29, found 13 usable rows"}
    with patch("routes_detection.flood_detection.detect", return_value=result):
        resp = _client().post("/internal/detect", json=BODY, headers=HEADERS)
    assert resp.status_code == 422 and "consecutive" in resp.get_json()["reason"]