"""
Sanity checks for models.update_password (backend/models.py), the
helper behind backend/change_password.py. Run directly with plain
Python, no pytest, no live Postgres, same style as
tests/test_preprocessing.py and tests/test_dashboard_api.py.

db.get_connection() is mocked with a MagicMock cursor/connection pair,
so this checks the SQL shape, the hashing, and the found/not-found
return value, not real SQL against a live database.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import models  # noqa: E402
from werkzeug.security import check_password_hash  # noqa: E402


def _fake_connection(rowcount):
    """A MagicMock connection/cursor pair reporting `rowcount` rows
    affected by the UPDATE, the way a real match (1) or no match (0)
    would."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = rowcount
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


def test_update_password_hashes_and_updates():
    conn, cursor = _fake_connection(rowcount=1)
    with patch("models.db.get_connection", return_value=conn):
        result = models.update_password("alice", "new-password-456")

    assert result is True
    conn.commit.assert_called_once()

    sql, params = cursor.execute.call_args.args
    assert "UPDATE users SET password_hash" in sql
    assert params[1] == "alice"

    new_hash = params[0]
    # pbkdf2, matching create_user() (see that function's own comment
    # on why, not Werkzeug's scrypt default), and actually verifiable.
    assert new_hash.startswith("pbkdf2:sha256")
    assert check_password_hash(new_hash, "new-password-456")
    assert not check_password_hash(new_hash, "wrong-password")


def test_update_password_no_such_user():
    conn, cursor = _fake_connection(rowcount=0)
    with patch("models.db.get_connection", return_value=conn):
        result = models.update_password("nobody", "whatever")
    assert result is False


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
