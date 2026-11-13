"""
Checks for the sign-in routes with mocked models: each branch (bad credentials, deactivated
account, success) and the event it logs.
"""

import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app as app_module  # noqa: E402


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


ACTIVE_USER = {
    "id": 1,
    "username": "root-admin",
    "password_hash": "pbkdf2:sha256:irrelevant",
    "role": "system_administrator",
    "is_active": True,
}

DEACTIVATED_USER = {**ACTIVE_USER, "is_active": False}


def test_login_requires_username_and_password():
    client = _client()
    resp = client.post("/login", json={"username": "", "password": ""})
    assert resp.status_code == 400


def test_login_unknown_username_logs_failure():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_login", return_value=None),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401
    mock_log.assert_called_once_with("nobody", "login_failure", "invalid username or password")


def test_login_wrong_password_logs_failure():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_login", return_value=ACTIVE_USER),
        patch("routes_auth.models.verify_password", return_value=False),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "wrong"})
    assert resp.status_code == 401
    mock_log.assert_called_once_with("root-admin", "login_failure", "invalid username or password")


def test_login_deactivated_account_rejected():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_login", return_value=DEACTIVATED_USER),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "correct"})
    assert resp.status_code == 403
    mock_log.assert_called_once_with("root-admin", "login_failure", "account is deactivated")


def test_a_correct_password_alone_never_signs_in():
    """Without 2FA set up, the password step leads to 2FA setup, not a session."""
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_login", return_value=ACTIVE_USER),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "correct"})
    assert resp.status_code == 200 and resp.get_json() == {"requires_totp_setup": True}
    mock_log.assert_called_once_with("root-admin", "login_password_ok_awaiting_2fa_setup", None)
    with client.session_transaction() as sess:
        assert "user_id" not in sess and sess["setup_user_id"] == 1


def test_an_account_with_2fa_is_asked_for_its_code():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_login", return_value={**ACTIVE_USER, "totp_enabled": True}),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.log_event"),
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "correct"})
    assert resp.get_json() == {"requires_totp": True}
    with client.session_transaction() as sess:
        assert "user_id" not in sess and sess["pending_user_id"] == 1


def test_finishing_2fa_setup_signs_in():
    client = _client()
    with client.session_transaction() as sess:
        sess["setup_user_id"] = 1
    with (
        patch("routes_auth.models.get_user_by_id", return_value={**ACTIVE_USER, "totp_secret": "BASE32SECRET3232"}),
        patch("routes_auth.pyotp.TOTP.verify", return_value=True),
        patch("routes_auth.models.enable_totp") as mock_enable,
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/totp/enable", json={"code": "123456"})
    assert resp.status_code == 200 and resp.get_json()["username"] == "root-admin"
    mock_enable.assert_called_once_with(1)
    assert [c.args[1] for c in mock_log.call_args_list] == ["totp_enabled", "login_success"]
    with client.session_transaction() as sess:
        assert sess["user_id"] == 1 and "setup_user_id" not in sess


def test_setup_state_cannot_reach_the_data():
    client = _client()
    with client.session_transaction() as sess:
        sess["setup_user_id"] = 1
    assert client.get("/me").status_code == 401
    assert client.get("/api/catchments").status_code == 401


def test_2fa_can_no_longer_be_turned_off_by_the_user():
    assert _client().post("/totp/disable", json={"password": "x"}).status_code == 404


def test_logout_clears_session():
    client = _client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "root-admin"
        sess["role"] = "system_administrator"

    resp = client.post("/logout")
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_me_requires_login():
    client = _client()
    resp = client.get("/me")
    assert resp.status_code == 401


def test_me_returns_session_info():
    client = _client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "root-admin"
        sess["role"] = "system_administrator"

    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.get_json() == {"id": 1, "username": "root-admin", "role": "system_administrator"}


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
