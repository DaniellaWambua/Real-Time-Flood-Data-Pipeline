"""
Checks for the access-control changes from the security audit (findings 5 and 6): the model's
day-by-day scores are only for Disaster Management and administrators, and the administrator
actions that decide who can sign in as whom need the administrator's own password and tell the
person affected. The database and the SMTP server are replaced by stand-ins.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import mailer  # noqa: E402
import security  # noqa: E402

TARGET = {"id": 5, "username": "jane.doe", "full_name": "Jane Doe", "email": "jane@example.org",
          "organisation": None, "role": "emergency_responder", "is_active": True, "password_hash": "x"}


def _client(role="system_administrator", user_id=1):
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    security.reset()
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=user_id, username="root-admin", role=role)
    return client


# Finding 5: the scores screen's data

SCORE_ROUTES = ["/api/anomalies/model", "/api/anomalies/scores", "/api/anomalies/calendar",
                "/api/anomalies/day?catchment=Mathare&date=2024-04-29"]


@pytest.mark.parametrize("role", ["emergency_responder", "government_official"])
@pytest.mark.parametrize("path", SCORE_ROUTES)
def test_field_roles_cannot_read_the_model_scores(role, path):
    assert _client(role=role).get(path).status_code == 403


def test_the_overview_data_stays_open_to_every_role():
    """The Overview page, open to every role, uses these; they carry no incident details."""
    client = _client(role="emergency_responder")
    with patch("routes_dashboard.db.query_all", return_value=[]), \
         patch("routes_dashboard.flood_detection.current_model_name", return_value="m"), \
         patch("routes_dashboard.flood_detection.visible_results_params", return_value=[]):
        for path in ("/api/anomalies/recent", "/api/readings/recent", "/api/sources"):
            assert client.get(path).status_code == 200, path


# Finding 6: administrator actions need the administrator's password

def _admin_patches(verify=True):
    return (patch("routes_users.models.get_user_by_id", return_value=TARGET),
            patch("routes_users.models.verify_password", return_value=verify),
            patch("routes_users.models.log_event"),
            patch("routes_users._find", return_value={**TARGET, "has_password": True, "created_at": None,
                                                      "last_sign_in": None, "invite_expires_at": None,
                                                      "totp_enabled": False}))


def test_resetting_2fa_without_the_password_is_refused():
    client = _client()
    with _admin_patches()[0], patch("routes_users.models.disable_totp") as mock_disable:
        resp = client.post("/api/users/5/reset-2fa", json={})
    assert resp.status_code == 401 and resp.get_json()["needs_password"] is True
    mock_disable.assert_not_called()


def test_resetting_2fa_with_a_wrong_password_is_refused_and_logged():
    client = _client()
    p1, p2, p3, p4 = _admin_patches(verify=False)
    with p1, p2, p3 as mock_log, p4, patch("routes_users.models.disable_totp") as mock_disable:
        resp = client.post("/api/users/5/reset-2fa", json={"password": "wrong"})
    assert resp.status_code == 403
    mock_disable.assert_not_called()
    assert mock_log.call_args.args[1] == "admin_reauth_failure"


def test_wrong_passwords_are_limited():
    client = _client()
    p1, p2, p3, p4 = _admin_patches(verify=False)
    with p1, p2, p3, p4, patch("routes_users.models.disable_totp"):
        codes = [client.post("/api/users/5/reset-2fa", json={"password": "wrong"}).status_code for _ in range(6)]
    assert codes == [403] * 5 + [429]


def test_resetting_2fa_with_the_password_works_and_tells_the_person():
    client = _client()
    p1, p2, p3, p4 = _admin_patches()
    with p1, p2, p3, p4, patch("routes_users.models.disable_totp") as mock_disable, \
         patch("routes_users.mailer.send_email") as mock_send:
        resp = client.post("/api/users/5/reset-2fa", json={"password": "admin-pass"})
    assert resp.status_code == 200
    mock_disable.assert_called_once_with(5)
    to, subject, text, _ = mock_send.call_args.args
    assert to == "jane@example.org" and "two-factor" in text and "root-admin" in text


def test_an_email_change_needs_the_password_and_tells_both_addresses():
    client = _client()
    with _admin_patches()[0], patch("routes_users.models.get_user_by_email", return_value=None), \
         patch("routes_users.models.set_user_email") as mock_set:
        assert client.patch("/api/users/5", json={"email": "new@example.org"}).status_code == 401
    mock_set.assert_not_called()

    p1, p2, p3, p4 = _admin_patches()
    with p1, p2, p3, p4, patch("routes_users.models.get_user_by_email", return_value=None), \
         patch("routes_users.models.set_user_email") as mock_set, \
         patch("routes_users.mailer.send_email") as mock_send:
        resp = client.patch("/api/users/5", json={"email": "new@example.org", "password": "admin-pass"})
    assert resp.status_code == 200
    mock_set.assert_called_once_with(5, "new@example.org")
    assert sorted(c.args[0] for c in mock_send.call_args_list) == ["jane@example.org", "new@example.org"]


def test_a_role_change_needs_the_password():
    client = _client()
    with _admin_patches()[0], patch("routes_users.models.update_user_role") as mock_role:
        assert client.patch("/api/users/5", json={"role": "system_administrator"}).status_code == 401
    mock_role.assert_not_called()


def test_name_changes_and_deactivation_need_no_password():
    client = _client()
    p1, p2, p3, p4 = _admin_patches()
    with p1, p2, p3, p4, patch("routes_users.models.update_user_details") as mock_details, \
         patch("routes_users.models.set_user_active") as mock_active:
        assert client.patch("/api/users/5", json={"full_name": "Jane W. Doe", "role": "emergency_responder"}
                            ).status_code == 200
        assert client.patch("/api/users/5", json={"is_active": False}).status_code == 200
    mock_details.assert_called_once()
    mock_active.assert_called_once_with(5, False)


def test_a_failed_notice_email_does_not_undo_the_change():
    client = _client()
    p1, p2, p3, p4 = _admin_patches()
    with p1, p2, p3 as mock_log, p4, patch("routes_users.models.disable_totp") as mock_disable, \
         patch("routes_users.mailer.send_email", side_effect=mailer.MailNotConfigured("no smtp")):
        assert client.post("/api/users/5/reset-2fa", json={"password": "admin-pass"}).status_code == 200
    mock_disable.assert_called_once_with(5)
    assert "security_notice_failed" in [c.args[1] for c in mock_log.call_args_list]


def test_the_notice_email_escapes_what_it_shows():
    _, text, html = mailer.security_notice_email("<b>Jane</b>", "jane.doe", "changed your role", "root-admin")
    assert "<b>Jane</b>" not in html and "&lt;b&gt;Jane&lt;/b&gt;" in html
    assert "root-admin" in text and "contact your system administrator" in text
