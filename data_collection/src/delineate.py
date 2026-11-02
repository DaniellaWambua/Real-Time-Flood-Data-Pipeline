import csv
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import rasterio
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union
from hydro import compute_flow, DEM

pts_path = "data_collection/data/05_spatial/processed/outlets_snapped.csv"
out_geojson = "data_collection/data/05_spatial/processed/catchments.geojson"
out_png = "data_collection/data/05_spatial/processed/catchments.png"

grid, fdir, acc = compute_flow()

outlets = {}
with open(pts_path) as f:
    for r in csv.DictReader(f):
        outlets[r["catchment"]] = (float(r["lon"]), float(r["lat"]))

full = {}
acc_arr = np.asarray(acc)
with rasterio.open(DEM) as src:
    for name, (lon, lat) in outlets.items():
        row, col = src.index(lon, lat)
        c = grid.catchment(x=col, y=row, fdir=fdir, xytype="index")
        full[name] = np.asarray(c).astype(bool)
        print(name, "catchment cells", int(full[name].sum()), "accumulation cells", int(acc_arr[row, col]))

exclusive = {
    "ngong": full["ngong"],
    "mathare": full["mathare"],
    "nairobi": full["nairobi"] & ~full["mathare"] & ~full["ngong"],
}

rows, geoms = [], []
with rasterio.open(DEM) as src:
    for name, mask in exclusive.items():
        shapes = features.shapes(mask.astype("uint8"), mask=mask, transform=src.transform)
        geoms.append(unary_union([shape(g) for g, v in shapes]))
        rows.append({"catchment": name, "cells": int(mask.sum())})

gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
gdf["area_km2"] = gdf.to_crs(epsg=32737).area / 1e6
gdf.to_file(out_geojson, driver="GeoJSON")
print(gdf[["catchment", "cells", "area_km2"]])

gdf.plot(column="catchment", legend=True, alpha=0.6)
plt.savefig(out_png, dpi=150)