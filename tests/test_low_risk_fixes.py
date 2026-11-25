"""
Checks for the lower-risk fixes from the security audit (findings 10 to 14 and 16): sign-in takes
as long whether or not the account exists, push subscriptions only reach real push services, the
activity log records the client address and cannot be flooded, and internal error text stays out
of responses. The database is replaced by stand-ins.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import models  # noqa: E402
import routes_notifications  # noqa: E402


def _client(user_id=3, role="emergency_responder"):
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=user_id, username="user-3", role=role)
    return client


# 10. No difference in work between a known and an unknown account

def test_an_unknown_account_still_runs_the_password_hash():
    with patch("models.check_password_hash", return_value=True) as mock_check:
        assert models.verify_password(None, "guess") is False
        assert models.verify_password({"password_hash": None}, "guess") is False
    assert mock_check.call_count == 2


def test_login_checks_a_password_even_when_there_is_no_account():
    client = app_module.create_app().test_client()
    with patch("routes_auth.models.get_user_by_login", return_value=None), \
         patch("models.check_password_hash", return_value=False) as mock_check, \
         patch("routes_auth.models.log_event"):
        assert client.post("/login", json={"username": "nobody", "password": "x"}).status_code == 401
    mock_check.assert_called_once()


# 11. Push subscriptions

@pytest.mark.parametrize("endpoint", [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://web.push.apple.com/QGx",
    "https://wns2-par02p.notify.windows.com/w/?token=abc",
])
def test_the_browser_push_services_are_accepted(endpoint):
    assert routes_notifications._push_service(endpoint)


@pytest.mark.parametrize("endpoint", [
    "https://evil.example/collect",
    "https://fcm.googleapis.com.evil.example/x",
    "http://fcm.googleapis.com/fcm/send/abc",
    "https://10.0.0.4/internal",
    "https://localhost:5001/internal/detect",
])
def test_other_addresses_are_refused(endpoint):
    client = _client()
    with patch("routes_notifications.db.execute") as execute:
        resp = client.post("/api/push/subscribe", json={"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}})
    assert resp.status_code == 400
    execute.assert_not_called()


def test_a_subscription_only_moves_users_with_its_own_keys():
    client = _client()
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "p", "auth": "a"}}
    with patch("routes_notifications.db.execute") as execute, \
         patch("routes_notifications.db.query_one", return_value={"n": 0}):
        assert client.post("/api/push/subscribe", json=sub).status_code == 201
    sql = execute.call_args.args[0]
    assert "WHERE push_subscriptions.p256dh = EXCLUDED.p256dh AND push_subscriptions.auth = EXCLUDED.auth" in sql


def test_devices_per_user_are_capped():
    client = _client()
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/new", "keys": {"p256dh": "p", "auth": "a"}}
    with patch("routes_notifications.db.execute") as execute, \
         patch("routes_notifications.db.query_one", return_value={"n": routes_notifications.MAX_SUBSCRIPTIONS}):
        assert client.post("/api/push/subscribe", json=sub).status_code == 409
    execute.assert_not_called()


# 12. The activity log

def test_events_from_a_request_record_the_client_address():
    flask_app = app_module.create_app()
    with flask_app.test_request_context("/login", environ_base={"REMOTE_ADDR": "197.248.1.20"}), \
         patch("models.db.execute") as mock_execute:
        models.log_event("officer", "login_failure", "invalid username or password")
    assert mock_execute.call_args.args[1][-1] == "197.248.1.20"


def test_the_address_comes_from_caddy_when_behind_it():
    flask_app = app_module.create_app()
    from werkzeug.middleware.proxy_fix import ProxyFix
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1)
    client = flask_app.test_client()
    with patch("routes_auth.models.get_user_by_login", return_value=None), \
         patch("models.db.execute") as mock_execute:
        client.post("/login", json={"username": "x", "password": "y"},
                    headers={"X-Forwarded-For": "41.90.5.5"}, environ_base={"REMOTE_ADDR": "172.18.0.5"})
    assert mock_execute.call_args.args[1][-1] == "41.90.5.5"


def test_a_huge_typed_username_cannot_flood_the_log():
    with patch("models.db.execute") as mock_execute:
        models.log_event("x" * 100_000, "login_failure", "y" * 100_000)
    actor, _, detail, _, _ = mock_execute.call_args.args[1]
    assert len(actor) == 120 and len(detail) == 1000


def test_request_bodies_are_capped():
    client = _client()
    resp = client.post("/login", data="x" * (2 * 1024 * 1024), content_type="application/json")
    assert resp.status_code == 413


# 14. Internal error text

def test_a_bad_google_credential_does_not_echo_the_library_error():
    client = app_module.create_app().test_client()
    with patch("routes_auth.config.GOOGLE_CLIENT_ID", "id"), \
         patch("routes_auth.google_id_token.verify_oauth2_token", side_effect=ValueError("Token used too early, 123")):
        resp = client.post("/login/google", json={"credential": "abc"})
    assert resp.status_code == 401 and "123" not in resp.get_json()["error"]


def test_an_smtp_failure_is_logged_but_not_shown():
    client = _client(user_id=1, role="system_administrator")
    body = {"email": "new@example.org", "full_name": "New Person", "role": "emergency_responder"}
    with patch("routes_users.models.get_user_by_email", return_value=None), \
         patch("routes_users.models.username_from_email", return_value="new"), \
         patch("routes_users.models.create_invited_user", side_effect=OSError("smtp.internal.host:587 refused")), \
         patch("routes_users.models.log_event") as mock_log:
        resp = client.post("/api/users/invite", json=body)
    assert resp.status_code == 502 and "smtp.internal.host" not in resp.get_json()["error"]
    assert "smtp.internal.host" in mock_log.call_args.args[2]
