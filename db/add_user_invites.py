"""
One-off migration for email invites and password-reset links, for a database created
before 02_schema.sql had them. Safe to run more than once.
Run from the db/ directory: python add_user_invites.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT")
db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS organisation TEXT")
db.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
db.execute(
    "CREATE TABLE IF NOT EXISTS user_tokens ("
    "id SERIAL PRIMARY KEY, "
    "user_id INTEGER NOT NULL REFERENCES users(id), "
    "purpose TEXT NOT NULL CHECK (purpose IN ('invite', 'reset')), "
    "token_hash TEXT NOT NULL UNIQUE, "
    "expires_at TIMESTAMPTZ NOT NULL, "
    "used_at TIMESTAMPTZ, "
    "created_by TEXT, "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
)
db.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens (user_id, purpose)")
print("users.full_name, users.organisation, nullable password_hash and user_tokens: present")
