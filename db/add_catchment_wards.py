"""
Loads the ward boundaries in db/reference/wards_nairobi_area.geojson and records,
for each active catchment, the wards that lie mostly inside it, largest overlap first.
Also works on a fresh database after migrate_final_catchments.py. Safe to run more than once.
Run from the db/ directory: python add_catchment_wards.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

WARDS_FILE = Path(__file__).resolve().parent / "reference" / "wards_nairobi_area.geojson"
MIN_SHARE = 0.25  # a ward is listed when at least a quarter of its area lies in the catchment

db.execute("ALTER TABLE catchment_areas ADD COLUMN IF NOT EXISTS wards TEXT[]")
db.execute("CREATE TABLE IF NOT EXISTS wards (id SERIAL PRIMARY KEY, name TEXT NOT NULL, "
           "boundary GEOMETRY(MultiPolygon, 4326) NOT NULL)")
db.execute("CREATE INDEX IF NOT EXISTS idx_wards_boundary ON wards USING GIST (boundary)")

db.execute("DELETE FROM wards")
features = json.loads(WARDS_FILE.read_text())["features"]
for f in features:
    db.execute("INSERT INTO wards (name, boundary) VALUES "
               "(%s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)))",
               (f["properties"]["ward"], json.dumps(f["geometry"])))
print(f"wards loaded: {len(features)}")

db.execute("""
UPDATE catchment_areas ca SET wards = sub.names FROM (
    SELECT c.id, array_agg(w.name ORDER BY ST_Area(ST_Intersection(w.boundary, ST_MakeValid(c.boundary))::geography) DESC) AS names
    FROM catchment_areas c JOIN wards w ON ST_Intersects(w.boundary, ST_MakeValid(c.boundary))
    WHERE c.is_active AND c.boundary IS NOT NULL
      AND ST_Area(ST_Intersection(w.boundary, ST_MakeValid(c.boundary))::geography) >= %s * ST_Area(w.boundary::geography)
    GROUP BY c.id
) sub WHERE ca.id = sub.id
""", (MIN_SHARE,))
for row in db.query_all("SELECT name, wards FROM catchment_areas WHERE is_active ORDER BY name"):
    print(f"{row['name']}: {', '.join(row['wards'] or []) or 'no wards'}")
