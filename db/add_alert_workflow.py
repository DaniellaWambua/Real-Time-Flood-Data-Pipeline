"""
One-off migration for the alert workflow (acknowledge and resolve), for a database
created before 02_schema.sql had these columns. Safe to run more than once.
Run from the db/ directory: python add_alert_workflow.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

for col, kind in [("acknowledged_at", "TIMESTAMPTZ"), ("acknowledged_by", "TEXT"),
                  ("resolved_at", "TIMESTAMPTZ"), ("resolved_by", "TEXT")]:
    db.execute(f"ALTER TABLE alerts ADD COLUMN IF NOT EXISTS {col} {kind}")
print("alerts workflow columns: present")
