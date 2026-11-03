import json

osm_path = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"

def key(name):
    return name.lower().replace("mto ", "").replace(" river", "").strip()

with open(osm_path) as f:
    osm = json.load(f)

east, west = {}, {}
for e in osm["elements"]:
    name = key(e["tags"]["name"])
    for p in e["geometry"]:
        if name not in east or p["lon"] > east[name]["lon"]:
            east[name] = p
        if name not in west or p["lon"] < west[name]["lon"]:
            west[name] = p

for name in sorted(east):
    print(name, "west end", west[name], "east end", east[name])