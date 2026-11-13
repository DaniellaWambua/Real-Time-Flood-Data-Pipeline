"""
One-off migration for the Open-Meteo rainfall warning, for a database created
before 02_schema.sql had the rainfall_forecasts table. Safe to run more than once.
Run from the db/ directory: python add_rainfall_forecasts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

db.execute("""
CREATE TABLE IF NOT EXISTS rainfall_forecasts (
    id              SERIAL PRIMARY KEY,
    catchment_id    INTEGER NOT NULL REFERENCES catchment_areas(id),
    forecast_date   DATE NOT NULL,
    precipitation_mm DOUBLE PRECISION NOT NULL,
    threshold_mm    DOUBLE PRECISION NOT NULL,
    is_warning      BOOLEAN NOT NULL,
    source          TEXT NOT NULL,
    issued_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (catchment_id, forecast_date)
)""")
print("rainfall_forecasts table: present")
