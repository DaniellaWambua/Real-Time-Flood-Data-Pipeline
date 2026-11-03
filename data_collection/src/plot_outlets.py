import csv
import json
import numpy as np
import matplotlib.pyplot as plt
from hydro import compute_flow

osm_path = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"
pts_path = "data_collection/data/05_spatial/processed/outlets_snapped.csv"
out = "data_collection/data/05_spatial/processed/outlets_check.png"

grid, fdir, acc = compute_flow()
acc_arr = np.asarray(acc)
streams = np.where(acc_arr > 1000, 1, np.nan)

with open(osm_path) as f:
    osm = json.load(f)

plt.figure(figsize=(14, 10))
plt.imshow(np.asarray(grid.read_raster(
    "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif")),
    extent=grid.extent, cmap="Greys")
plt.imshow(streams, extent=grid.extent, cmap="winter", interpolation="nearest")

for e in osm["elements"]:
    plt.plot([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]],
             color="red", linewidth=1.5)

with open(pts_path) as f:
    for r in csv.DictReader(f):
        plt.scatter(float(r["lon"]), float(r["lat"]), color="yellow", edgecolor="black", s=80, zorder=5)
        plt.text(float(r["lon"]), float(r["lat"]), r["catchment"], fontsize=11)

plt.xlim(36.75, 37.0)
plt.ylim(-1.34, -1.2)
plt.savefig(out, dpi=150)