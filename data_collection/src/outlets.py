import csv
import json
import math

osm_path = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"
out = "data_collection/data/05_spatial/processed/outlets.csv"

def key(name):
    return name.lower().replace("mto ", "").replace(" river", "").strip()

def metres(a, b):
    dx = (a["lon"] - b["lon"]) * 111320 * math.cos(math.radians(a["lat"]))
    dy = (a["lat"] - b["lat"]) * 110540
    return math.hypot(dx, dy)

with open(osm_path) as f:
    osm = json.load(f)

points = {}
for e in osm["elements"]:
    points.setdefault(key(e["tags"]["name"]), []).extend(e["geometry"])

for name in points:
    points[name].sort(key=lambda p: p["lon"])

outlets = {}

for name in ["motoine"]:
    pts = points[name]
    end = pts[-1]
    for p in reversed(pts):
        if metres(p, end) >= 500:
            outlets[name] = p
            break

chosen_lon = {"mathare": 36.880, "ngong": 36.941}
for name, lon in chosen_lon.items():
    outlets[name] = min(points[name], key=lambda p: abs(p["lon"] - lon))

ngong_end = points["ngong"][-1]
nairobi = points["nairobi"]
start = min(nairobi, key=lambda p: metres(p, ngong_end))
for p in nairobi:
    if p["lon"] > start["lon"] and metres(p, start) >= 500:
        outlets["nairobi"] = p
        break

with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["catchment", "lat", "lon"])
    for name in ["motoine", "ngong", "mathare", "nairobi"]:
        w.writerow([name, outlets[name]["lat"], outlets[name]["lon"]])
        print(name, outlets[name]["lat"], outlets[name]["lon"])