"""
One-off migration for alert responses (field updates, resource allocations and recovery notes),
for a database created before 02_schema.sql had the alert_responses table. Safe to run more than once.
Run from the db/ directory: python add_alert_responses.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

db.execute(
    "CREATE TABLE IF NOT EXISTS alert_responses ("
    "id SERIAL PRIMARY KEY, alert_id INTEGER NOT NULL REFERENCES alerts(id), kind TEXT NOT NULL, "
    "note TEXT NOT NULL, author TEXT NOT NULL, author_role TEXT NOT NULL, "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
)
db.execute("CREATE INDEX IF NOT EXISTS idx_alert_responses_alert ON alert_responses (alert_id, created_at)")
print("alert_responses table: present")
