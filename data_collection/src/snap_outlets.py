import csv
import math
import numpy as np
import rasterio
from hydro import compute_flow, DEM

src_csv = "data_collection/data/05_spatial/processed/outlets.csv"
out_csv = "data_collection/data/05_spatial/processed/outlets_snapped.csv"
RADIUS = 3

grid, fdir, acc = compute_flow()
acc_arr = np.asarray(acc)

with rasterio.open(DEM) as src, open(src_csv) as fin, open(out_csv, "w", newline="") as fout:
    writer = csv.writer(fout)
    writer.writerow(["catchment", "lat", "lon", "acc_cells", "shift_m"])
    for r in csv.DictReader(fin):
        lat, lon = float(r["lat"]), float(r["lon"])
        row, col = src.index(lon, lat)
        r0, c0 = row - RADIUS, col - RADIUS
        window = acc_arr[r0:row + RADIUS + 1, c0:col + RADIUS + 1]
        dr, dc = np.unravel_index(np.argmax(window), window.shape)
        new_lon, new_lat = src.xy(r0 + dr, c0 + dc)
        dx = (new_lon - lon) * 111320 * math.cos(math.radians(lat))
        dy = (new_lat - lat) * 110540
        shift = round(math.hypot(dx, dy))
        cells = int(acc_arr[r0 + dr, c0 + dc])
        writer.writerow([r["catchment"], new_lat, new_lon, cells, shift])
        print(r["catchment"], new_lat, new_lon, "cells", cells, "shift_m", shift)