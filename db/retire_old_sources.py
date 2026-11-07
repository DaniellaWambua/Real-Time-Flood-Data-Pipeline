"""
Bring an existing database's data_sources table to the final shape: one active
feed carrying three datasets.

CHIRPS, GloFAS and KMD were seeded as separate sources when the design expected
three separate ingestion paths. The pipeline that was built combines CHIRPS,
IMERG and ERA5-Land into one daily reading per catchment before publishing, so
those rows never received anything and sat on the screens as three disconnected
sources. They are marked inactive rather than deleted, the same way the retired
catchments are kept, so the old rows that reference them stay readable.

Safe to re-run. Run once against an existing database:
    python db/retire_old_sources.py
A database built fresh from db/init/02_schema.sql and db/seed.py already comes
out this way and does not need it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import db  # noqa: E402

KEEP = "historical-replay"  # must match ingestion/config.py's REPLAY_SOURCE
DATASETS = "CHIRPS, IMERG, ERA5-Land"


def add_columns():
    db.execute("ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS datasets TEXT")
    db.execute("ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    print("columns datasets and is_active are present.")


def retire_others():
    kept = db.query_one("SELECT id FROM data_sources WHERE name = %s", (KEEP,))
    if kept is None:
        print(f"no '{KEEP}' source found; run the producer and consumer first, or db/seed.py.")
        return

    db.execute(
        "UPDATE data_sources SET datasets = %s, is_active = true WHERE name = %s",
        (DATASETS, KEEP),
    )
    db.execute("UPDATE data_sources SET is_active = false WHERE name <> %s", (KEEP,))

    for row in db.query_all(
        "SELECT name, is_active, datasets, "
        "(SELECT COUNT(*) FROM hydro_data_records h WHERE h.data_source_id = ds.id) AS rows "
        "FROM data_sources ds ORDER BY ds.id"
    ):
        state = "active" if row["is_active"] else "retired"
        print(f"  {row['name']}: {state}, {row['rows']} readings{', ' + row['datasets'] if row['datasets'] else ''}")


if __name__ == "__main__":
    add_columns()
    retire_others()
    print("done.")
