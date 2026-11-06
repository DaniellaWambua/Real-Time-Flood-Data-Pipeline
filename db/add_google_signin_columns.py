"""
One-off migration adding Google Sign-In support to the existing
password-based login (another "going an extra mile" item, like
db/add_2fa_columns.py). A fresh `docker compose up` picks this up
automatically from db/init/02_schema.sql; this script is for an
already-running database, run once from the db/ directory:

    python add_google_signin_columns.py

Accounts stay admin-provisioned (proposal 3.6.2, create_user.py): this
does not add public registration. email is NULL until an admin attaches
one to an existing account (System Administration screen, or
create_user.py's optional 5th argument); backend/routes_auth.py's
POST /login/google only succeeds for an email that already matches a
provisioned account, and still goes through the same 2FA check as a
password login.
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
