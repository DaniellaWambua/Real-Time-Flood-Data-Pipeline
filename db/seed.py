"""
Seed data_sources and catchment_areas so the ingestion pipeline has
somewhere to write to.

CATCHMENT_COORDS below are single points actually on each named river's
channel, taken from OpenStreetMap's own "waterway" data for that river,
near the locality CATCHMENT_COUNTY already associates it with (CBD,
Huruma, Kibera, Karen, Ahero, Garissa), not hand-picked guesses. They
are NOT the coordinates used in the ERA5/CHIRPS extraction notebooks,
which live outside this repository (see project-checklist.md) and
remain the more authoritative source if they turn up; replace
CATCHMENT_COORDS with those exact values if so, then re-run this script
(it is safe to re-run, existing rows are left as is: see
update_catchment_coords.py in this directory for moving an already-
seeded database onto a new CATCHMENT_COORDS value instead).

Usage (from the db/ directory, with the db container running):
    python seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402  (backend/db.py's psycopg2 connection helper)

# name -> (longitude, latitude). Longitude first, to match PostGIS's
# ST_MakePoint(lon, lat) argument order.
# Nairobi River/Mathare/Ngong/Motoine are OSM waterway points, queried
# via the Overpass API on 2026-10-11 (see db/COORDS_SOURCES.md). Mukuru
# and Ruaraka replace Nyando River/Tana River for the v10 Nairobi-only
# rescoping (src/config.py's CATCHMENTS): these two are the exact
# Earth Engine/Open-Meteo points used in Historical_Data_extraction.ipynb
# to pull their CHIRPS/GloFAS/ERA5 rows, not independently sourced OSM
# points, so the database's catchment location matches what the model
# was actually trained on.
CATCHMENT_COORDS = {
    # On "Nairobi River" (OSM way), 0.84km from the CBD.
    "Nairobi River": (36.8222826, -1.2790314),
    # On "Mathare River" (OSM way), 0.39km from Huruma.
    "Mathare": (36.8688588, -1.2564097),
    # On "Ngong river" (OSM way), 0.10km from Kibera.
    "Ngong": (36.7897207, -1.3107824),
    # On "Motoine River" (OSM way); OSM's mapped extent of this river
    # currently stops in Karen, about 8.5km north of Ongata Rongai town
    # (where Motoine flooding is usually reported) with no mapped
    # segment there to verify against, so this is the southmost point
    # OSM has actually mapped on the channel, not an Ongata Rongai point.
    "Motoine": (36.7529515, -1.3196194),
    # Mukuru kwa Njenga/Reuben, Embakasi: the point used for its CHIRPS/
    # GloFAS/ERA5 extraction.
    "Mukuru": (36.8827, -1.32564),
    # Ruaraka, along the Nairobi River downstream: the point used for
    # its CHIRPS/GloFAS/ERA5 extraction.
    "Ruaraka": (36.91359, -1.27761),
}

CATCHMENT_COUNTY = {
    "Nairobi River": "Nairobi",
    "Mathare": "Nairobi",
    "Ngong": "Nairobi",
    "Motoine": "Kajiado",
    "Mukuru": "Nairobi",
    "Ruaraka": "Nairobi",
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
