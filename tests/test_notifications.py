"""
Tests for alert and warning emails (backend/notify.py), the notify flag through detection,
and the internal /notify-warning endpoint. Mail and the database are replaced by stand-ins.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import config  # noqa: E402
import flood_detection  # noqa: E402
import mailer  # noqa: E402
import notify  # noqa: E402

HEADERS = {"X-Internal-Token": config.INTERNAL_API_TOKEN}
DAY = datetime.date(2024, 4, 29)


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_a_flood_alert_is_emailed_to_every_recipient_and_logged():
    with patch("notify.recipients", return_value=["a@x.org", "b@x.org"]), \
         patch("notify.mailer.send_email") as send, patch("notify.models.log_event") as log:
        sent = notify.flood_alert("Mathare", ["Mabatini", "Huruma"], DAY, "high", 0.91, 0.528)
    assert sent == 2 and send.call_count == 2
    subject = send.call_args.args[1]
    assert "Mathare" in subject and "high" in subject and "29 Apr 2024" in subject
    assert "Mabatini, Huruma" in send.call_args.args[2]
    assert log.call_args.args[1] == "alert_notified" and "emailed 2 of 2" in log.call_args.args[2]


def test_one_failing_address_does_not_stop_the_others():
    with patch("notify.recipients", return_value=["a@x.org", "b@x.org"]), \
         patch("notify.mailer.send_email", side_effect=[OSError("refused"), None]), \
         patch("notify.models.log_event") as log:
        sent = notify.rainfall_warning("Ngong", [], DAY, 62.0, 50.0)
    assert sent == 1 and "failed a@x.org" in log.call_args.args[2]


def test_nothing_is_sent_without_mail_settings_or_recipients():
    with patch("notify.recipients", return_value=["a@x.org"]), \
         patch("notify.mailer.send_email", side_effect=mailer.MailNotConfigured("no smtp")), \
         patch("notify.models.log_event") as log:
        assert notify.flood_alert("Ngong", [], DAY, "low", 0.6, 0.528) == 0
    assert log.call_args.args[1] == "alert_notify_skipped"
    with patch("notify.recipients", return_value=[]), patch("notify.models.log_event") as log:
        assert notify.rainfall_warning("Ngong", [], DAY, 70.0, 50.0) == 0
    assert "no responder" in log.call_args.args[2]


def _detect(notify_flag):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [[11], [22]]
    with patch("flood_detection.build_window", return_value=("window", None)), \
         patch("flood_detection.score_window", return_value=0.9), \
         patch("flood_detection.load_models", return_value=({"threshold": 0.528, "version": "v2"}, [])), \
         patch("flood_detection.db.get_connection", return_value=conn), \
         patch("flood_detection.db.query_one", return_value={"name": "Mathare", "wards": ["Mabatini"]}), \
         patch("notify.flood_alert", return_value=3) as alert:
        result = flood_detection.detect(2, DAY, 99, notify=notify_flag)
    return result, alert


def test_only_a_live_reading_emails_its_alert():
    result, alert = _detect(True)
    alert.assert_called_once_with("Mathare", ["Mabatini"], DAY, "high", 0.9, 0.528)
    assert result["notified"] == 3
    result, alert = _detect(False)
    alert.assert_not_called()
    assert result["notified"] is None


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
