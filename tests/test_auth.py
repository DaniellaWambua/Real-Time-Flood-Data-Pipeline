"""
Sanity checks for the auth routes (backend/routes_auth.py), run the
same way as tests/test_dashboard_api.py: plain Python, no pytest, no
live Postgres. models.get_user_by_username/verify_password/log_event
are mocked with canned values, so this checks login's branching (bad
credentials, a deactivated account, success) and that each branch logs
the right system_logs event, not real password hashing or SQL.
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
        patch("routes_auth.models.get_user_by_username", return_value=None),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "nobody", "password": "whatever"})
    assert resp.status_code == 401
    mock_log.assert_called_once_with("nobody", "login_failure", "invalid username or password")


def test_login_wrong_password_logs_failure():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_username", return_value=ACTIVE_USER),
        patch("routes_auth.models.verify_password", return_value=False),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "wrong"})
    assert resp.status_code == 401
    mock_log.assert_called_once_with("root-admin", "login_failure", "invalid username or password")


def test_login_deactivated_account_rejected():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_username", return_value=DEACTIVATED_USER),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "correct"})
    assert resp.status_code == 403
    mock_log.assert_called_once_with("root-admin", "login_failure", "account is deactivated")


def test_login_success_sets_session_and_logs():
    client = _client()
    with (
        patch("routes_auth.models.get_user_by_username", return_value=ACTIVE_USER),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/login", json={"username": "root-admin", "password": "correct"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"id": 1, "username": "root-admin", "role": "system_administrator"}
    mock_log.assert_called_once_with("root-admin", "login_success", None)

    with client.session_transaction() as sess:
        assert sess["user_id"] == 1
        assert sess["role"] == "system_administrator"


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
