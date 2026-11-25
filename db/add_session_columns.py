"""
Migration adding the columns that make sessions revocable and authenticator codes single-use
(a fresh database gets them from db/init/02_schema.sql). Safe to re-run. From db/:

    python add_session_columns.py

Every session cookie issued before this runs has no session version, so everyone signs in once more.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_session_columns():
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_last_step BIGINT")
    print("users.session_version/totp_last_step: present.")


if __name__ == "__main__":
    add_session_columns()
