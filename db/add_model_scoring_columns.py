"""
One-off migration for live model-driven anomaly scoring (proposal 3.6.4):
hydro_data_records previously stored only the five live-measured readings
(rainfall_mm, river_discharge_m3s, soil_moisture_m3m3, evaporation_mm,
oni), dropping the three rolling features the simulated feed already
publishes alongside them (rainfall_3day, rainfall_7day, discharge_change,
see ingestion/config.py's FEATURE_FIELDS and producer.py). Storing them
too means the live-scoring window builder (ingestion/model_scoring.py)
can read a catchment's full feature history straight back out of this
table, rather than recomputing rolling sums/diffs itself and risking a
second, drifting copy of logic that already exists once in the dataset
build. A fresh `docker compose up` picks these up automatically from
db/init/02_schema.sql; this script is for an already-running database,
run once from the db/ directory:

    python add_model_scoring_columns.py

All three statements are idempotent (IF NOT EXISTS), safe to run more
than once.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_model_scoring_columns():
    for column in ("rainfall_3day", "rainfall_7day", "discharge_change"):
        db.execute(f"ALTER TABLE hydro_data_records ADD COLUMN IF NOT EXISTS {column} DOUBLE PRECISION")
    print("hydro_data_records.rainfall_3day/rainfall_7day/discharge_change: present.")


if __name__ == "__main__":
    add_model_scoring_columns()
