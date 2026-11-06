"""
One-off migration to the final three catchments and model inputs, for a database
created before 02_schema.sql had these columns. Safe to run more than once.
Run from the db/ directory: python migrate_final_catchments.py
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

GEOJSON = Path(__file__).resolve().parent.parent / "data_collection/data/05_spatial/processed/catchments.geojson"
FINAL = {"nairobi": "Nairobi River", "mathare": "Mathare", "ngong": "Ngong"}  # model code -> database name
NEW_COLUMNS = ["imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "era5_rain_mm",
               "soil_1", "soil_2", "temp_c", "dewpoint_depression", "pressure_hpa"]

db.execute("ALTER TABLE catchment_areas ADD COLUMN IF NOT EXISTS code TEXT UNIQUE")
db.execute("ALTER TABLE catchment_areas ADD COLUMN IF NOT EXISTS boundary GEOMETRY(Polygon, 4326)")
db.execute("ALTER TABLE catchment_areas ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
for col in NEW_COLUMNS:
    db.execute(f"ALTER TABLE hydro_data_records ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION")
print("columns: present")

for f in json.loads(GEOJSON.read_text())["features"]:
    code = f["properties"]["catchment"]
    name, shape = FINAL[code], json.dumps(f["geometry"])
    if db.query_one("SELECT id FROM catchment_areas WHERE name = %s", (name,)):
        db.execute("UPDATE catchment_areas SET code = %s, is_active = true, "
                   "boundary = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) WHERE name = %s",
                   (code, shape, name))
        print(f"{name}: updated")
    else:
        db.execute("INSERT INTO catchment_areas (name, county, code, geom, boundary) VALUES (%s, 'Nairobi', %s, "
                   "ST_PointOnSurface(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), "
                   "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))", (name, code, shape, shape))
        print(f"{name}: inserted")

db.execute("UPDATE catchment_areas SET is_active = false WHERE code IS NULL")
print("other catchments: marked inactive, not deleted")