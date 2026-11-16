"""
Checks for the Settings page endpoints (/account and /account/password) with mocked models:
signed-out access, the details returned, and each branch of changing one's own password.
"""

import datetime
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app as app_module  # noqa: E402
import models  # noqa: E402

USER = {
    "id": 7,
    "username": "officer1",
    "password_hash": "pbkdf2:sha256:irrelevant",
    "role": "disaster_management_agency",
    "is_active": True,
    "created_at": datetime.datetime(2026, 11, 1, 9, 0, tzinfo=datetime.timezone.utc),
    "totp_secret": "SECRET",
    "totp_enabled": True,
    "email": "officer1@example.org",
    "full_name": "Officer One",
    "organisation": "Nairobi County",
}


def _signed_in_client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = USER["id"]
        sess["username"] = USER["username"]
        sess["role"] = USER["role"]
    return client


def _signed_out_client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def test_account_needs_a_session():
    client = _signed_out_client()
    assert client.get("/account").status_code == 401
    assert client.post("/account/password", json={}).status_code == 401


def test_account_returns_details_without_secrets():
    client = _signed_in_client()
    with (
        patch("routes_auth.models.get_user_by_id", return_value=USER),
        patch("routes_auth.models.last_password_change", return_value=None),
    ):
        resp = client.get("/account")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "officer1"
    assert body["full_name"] == "Officer One"
    assert body["email"] == "officer1@example.org"
    assert body["organisation"] == "Nairobi County"
    assert body["role"] == "disaster_management_agency"
    assert body["totp_enabled"] is True
    assert body["password_changed_at"] is None
    assert "password_hash" not in body and "totp_secret" not in body


def test_change_password_rejects_short_or_unchanged_passwords():
    client = _signed_in_client()
    with (
        patch("routes_auth.models.get_user_by_id", return_value=USER),
        patch("routes_auth.models.update_password") as mock_update,
    ):
        missing = client.post("/account/password", json={"current_password": "", "new_password": ""})
        short = client.post("/account/password", json={"current_password": "old-pass-1", "new_password": "short"})
        same = client.post("/account/password", json={"current_password": "same-pass-1", "new_password": "same-pass-1"})
    assert missing.status_code == 400
    assert short.status_code == 400 and "at least 12" in short.get_json()["error"]
    assert same.status_code == 400
    mock_update.assert_not_called()


def test_change_password_with_wrong_current_password_is_refused_and_logged():
    client = _signed_in_client()
    with (
        patch("routes_auth.models.get_user_by_id", return_value=USER),
        patch("routes_auth.models.verify_password", return_value=False),
        patch("routes_auth.models.update_password") as mock_update,
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/account/password", json={"current_password": "wrong-pass", "new_password": "kettle sings at dawn"})
    assert resp.status_code == 403
    mock_update.assert_not_called()
    mock_log.assert_called_once_with("officer1", "password_change_failure", "wrong current password")


def test_change_password_success_updates_and_logs():
    client = _signed_in_client()
    with (
        patch("routes_auth.models.get_user_by_id", return_value=USER),
        patch("routes_auth.models.verify_password", return_value=True),
        patch("routes_auth.models.update_password", return_value=True) as mock_update,
        patch("routes_auth.models.log_event") as mock_log,
    ):
        resp = client.post("/account/password", json={"current_password": "old-pass-1", "new_password": "kettle sings at dawn"})
    assert resp.status_code == 200
    mock_update.assert_called_once_with("officer1", "kettle sings at dawn")
    mock_log.assert_called_once_with("officer1", "password_changed", None)


def test_password_events_are_filed_under_sign_in():
    assert models.log_category("password_changed") == "sign_in"
    assert models.log_category("password_change_failure") == "sign_in"
    assert models.log_category("password_reset_completed") == "sign_in"
    assert models.log_category("password_reset_sent") == "accounts"
