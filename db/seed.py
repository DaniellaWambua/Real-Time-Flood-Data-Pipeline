"""
Seed data_sources and catchment_areas so the ingestion pipeline has
somewhere to write to.

Catchment coordinates below are rough, single-point estimates for each
river (consistent with catchment_areas.geom's own column comment in
02_schema.sql: "catchment reference point, 3km-buffered estimate"), picked
to get the end-to-end pipeline running now. They are NOT the coordinates
used in the ERA5/CHIRPS extraction notebooks, which live outside this
repository (see project-checklist.md). Replace CATCHMENT_COORDS below with
those exact values once that notebook (or Daniella) supplies them, then
re-run this script; it is safe to re-run, existing rows are left as is.

Usage (from the db/ directory, with the db container running):
    python seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402  (backend/db.py's psycopg2 connection helper)

# name -> (longitude, latitude). Longitude first, to match PostGIS's
# ST_MakePoint(lon, lat) argument order.
CATCHMENT_COORDS = {
    "Nairobi River": (36.8265, -1.2864),   # Nairobi River at the CBD
    "Mathare": (36.8550, -1.2611),         # Mathare Valley
    "Ngong": (36.7820, -1.3103),           # Ngong River near Kibera
    "Motoine": (36.7524, -1.3975),         # Motoine River, Ongata Rongai
    "Nyando River": (34.8333, -0.1500),    # Nyando River mouth, Kano Plains
    "Tana River": (39.6401, -0.4536),      # Tana River at Garissa
}

CATCHMENT_COUNTY = {
    "Nairobi River": "Nairobi",
    "Mathare": "Nairobi",
    "Ngong": "Nairobi",
    "Motoine": "Kajiado",
    "Nyando River": "Kisumu",
    "Tana River": "Garissa",
}

DATA_SOURCES = [
    # (name, source_type, fetch_interval, connection_status)
    ("CHIRPS", "satellite_rainfall", "1 day", "disconnected"),
    ("GloFAS", "hydrological_model", "1 day", "disconnected"),
    ("KMD", "advisory", "1 day", "disconnected"),
    ("simulated-dataset-feed", "historical-replay", "1 second", "disconnected"),
]


def seed_catchments():
    for name, (lon, lat) in CATCHMENT_COORDS.items():
        existing = db.query_one("SELECT id FROM catchment_areas WHERE name = %s", (name,))
        if existing:
            print(f"catchment '{name}' already exists (id={existing['id']}), skipping.")
            continue
        db.execute(
            "INSERT INTO catchment_areas (name, county, geom) "
            "VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
            (name, CATCHMENT_COUNTY[name], lon, lat),
        )
        print(f"inserted catchment '{name}'.")


def seed_data_sources():
    for name, source_type, fetch_interval, status in DATA_SOURCES:
        existing = db.query_one("SELECT id FROM data_sources WHERE name = %s", (name,))
        if existing:
            print(f"data source '{name}' already exists (id={existing['id']}), skipping.")
            continue
        db.execute(
            "INSERT INTO data_sources (name, source_type, fetch_interval, connection_status) "
            "VALUES (%s, %s, %s::interval, %s)",
            (name, source_type, fetch_interval, status),
        )
        print(f"inserted data source '{name}'.")


if __name__ == "__main__":
    seed_data_sources()
    seed_catchments()
