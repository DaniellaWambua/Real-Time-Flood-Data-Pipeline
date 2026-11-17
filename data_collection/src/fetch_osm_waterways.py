import json
import requests

url = "https://overpass-api.de/api/interpreter"
query = """
[out:json][timeout:90];
way["waterway"]["name"~"Nairobi|Mathare|Ngong|Motoine",i](-1.55,36.55,-1.00,37.20);
out geom;
"""
out = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"

headers = {
    "User-Agent": "nairobi-flood-data-capstone/0.1 (student project, nairobifloodsews@gmail.com)",
    "Accept": "*/*",
}

resp = requests.post(url, data={"data": query}, headers=headers, timeout=120)
resp.raise_for_status()
data = resp.json()

with open(out, "w") as f:
    json.dump(data, f)

print("segments", len(data["elements"]))
print(sorted({e["tags"].get("name", "") for e in data["elements"]}))