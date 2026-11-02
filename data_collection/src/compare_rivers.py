import json
import numpy as np
import matplotlib.pyplot as plt
from pysheds.grid import Grid

dem_path = "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"
osm_path = "data_collection/data/05_spatial/raw/osm_waterways_nairobi.json"
out = "data_collection/data/05_spatial/processed/osm_vs_dem_streams.png"

grid = Grid.from_raster(dem_path)
dem = grid.read_raster(dem_path)
inflated = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
fdir = grid.flowdir(inflated)
acc = np.asarray(grid.accumulation(fdir))
streams = np.where(acc > 1000, 1, np.nan)

with open(osm_path) as f:
    osm = json.load(f)

colours = {"nairobi": "red", "mathare": "orange", "ngong": "magenta", "motoine": "black"}

def key(name):
    return name.lower().replace("mto ", "").replace(" river", "").strip()

plt.figure(figsize=(14, 11))
plt.imshow(dem, extent=grid.extent, cmap="Greys")
plt.imshow(streams, extent=grid.extent, cmap="winter", interpolation="nearest")

for e in osm["elements"]:
    name = key(e["tags"]["name"])
    xs = [p["lon"] for p in e["geometry"]]
    ys = [p["lat"] for p in e["geometry"]]
    plt.plot(xs, ys, color=colours[name], linewidth=1.5)

plt.xlim(36.6, 37.1)
plt.ylim(-1.45, -1.1)
plt.savefig(out, dpi=150)