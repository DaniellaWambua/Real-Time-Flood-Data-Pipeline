"""
One-off migration for provisional alerts (the fast model without CHIRPS), for a database created
before 02_schema.sql had these columns. Safe to run more than once.
Run from the db/ directory: python add_provisional_alerts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

db.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS provisional BOOLEAN NOT NULL DEFAULT false")
db.execute("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS confirmation TEXT")
print("alerts provisional columns: present")
