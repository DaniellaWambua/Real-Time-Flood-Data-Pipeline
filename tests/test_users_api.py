"""
Tests for invite-based user management (backend/routes_users.py), the set-password
links (routes_auth.py /account/link/<code>) and the email builder (backend/mailer.py).
The database and the SMTP server are replaced by stand-ins.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import mailer  # noqa: E402
import models  # noqa: E402

NOW = datetime.datetime(2026, 11, 8, 9, 0, tzinfo=datetime.timezone.utc)
ROW = {"id": 5, "username": "jane.doe", "full_name": "Jane Doe", "email": "jane@example.org",
       "organisation": "Kenya Red Cross", "role": "emergency_responder", "is_active": True,
       "totp_enabled": False, "created_at": NOW, "last_sign_in": None, "has_password": False,
       "invite_expires_at": NOW + datetime.timedelta(hours=72), "invite_expired": False}
BODY = {"email": "Jane@Example.org", "full_name": "Jane Doe", "organisation": "Kenya Red Cross",
        "role": "emergency_responder"}


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="system_administrator", user_id=1, username="root-admin"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role


def test_user_management_is_for_administrators_only():
    client = _client()
    assert client.get("/api/users").status_code == 401
    _login(client, role="emergency_responder")
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users/invite", json=BODY).status_code == 403


def test_user_list_has_a_status_and_no_secrets():
    client = _client()
    _login(client)
    with patch("routes_users.models.list_users", return_value=[ROW]):
        body = client.get("/api/users").get_json()
    assert body[0]["status"] == "invited"
    assert "password_hash" not in body[0] and "totp_secret" not in body[0]


def test_status_covers_every_state():
    assert models.user_status({**ROW, "has_password": True}) == "active"
    assert models.user_status({**ROW, "is_active": False}) == "deactivated"
    assert models.user_status(ROW) == "invited"
    assert models.user_status({**ROW, "invite_expired": True}) == "invite_expired"


def test_invite_checks_its_fields():
    client = _client()
    _login(client)
    assert client.post("/api/users/invite", json={**BODY, "email": "not-an-email"}).status_code == 400
    assert client.post("/api/users/invite", json={**BODY, "full_name": " "}).status_code == 400
    assert client.post("/api/users/invite", json={**BODY, "role": "boss"}).status_code == 400
    with patch("routes_users.models.get_user_by_email", return_value={"id": 2}):
        assert client.post("/api/users/invite", json=BODY).status_code == 409


def test_invite_emails_a_link_and_logs_it():
    client = _client()
    _login(client)

    def fake_create(*args):
        args[-1]("CODE123")  # the route's send() callback
        return 5

    with (
        patch("routes_users.models.get_user_by_email", return_value=None),
        patch("routes_users.models.username_from_email", return_value="jane.doe"),
        patch("routes_users.models.create_invited_user", side_effect=fake_create) as mock_create,
        patch("routes_users.mailer.send_email") as mock_send,
        patch("routes_users._find", return_value=ROW),
        patch("routes_users.models.log_event") as mock_log,
    ):
        resp = client.post("/api/users/invite", json=BODY)
    assert resp.status_code == 201 and resp.get_json()["status"] == "invited"
    assert mock_create.call_args.args[:5] == ("jane.doe", "jane@example.org", "Jane Doe", "Kenya Red Cross",
                                              "emergency_responder")
    to, subject, text, html = mock_send.call_args.args
    assert to == "jane@example.org" and "/account/CODE123" in text and "jane.doe" in text
    mock_log.assert_called_once()
    assert mock_log.call_args.args[1] == "user_invited"


def test_invite_saves_nothing_when_email_is_not_configured():
    client = _client()
    _login(client)

    def fake_create(*args):
        args[-1]("CODE123")
        return 5

    with (
        patch("routes_users.models.get_user_by_email", return_value=None),
        patch("routes_users.models.username_from_email", return_value="jane.doe"),
        patch("routes_users.models.create_invited_user", side_effect=fake_create),
        patch("routes_users.config.SMTP_USERNAME", ""),
        patch("routes_users.models.log_event") as mock_log,
    ):
        resp = client.post("/api/users/invite", json=BODY)
    assert resp.status_code == 503 and "not configured" in resp.get_json()["error"]
    mock_log.assert_not_called()


def test_resend_and_reset_only_apply_to_the_right_accounts():
    client = _client()
    _login(client)
    with patch("routes_users._find", return_value={**ROW, "has_password": True}):
        assert client.post("/api/users/5/resend-invite", json={}).status_code == 409
    with patch("routes_users._find", return_value=ROW):
        assert client.post("/api/users/5/send-reset", json={}).status_code == 409


def test_admin_cannot_deactivate_themselves():
    client = _client()
    _login(client, user_id=5)
    with patch("routes_users.models.get_user_by_id", return_value={**ROW, "password_hash": "x"}):
        assert client.patch("/api/users/5", json={"is_active": False}).status_code == 400


def test_admin_cannot_change_their_own_role():
    client = _client()
    _login(client, user_id=5)
    with patch("routes_users.models.get_user_by_id", return_value=ROW):
        assert client.patch("/api/users/5", json={"role": "government_official"}).status_code == 400


def test_role_change_is_logged():
    client = _client()
    _login(client)
    with (
        patch("routes_users.models.get_user_by_id", return_value=ROW),
        patch("routes_users.models.verify_password", return_value=True),
        patch("routes_users._notify"),
        patch("routes_users.models.update_user_role") as mock_role,
        patch("routes_users.models.log_event") as mock_log,
        patch("routes_users._find", return_value={**ROW, "role": "government_official"}),
    ):
        resp = client.patch("/api/users/5", json={"role": "government_official", "password": "admin-pass"})
    assert resp.status_code == 200
    mock_role.assert_called_once_with(5, "government_official")
    mock_log.assert_called_once_with("root-admin", "user_role_changed", "jane.doe -> government_official")


LINK = {"link_id": 9, "purpose": "invite", "expires_at": NOW, "user_id": 5, "username": "jane.doe",
        "full_name": "Jane Doe", "email": "jane@example.org", "role": "emergency_responder", "is_active": True}


def test_an_unknown_or_expired_link_is_refused():
    with patch("routes_auth.models.find_link", return_value=None):
        assert _client().get("/account/link/nope").status_code == 404


def test_a_link_needs_a_long_enough_password():
    with patch("routes_auth.models.find_link", return_value=LINK):
        assert _client().post("/account/link/CODE", json={"password": "short"}).status_code == 400


def test_using_a_link_sets_the_password_then_asks_for_2fa_setup():
    client = _client()
    with (
        patch("routes_auth.models.find_link", return_value=LINK),
        patch("routes_auth.models.set_password_with_link", return_value=True) as mock_set,
        patch("routes_auth.models.get_user_by_id", return_value={**ROW, "password_hash": "x"}),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/account/link/CODE", json={"password": "kettle sings at dawn"})
    assert resp.status_code == 200 and resp.get_json() == {"requires_totp_setup": True}
    mock_set.assert_called_once_with(9, 5, "kettle sings at dawn")
    assert [c.args[1] for c in mock_log.call_args_list] == ["user_activated", "login_password_ok_awaiting_2fa_setup"]
    with client.session_transaction() as sess:
        assert "user_id" not in sess and sess["setup_user_id"] == 5


def test_a_used_link_cannot_be_used_again():
    with (
        patch("routes_auth.models.find_link", return_value=LINK),
        patch("routes_auth.models.set_password_with_link", return_value=False),
    ):
        assert _client().post("/account/link/CODE", json={"password": "kettle sings at dawn"}).status_code == 409


def test_a_reset_does_not_skip_two_factor_sign_in():
    client = _client()
    with (
        patch("routes_auth.models.find_link", return_value={**LINK, "purpose": "reset"}),
        patch("routes_auth.models.set_password_with_link", return_value=True),
        patch("routes_auth.models.get_user_by_id", return_value={**ROW, "totp_enabled": True}),
        patch("routes_auth.models.log_event"),
    ):
        resp = client.post("/account/link/CODE", json={"password": "kettle sings at dawn"})
    assert resp.get_json() == {"requires_totp": True}
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_admin_can_reset_someone_elses_2fa_but_not_their_own():
    client = _client()
    _login(client, user_id=1)
    with (
        patch("routes_users.models.get_user_by_id", return_value=ROW),
        patch("routes_users.models.verify_password", return_value=True),
        patch("routes_users._notify"),
        patch("routes_users.models.disable_totp") as mock_disable,
        patch("routes_users.models.log_event") as mock_log,
        patch("routes_users._find", return_value=ROW),
    ):
        assert client.post("/api/users/5/reset-2fa", json={"password": "admin-pass"}).status_code == 200
    mock_disable.assert_called_once_with(5)
    mock_log.assert_called_once_with("root-admin", "user_2fa_reset", "jane.doe")
    assert client.post("/api/users/1/reset-2fa", json={}).status_code == 400


def test_email_can_be_changed_but_not_to_one_already_used():
    client = _client()
    _login(client)
    with (
        patch("routes_users.models.get_user_by_id", return_value=ROW),
        patch("routes_users.models.get_user_by_email", return_value={"id": 8}),
    ):
        assert client.patch("/api/users/5", json={"email": "taken@example.org"}).status_code == 409
    with (
        patch("routes_users.models.get_user_by_id", return_value=ROW),
        patch("routes_users.models.get_user_by_email", return_value=None),
        patch("routes_users.models.verify_password", return_value=True),
        patch("routes_users._notify"),
        patch("routes_users.models.set_user_email") as mock_set,
        patch("routes_users.models.log_event"),
        patch("routes_users._find", return_value=ROW),
    ):
        assert client.patch("/api/users/5", json={"email": "New@Example.org", "password": "x"}).status_code == 200
    mock_set.assert_called_once_with(5, "new@example.org")


def test_invite_email_carries_the_link_and_username():
    subject, text, html = mailer.invite_email("Jane Doe", "jane.doe", "Emergency Responder", "root-admin",
                                              "http://localhost:5173/account/ABC", 72)
    assert "invited" in subject
    for part in (text, html):
        assert "http://localhost:5173/account/ABC" in part and "jane.doe" in part and "72 hours" in part


def test_sending_without_an_smtp_account_fails_clearly():
    with patch("mailer.config.SMTP_USERNAME", ""):
        try:
            mailer.send_email("a@b.co", "s", "t", "<p>t</p>")
        except mailer.MailNotConfigured:
            return
    raise AssertionError("expected MailNotConfigured")
