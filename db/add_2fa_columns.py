"""
Migration adding two-factor authentication columns to an existing database
(a fresh database gets them from db/init/02_schema.sql). Safe to re-run. From db/:

    python add_2fa_columns.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_2fa_columns():
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT")
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT false")
    print("users.totp_secret/totp_enabled: present.")


if __name__ == "__main__":
    add_2fa_columns()
