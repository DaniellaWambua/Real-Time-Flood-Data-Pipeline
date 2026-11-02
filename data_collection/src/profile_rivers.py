import json
import numpy as np
import rasterio
from hydro import compute_flow, DEM

osm_path = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"
R = 3

def key(name):
    return name.lower().replace("mto ", "").replace(" river", "").strip()

grid, fdir, acc = compute_flow()
acc_arr = np.asarray(acc)

with open(osm_path) as f:
    osm = json.load(f)

points = {}
for e in osm["elements"]:
    points.setdefault(key(e["tags"]["name"]), []).extend(e["geometry"])

with rasterio.open(DEM) as src:
    for name in ["motoine", "ngong", "mathare", "nairobi"]:
        pts = sorted(points[name], key=lambda p: p["lon"])
        step = max(1, len(pts) // 15)
        print(name)
        for p in pts[::step]:
            row, col = src.index(p["lon"], p["lat"])
            w = acc_arr[row - R:row + R + 1, col - R:col + R + 1]
            print("  lon", round(p["lon"], 3), "cells", int(w.max()))