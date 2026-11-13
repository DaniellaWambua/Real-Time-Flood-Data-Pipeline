"""
Bring an existing database's data_sources to one active feed carrying three datasets.
The old CHIRPS, GloFAS and KMD rows are marked inactive, not deleted, so rows referencing them
stay readable. Safe to re-run; a fresh database does not need it.
    python db/retire_old_sources.py
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
