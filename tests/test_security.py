"""
Checks for the sign-in hardening from the security audit (docs: Security audit of the Flood Early
Warning System, findings 1 to 4):
  1  sessions end at once on logout, deactivation, a role change or a new version
  2  sign-in and code attempts are rate limited, and a half-finished sign-in times out
  3  /totp/setup cannot replace a working authenticator, and a code works only once
  4  state-changing requests must be JSON, and the cookie is SameSite=Strict and HttpOnly
The database is replaced by stand-ins.
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyotp
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import models  # noqa: E402
import security  # noqa: E402

SECRET = "BASE32SECRET3232"
USER = {"id": 1, "username": "officer", "password_hash": "x", "role": "system_administrator",
        "is_active": True, "totp_enabled": True, "totp_secret": SECRET, "session_version": 3}


def _client(rate_limits=False):
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["RATE_LIMITS"] = rate_limits
    security.reset()
    return flask_app.test_client()


def _signed_in(client, sv=3, role="system_administrator"):
    with client.session_transaction() as sess:
        sess.update(user_id=1, username="officer", role=role, sv=sv)


def _pending(client, started=None):
    with client.session_transaction() as sess:
        sess.update(pending_user_id=1, step_started=int(started or time.time()))


def _state(**changes):
    return {"id": 1, "username": "officer", "role": "system_administrator", "is_active": True,
            "session_version": 3, **changes}


# 1. Sessions end at once

@pytest.mark.real_session_check
def test_a_session_from_before_the_account_was_signed_out_is_refused():
    client = _client()
    _signed_in(client, sv=3)
    with patch("decorators.models.session_state", return_value=_state(session_version=4)):
        assert client.get("/api/catchments").status_code == 401
        assert client.get("/me").status_code == 401
    with client.session_transaction() as sess:
        assert "user_id" not in sess  # the stale cookie is cleared


@pytest.mark.real_session_check
def test_a_deactivated_account_loses_access_straight_away():
    client = _client()
    _signed_in(client)
    with patch("decorators.models.session_state", return_value=_state(is_active=False)):
        assert client.get("/api/users").status_code == 401


@pytest.mark.real_session_check
def test_the_role_comes_from_the_database_not_the_cookie():
    client = _client()
    _signed_in(client, role="system_administrator")  # cookie claims admin
    with patch("decorators.models.session_state", return_value=_state(role="emergency_responder")):
        assert client.get("/api/users").status_code == 403


@pytest.mark.real_session_check
def test_a_current_session_still_works():
    client = _client()
    _signed_in(client)
    with patch("decorators.models.session_state", return_value=_state()), \
         patch("routes_users.models.list_users", return_value=[]):
        assert client.get("/api/users").status_code == 200
        assert client.get("/me").get_json()["role"] == "system_administrator"


def test_signing_in_stores_the_session_version():
    client = _client()
    _pending(client)
    with patch("routes_auth.models.get_user_by_id", return_value=USER), \
         patch("routes_auth.models.claim_totp_step", return_value=True), \
         patch("routes_auth.models.log_event"):
        assert client.post("/login/verify-totp", json={"code": pyotp.TOTP(SECRET).now()}).status_code == 200
    with client.session_transaction() as sess:
        assert sess["sv"] == 3 and "pending_user_id" not in sess


@pytest.mark.parametrize("call", [
    lambda: models.set_user_active(2, False),
    lambda: models.update_user_role(2, "government_official"),
    lambda: models.update_password("alice", "a-new-long-passphrase"),
    lambda: models.set_user_email(2, "new@example.org"),
    lambda: models.disable_totp(2),
    lambda: models.end_sessions(2),
])
def test_account_changes_end_its_sessions(call):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1
    with patch("models.db.get_connection", return_value=conn):
        call()
    sql = cursor.execute.call_args.args[0]
    assert "session_version = session_version + 1" in sql


# 2. Rate limits and the time allowed for the second step

def test_repeated_password_guesses_for_one_account_are_stopped():
    client = _client(rate_limits=True)
    with patch("routes_auth.models.get_user_by_login", return_value=None), \
         patch("routes_auth.models.log_event"):
        codes = [client.post("/login", json={"username": "Officer", "password": "guess"}).status_code
                 for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_the_limit_response_says_when_to_try_again():
    client = _client(rate_limits=True)
    with patch("routes_auth.models.get_user_by_login", return_value=None), \
         patch("routes_auth.models.log_event"):
        for _ in range(10):
            client.post("/login", json={"username": "officer", "password": "guess"})
        resp = client.post("/login", json={"username": "officer", "password": "guess"})
    assert resp.status_code == 429 and int(resp.headers["Retry-After"]) > 0
    assert "too many attempts" in resp.get_json()["error"]


def test_guessing_the_2fa_code_is_stopped_after_five_tries():
    client = _client(rate_limits=True)
    _pending(client)
    with patch("routes_auth.models.get_user_by_id", return_value=USER), \
         patch("routes_auth.models.log_event"):
        codes = [client.post("/login/verify-totp", json={"code": "000000"}).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]


def test_limits_are_off_unless_turned_on():
    client = _client(rate_limits=False)
    with patch("routes_auth.models.get_user_by_login", return_value=None), \
         patch("routes_auth.models.log_event"):
        codes = {client.post("/login", json={"username": "x", "password": "y"}).status_code for _ in range(15)}
    assert codes == {401}


def test_a_half_finished_sign_in_times_out():
    client = _client()
    _pending(client, started=time.time() - 301)
    with patch("routes_auth.models.get_user_by_id", return_value=USER):
        resp = client.post("/login/verify-totp", json={"code": pyotp.TOTP(SECRET).now()})
    assert resp.status_code == 400 and "timed out" in resp.get_json()["error"]


def test_a_deactivated_account_cannot_finish_signing_in():
    client = _client()
    _pending(client)
    with patch("routes_auth.models.get_user_by_id", return_value={**USER, "is_active": False}):
        assert client.post("/login/verify-totp", json={"code": pyotp.TOTP(SECRET).now()}).status_code == 400


# 3. Authenticator secrets and codes

def test_a_working_authenticator_cannot_be_replaced():
    client = _client()
    _signed_in(client)
    with patch("routes_auth.models.get_user_by_id", return_value=USER), \
         patch("routes_auth.models.set_totp_secret") as mock_set:
        resp = client.post("/totp/setup", json={})
    assert resp.status_code == 409
    mock_set.assert_not_called()


def test_first_time_setup_still_works():
    client = _client()
    with client.session_transaction() as sess:
        sess.update(setup_user_id=1, step_started=int(time.time()))
    new_user = {**USER, "totp_enabled": False, "totp_secret": None}
    with patch("routes_auth.models.get_user_by_id", return_value=new_user), \
         patch("routes_auth.models.set_totp_secret") as mock_set:
        resp = client.post("/totp/setup", json={})
    assert resp.status_code == 200 and "secret" in resp.get_json()
    mock_set.assert_called_once()


def test_a_used_code_cannot_be_used_again():
    client = _client()
    _pending(client)
    with patch("routes_auth.models.get_user_by_id", return_value=USER), \
         patch("routes_auth.models.claim_totp_step", return_value=False), \
         patch("routes_auth.models.log_event"):
        resp = client.post("/login/verify-totp", json={"code": pyotp.TOTP(SECRET).now()})
    assert resp.status_code == 401


def test_claiming_a_code_only_moves_forward():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.rowcount = 0  # the step, or a later one, was already used
    with patch("models.db.get_connection", return_value=conn):
        assert models.claim_totp_step(1, 5000) is False
    sql, params = cursor.execute.call_args.args
    assert "totp_last_step < %s" in sql and params == (5000, 1, 5000)


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", None])
def test_malformed_codes_are_refused_without_a_lookup(code):
    import routes_auth
    with patch("routes_auth.models.claim_totp_step") as mock_claim:
        assert routes_auth._code_ok(USER, code) is False
    mock_claim.assert_not_called()


# 4. Cross-site request forgery and the cookie

def test_a_form_post_from_another_site_is_refused():
    client = _client()
    _signed_in(client)
    with patch("routes_users.models.disable_totp") as mock_disable:
        resp = client.post("/api/users/5/reset-2fa", data={})  # what a hidden HTML form sends
    assert resp.status_code == 415
    mock_disable.assert_not_called()


def test_reads_do_not_need_json():
    client = _client()
    _signed_in(client)
    with patch("routes_users.models.list_users", return_value=[]):
        assert client.get("/api/users").status_code == 200


def test_the_session_cookie_is_strict_and_hidden_from_scripts():
    client = _client()
    with patch("routes_auth.models.get_user_by_login", return_value=USER), \
         patch("routes_auth.models.verify_password", return_value=True), \
         patch("routes_auth.models.log_event"):
        resp = client.post("/login", json={"username": "officer", "password": "correct"})
    cookie = resp.headers["Set-Cookie"]
    assert "SameSite=Strict" in cookie and "HttpOnly" in cookie
