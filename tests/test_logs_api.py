"""
Tests for the Activity log (backend/routes_logs.py) and how events are filed by area
(models.log_category). The database is replaced by a stand-in.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import models  # noqa: E402

WHEN = datetime.datetime(2026, 11, 8, 9, 30, tzinfo=datetime.timezone.utc)


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="system_administrator"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "root-admin"
        sess["role"] = role


def test_every_event_is_filed_under_one_area():
    assert models.log_category("login_success") == "sign_in"
    assert models.log_category("login_password_ok_awaiting_2fa_setup") == "sign_in"
    assert models.log_category("totp_enabled") == "sign_in"
    assert models.log_category("password_reset_completed") == "sign_in"
    assert models.log_category("user_invited") == "accounts"
    assert models.log_category("password_reset_sent") == "accounts"
    assert models.log_category("alert_acknowledged") == "alerts"
    assert models.log_category("reading_rejected") == "pipeline"


def test_the_log_is_for_administrators_only():
    client = _client()
    _login(client, role="emergency_responder")
    assert client.get("/api/logs").status_code == 403


def test_filters_reach_the_query():
    client = _client()
    _login(client)
    with patch("routes_logs.db.query_all", return_value=[]) as mocked:
        resp = client.get("/api/logs?category=sign_in&period=1d&q=jane&outcome=failed&before=40&limit=25")
    assert resp.status_code == 200
    sql, params = mocked.call_args.args
    assert "category = %s" in sql and "id < %s" in sql and "ILIKE" in sql
    assert params == ("sign_in", "1 day", "%jane%", "%jane%", "%jane%", ["login_failure", "password_change_failure"], 40, 25)


def test_all_time_and_unknown_values_are_ignored_safely():
    client = _client()
    _login(client)
    with patch("routes_logs.db.query_all", return_value=[]) as mocked:
        client.get("/api/logs?category=everything&period=all&outcome=maybe")
    assert mocked.call_args.args[1] == (50,)


def test_alert_entries_carry_the_alert_details():
    client = _client()
    _login(client)
    logs = [{"id": 3, "occurred_at": WHEN, "actor": "responder1", "action": "alert_acknowledged",
             "detail": "alert 7 (Mathare)", "category": "alerts"}]
    alert = {"id": 7, "severity": "high", "catchment": "Mathare",
             "flood_day": datetime.datetime(2024, 4, 29, tzinfo=datetime.timezone.utc),
             "anomaly_score": 0.912, "threshold_used": 0.555}
    with patch("routes_logs.db.query_all", side_effect=[logs, [alert]]):
        body = client.get("/api/logs?category=alerts").get_json()
    assert body[0]["alert"]["severity"] == "high" and body[0]["alert"]["flood_day"].startswith("2024-04-29")

