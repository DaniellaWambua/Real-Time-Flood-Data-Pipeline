"""
Checks for the user management and logging helpers in models.py, with a mocked connection.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402


def _fake_connection(rowcount):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = rowcount
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def test_update_user_role_updates_matching_user():
    conn, cursor = _fake_connection(rowcount=1)
    with patch("models.db.get_connection", return_value=conn):
        result = models.update_user_role(2, "government_official")

    assert result is True
    conn.commit.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert "UPDATE users SET role" in sql
    assert params == ("government_official", 2)


def test_update_user_role_no_such_user():
    conn, cursor = _fake_connection(rowcount=0)
    with patch("models.db.get_connection", return_value=conn):
        result = models.update_user_role(999, "government_official")
    assert result is False


def test_set_user_active_deactivates():
    conn, cursor = _fake_connection(rowcount=1)
    with patch("models.db.get_connection", return_value=conn):
        result = models.set_user_active(2, False)

    assert result is True
    conn.commit.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert "UPDATE users SET is_active" in sql
    assert params == (False, 2)


def test_set_user_active_no_such_user():
    conn, cursor = _fake_connection(rowcount=0)
    with patch("models.db.get_connection", return_value=conn):
        result = models.set_user_active(999, True)
    assert result is False


def test_log_event_inserts_a_row():
    with patch("models.db.execute") as mock_execute:
        models.log_event("root-admin", "user_created", "newbie (emergency_responder)")

    sql, params = mock_execute.call_args.args
    assert "INSERT INTO system_logs" in sql
    assert params == ("root-admin", "user_created", "newbie (emergency_responder)", "accounts", None)


def test_log_event_allows_a_null_actor():
    with patch("models.db.execute") as mock_execute:
        models.log_event(None, "login_failure", "invalid username or password")

    _, params = mock_execute.call_args.args
    assert params[0] is None


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
