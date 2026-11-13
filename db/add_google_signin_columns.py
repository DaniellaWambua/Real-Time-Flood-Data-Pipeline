"""
Migration adding the email column used by Google sign-in to an existing database
(a fresh database gets it from db/init/02_schema.sql). Safe to re-run. From db/:

    python add_google_signin_columns.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_google_signin_columns():
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT UNIQUE")
    print("users.email: present.")


if __name__ == "__main__":
    add_google_signin_columns()
