"""
One-off migration adding TOTP-based two-factor authentication to the
existing session-based login (proposal 3.6.2 names "secure user
authentication" as a requirement; this goes beyond what the proposal
asked for, same spirit as the rest of this checklist's "going an extra
mile" items). A fresh `docker compose up` picks these up automatically
from db/init/02_schema.sql; this script is for an already-running
database, run once from the db/ directory:

    python add_2fa_columns.py

Both statements are idempotent (IF NOT EXISTS), safe to run more than
once. totp_secret is NULL until a user enrols, either through the app
(backend/routes_auth.py's POST /totp/setup + /totp/enable) or from the
command line (backend/enable_totp.py); totp_enabled stays false until
they confirm the first code, so a half-finished enrolment never locks
anyone out.
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
