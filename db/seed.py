"""
Seed data_sources and catchment_areas. Safe to re-run; existing rows are left as they are
(use update_catchment_coords.py to move a seeded catchment).

Usage (from db/, with the db container running):
    python seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402  (backend/db.py's psycopg2 connection helper)

# name -> (longitude, latitude), in PostGIS ST_MakePoint order. Each point lies on the river's
# OpenStreetMap waterway near the named locality (queries in db/COORDS_SOURCES.md).
CATCHMENT_COORDS = {
    # On "Nairobi River" (OSM way), 0.84km from the CBD.
    "Nairobi River": (36.8222826, -1.2790314),
    # On "Mathare River" (OSM way), 0.39km from Huruma.
    "Mathare": (36.8688588, -1.2564097),
    # On "Ngong river" (OSM way), 0.10km from Kibera.
    "Ngong": (36.7897207, -1.3107824),
    # OSM's mapped Motoine stops in Karen, so this is its southernmost mapped point.
    "Motoine": (36.7529515, -1.3196194),
    # On "Nyando river" (OSM way), 0.21km from Ahero.
    "Nyando River": (34.9208784, -0.172945),
    # On "Tana River" (OSM way), 0.79km from central Garissa.
    "Tana River": (39.6356341, -0.4695316),
}

CATCHMENT_COUNTY = {
    "Nairobi River": "Nairobi",
    "Mathare": "Nairobi",
    "Ngong": "Nairobi",
    "Motoine": "Kajiado",
    "Nyando River": "Kisumu",
    "Tana River": "Garissa",
}

# One feed carrying CHIRPS, IMERG and ERA5-Land, combined into one daily reading per catchment.
# The name must match ingestion/config.py's REPLAY_SOURCE.
DATA_SOURCES = [
    # (name, source_type, fetch_interval, connection_status, datasets)
    ("historical-replay", "daily-feed", "1 day", "disconnected", "CHIRPS, IMERG, ERA5-Land"),
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
    for name, source_type, fetch_interval, status, datasets in DATA_SOURCES:
        existing = db.query_one("SELECT id FROM data_sources WHERE name = %s", (name,))
        if existing:
            print(f"data source '{name}' already exists (id={existing['id']}), skipping.")
            continue
        db.execute(
            "INSERT INTO data_sources (name, source_type, fetch_interval, connection_status, datasets) "
            "VALUES (%s, %s, %s::interval, %s, %s)",
            (name, source_type, fetch_interval, status, datasets),
        )
        print(f"inserted data source '{name}'.")


if __name__ == "__main__":
    seed_data_sources()
    seed_catchments()
