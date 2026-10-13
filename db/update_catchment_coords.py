"""
Move an already-seeded database's catchment_areas.geom onto whatever
seed.py's CATCHMENT_COORDS currently says, by name.

seed.py itself is deliberately idempotent the other way: it skips a
catchment that already exists rather than touching it, so running it
again after editing CATCHMENT_COORDS does nothing to existing rows.
That is the right default for a script every setup runs, but it means
a correction to CATCHMENT_COORDS (like the 2026-10-11 move from rough
guesses to real OSM waterway points, see COORDS_SOURCES.md) needs this
separate, explicit step to actually reach a database that was already
seeded under the old values.

Usage (from the db/ directory, with the db container running):
    python update_catchment_coords.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402  (backend/db.py's psycopg2 connection helper)
from seed import CATCHMENT_COORDS  # noqa: E402


def update_catchment_coords():
    for name, (lon, lat) in CATCHMENT_COORDS.items():
        existing = db.query_one(
            "SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat FROM catchment_areas WHERE name = %s",
            (name,),
        )
        if not existing:
            print(f"catchment '{name}' not found, run seed.py first. skipping.")
            continue
        if abs(existing["lon"] - lon) < 1e-9 and abs(existing["lat"] - lat) < 1e-9:
            print(f"catchment '{name}' already at the current coordinates, skipping.")
            continue
        print(
            f"catchment '{name}': ({existing['lon']:.6f}, {existing['lat']:.6f}) "
            f"-> ({lon:.6f}, {lat:.6f})"
        )
        db.execute(
            "UPDATE catchment_areas SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326) "
            "WHERE name = %s",
            (lon, lat, name),
        )


if __name__ == "__main__":
    update_catchment_coords()
