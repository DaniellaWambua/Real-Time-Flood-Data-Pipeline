"""
Tests for in-app notifications and Web Push (backend/notify.py, routes_notifications.py), who is told
what, and the internal /notify-warning endpoint. The database and push service are stand-ins.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import config  # noqa: E402
import flood_detection  # noqa: E402
import notify  # noqa: E402

HEADERS = {"X-Internal-Token": config.INTERNAL_API_TOKEN}
DAY = datetime.date(2026, 10, 5)
INCIDENT = {"id": 7, "catchment": "Mathare", "wards": ["Mabatini"], "start_day": DAY, "end_day": DAY,
            "severity": "high", "verification": "pending", "provisional": True}


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="emergency_responder", user_id=3):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "user"
        sess["role"] = role


def _send(fn, *args):
    with patch("notify._users", side_effect=lambda roles: [{"disaster_management_agency": 1,
                                                              "emergency_responder": 2,
                                                              "government_official": 3}[r] for r in roles]) as users, \
         patch("notify.db.execute") as execute, patch("notify._push", return_value=0) as push:
        told = fn(*args)
    return told, users, execute, push


def test_a_new_incident_goes_to_disaster_management_to_verify():
    told, users, execute, push = _send(notify.incident_to_verify, INCIDENT)
    assert told == 1 and users.call_args.args[0] == notify.DMA
    user_id, kind, title, body, link = execute.call_args.args[1]
    assert (user_id, kind, link) == (1, "verify", "/incidents?id=7")
    assert "Mathare (Mabatini)" in body and "05 Oct 2026" in body and "Provisional" in body
    assert push.call_args.args[1]["title"] == title


def test_a_verified_incident_goes_to_responders_and_officials():
    told, users, execute, _ = _send(notify.incident_verified, dict(INCIDENT, verification="verified"), "officer-1")
    assert told == 2 and users.call_args.args[0] == notify.FIELD
    assert "Verified by officer-1" in execute.call_args.args[1][3]


def test_a_settled_incident_reaches_the_field_only_if_it_was_verified():
    told, *_ = _send(notify.incident_settled, INCIDENT, "confirmed")
    assert told == 1
    told, _, execute, _ = _send(notify.incident_settled, dict(INCIDENT, verification="verified"), "not_confirmed")
    assert told == 3 and "not confirmed" in execute.call_args.args[1][2]


def test_a_rain_warning_goes_to_all_three_roles():
    told, *_ = _send(notify.rainfall_warning, "Ngong", [], DAY, 62.0, 50.0)
    assert told == 3


def test_push_is_skipped_without_keys():
    with patch.object(config, "VAPID_PRIVATE_KEY", ""), patch("notify.db.query_all") as q:
        assert notify._push([1], {"title": "x"}) == 0
    q.assert_not_called()


def _detect(notify_flag, settled_alert=None):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [[11], [22]] if settled_alert is None else [[11], [settled_alert], [5]]
    full = {"name": "lstm_raw", "version": "v2", "threshold": 0.528}
    with patch("flood_detection.build_window", return_value=("window", None)), \
         patch("flood_detection.score_window", return_value=0.9), \
         patch("flood_detection.load_models", return_value=(full, [])), \
         patch("flood_detection.db.get_connection", return_value=conn), \
         patch("flood_detection.has_model", return_value=settled_alert is not None), \
         patch("flood_detection.read_config", return_value={"name": "lstm_fast", "version": "v1"}), \
         patch("incidents.attach", return_value=(5, True)), \
         patch("incidents.get", return_value=INCIDENT), \
         patch("notify.incident_to_verify", return_value=1) as verify, \
         patch("notify.incident_settled", return_value=2) as settled:
        result = flood_detection.detect(2, DAY, 99, notify=notify_flag)
    return result, verify, settled


def test_only_live_readings_notify_and_a_new_incident_asks_for_verification():
    result, verify, _ = _detect(True)
    verify.assert_called_once_with(INCIDENT)
    assert result["notified"] == 1 and result["incident_id"] == 5
    result, verify, _ = _detect(False)
    verify.assert_not_called()
    assert result["notified"] is None


def test_a_settled_provisional_incident_is_reported():
    result, verify, settled = _detect(True, settled_alert=40)
    settled.assert_called_once_with(INCIDENT, "confirmed")
    verify.assert_not_called()
    assert result["settled"] == "confirmed" and result["incident_id"] == 5


def test_each_user_reads_only_their_own_notifications():
    client = _client()
    assert client.get("/api/notifications").status_code == 401
    _login(client, user_id=3)
    with patch("routes_notifications.db.query_all", return_value=[]) as q:
        client.get("/api/notifications?unread=true")
    assert q.call_args.args[1][0] == 3 and "read_at IS NULL" in q.call_args.args[0]
    with patch("routes_notifications.db.execute") as execute:
        client.post("/api/notifications/9/read", json={})
    assert execute.call_args.args[1] == (9, 3)


def test_a_push_subscription_needs_an_https_endpoint_and_keys():
    client = _client()
    _login(client)
    assert client.post("/api/push/subscribe", json={"endpoint": "http://x"}).status_code == 400
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "p", "auth": "a"}}
    with patch("routes_notifications.db.execute") as execute, \
         patch("routes_notifications.db.query_one", return_value={"n": 0}):
        assert client.post("/api/push/subscribe", json=sub).status_code == 201
    assert execute.call_args.args[1] == (3, "https://fcm.googleapis.com/fcm/send/abc", "p", "a")


def test_notify_warning_needs_the_token_and_complete_details():
    client = _client()
    body = {"catchment_id": 2, "date": "2026-11-11", "precipitation_mm": 61.5, "threshold_mm": 50.0}
    assert client.post("/internal/notify-warning", json=body).status_code == 403
    assert client.post("/internal/notify-warning", json={"catchment_id": 2}, headers=HEADERS).status_code == 400
    with patch("routes_detection.db.query_one", return_value={"name": "Mathare", "wards": ["Mabatini"]}), \
         patch("routes_detection.notify.rainfall_warning", return_value=2) as warn:
        resp = client.post("/internal/notify-warning", json=body, headers=HEADERS)
    assert resp.status_code == 200 and resp.get_json() == {"notified": 2}
    warn.assert_called_once_with("Mathare", ["Mabatini"], datetime.date(2026, 11, 11), 61.5, 50.0)
