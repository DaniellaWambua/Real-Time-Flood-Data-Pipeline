"""
Migration adding the System Administration columns and tables to an existing database
(a fresh database gets them from db/init/02_schema.sql). Safe to re-run. From db/:

    python add_admin_features.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_admin_features():
    db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    print("users.is_active: present.")

    db.execute(
        "CREATE TABLE IF NOT EXISTS system_logs ("
        "id BIGSERIAL PRIMARY KEY, "
        "occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "actor TEXT, "
        "action TEXT NOT NULL, "
        "detail TEXT"
        ")"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_system_logs_occurred_at "
        "ON system_logs (occurred_at DESC)"
    )
    print("system_logs table: present.")


if __name__ == "__main__":
    add_admin_features()
