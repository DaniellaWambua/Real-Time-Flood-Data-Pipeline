"""
One-off migration for the System Administration screen's new features
(user account controls, system logs, pipeline-health timestamps): adds
what db/init/02_schema.sql now expects to a database that was already
initialised before these columns/tables existed. A fresh
`docker compose up` picks these up automatically from 02_schema.sql;
this script is for an already-running database, the same reason
update_catchment_coords.py exists for the catchment coordinates fix,
run once from the db/ directory:

    python add_admin_features.py

Both statements are idempotent (IF NOT EXISTS), safe to run more than
once or against a database that already has them.
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
