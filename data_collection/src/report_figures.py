"""
Figures for the Dataset Description in Chapter 5, drawn from the project's own data.
Run from the repository root with the data_collection environment:
    data_collection/.venv/bin/python data_collection/src/report_figures.py
Writes PNG files to reports/figures/chapter5/.
"""
import json
import os

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pysheds.grid import Grid
from shapely import wkb

D = "data_collection/data/"
OUT = "reports/figures/chapter5/"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": "#52514e",
                     "xtick.color": "#52514e", "ytick.color": "#52514e"})
DEM = D + "04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"
NAMES = {"nairobi": "Nairobi River", "mathare": "Mathare", "ngong": "Ngong"}
FILL = {"mathare": "#2a78d6", "nairobi": "#eb6834", "ngong": "#1baf7a"}
RIVER = {"Nairobi River": "#c0392b", "Mathare River": "#1f4e9a", "Ngong River": "#117a55", "Motoine River": "#8e44ad"}


def river_name(tags):
    n = tags.get("name", "").lower()
    if "mathare" in n:
        return "Mathare River"
    if "ngong" in n:
        return "Ngong River"
    if "motoine" in n:
        return "Motoine River"
    return "Nairobi River"


def clean(ax, xlab=True):
    ax.set_xlabel(""); ax.set_ylabel("")
    if xlab:
        ax.set_xlabel("Longitude (degrees)")
        ax.set_ylabel("Latitude (degrees)")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)


grid = Grid.from_raster(DEM)
dem = grid.read_raster(DEM)
flooded = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
acc = np.asarray(grid.accumulation(grid.flowdir(flooded)))
channels = np.where(acc > 1000, 1.0, np.nan)
ext = grid.extent  # (xmin, xmax, ymin, ymax)
catch = gpd.read_file(D + "05_spatial/processed/catchments.geojson")
osm = json.load(open(D + "05_spatial/raw/osm_waterways_nairobi.json"))["elements"]
outlets = pd.read_csv(D + "05_spatial/processed/outlets_snapped.csv")
outlets = outlets[outlets["catchment"] != "motoine"]

# Figure: NASADEM elevation with the catchment boundaries
fig, ax = plt.subplots(figsize=(9, 6.5), dpi=200)
im = ax.imshow(np.asarray(dem), extent=ext, cmap="terrain", vmin=1300, vmax=2500)
catch.boundary.plot(ax=ax, color="black", linewidth=1.2)
cb = fig.colorbar(im, ax=ax, shrink=0.8); cb.set_label("Elevation (m)")
ax.legend(handles=[Line2D([], [], color="black", lw=1.2, label="Catchment boundaries")], loc="lower left", frameon=True)
clean(ax); plt.tight_layout(); plt.savefig(OUT + "fig_nasadem_elevation.png"); plt.close()

# Figure: mapped rivers over the channels derived from the elevation model
fig, ax = plt.subplots(figsize=(10, 6.5), dpi=200)
ax.imshow(np.asarray(dem), extent=ext, cmap="Greys", vmin=1300, vmax=2600)
ax.imshow(channels, extent=ext, cmap=matplotlib.colors.ListedColormap(["#6fa8dc"]), interpolation="nearest")
for e in osm:
    n = river_name(e.get("tags", {}))
    ax.plot([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]], color=RIVER[n], lw=2)
ax.set_xlim(36.6, 37.05); ax.set_ylim(-1.40, -1.10)
ax.legend(handles=[Line2D([], [], color="#6fa8dc", lw=2, label="Channels from the elevation model")] +
          [Line2D([], [], color=c, lw=2, label=f"{n} (OpenStreetMap)") for n, c in RIVER.items()],
          loc="lower right", frameon=True, fontsize=9)
clean(ax); plt.tight_layout(); plt.savefig(OUT + "fig_rivers_vs_channels.png"); plt.close()

# Figure: outlet points on the rivers
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
ax.imshow(np.asarray(dem), extent=ext, cmap="Greys", vmin=1300, vmax=2600)
ax.imshow(channels, extent=ext, cmap=matplotlib.colors.ListedColormap(["#6fa8dc"]), interpolation="nearest")
for e in osm:
    n = river_name(e.get("tags", {}))
    ax.plot([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]], color=RIVER[n], lw=2)
for r in outlets.itertuples():
    ax.scatter(r.lon, r.lat, s=120, color="#ffd23f", edgecolor="black", zorder=5)
    ax.annotate(f"{NAMES[r.catchment]} outlet", (r.lon, r.lat), xytext=(0, 14), textcoords="offset points",
                ha="center", fontsize=10, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#52514e", lw=0.6))
ax.set_xlim(36.75, 37.0); ax.set_ylim(-1.34, -1.20)
ax.legend(handles=[Line2D([], [], marker="o", ls="", markerfacecolor="#ffd23f", markeredgecolor="black", ms=10,
                          label="Outlet point")] +
          [Line2D([], [], color=c, lw=2, label=n) for n, c in RIVER.items()], loc="lower left", fontsize=9)
clean(ax); plt.tight_layout(); plt.savefig(OUT + "fig_outlets.png"); plt.close()

# Figure: the three catchments
fig, ax = plt.subplots(figsize=(9, 6), dpi=200)
for c in ["nairobi", "mathare", "ngong"]:
    catch[catch["catchment"] == c].plot(ax=ax, color=FILL[c], alpha=0.75, edgecolor="white", linewidth=1.5)
for e in osm:
    ax.plot([p["lon"] for p in e["geometry"]], [p["lat"] for p in e["geometry"]], color="#0b0b0b", lw=0.9)
for r in outlets.itertuples():
    ax.scatter(r.lon, r.lat, s=60, color="#ffd23f", edgecolor="black", zorder=5)
areas = dict(zip(catch["catchment"], catch["area_km2"]))
ax.legend(handles=[Patch(color=FILL[c], alpha=0.75, label=f"{NAMES[c]} ({areas[c]:.0f} km²)")
                   for c in ["mathare", "nairobi", "ngong"]] +
          [Line2D([], [], color="#0b0b0b", lw=0.9, label="Mapped rivers"),
           Line2D([], [], marker="o", ls="", markerfacecolor="#ffd23f", markeredgecolor="black", label="Outlets")],
          loc="upper right", fontsize=9)
ax.set_xlim(36.55, 37.0)
clean(ax); plt.tight_layout(); plt.savefig(OUT + "fig_catchments.png"); plt.close()

# Figure: one Groundsource record, its attributes and its outline over the catchments
UUID = "a6abd4c0c29240518023d840e782953e"
g = pd.read_parquet(D + "01_flood_labels/processed/groundsource_candidates.parquet")
rec = g[g["uuid"] == UUID].iloc[0]
shape = wkb.loads(bytes(rec["geometry"]))
coords = list(shape.exterior.coords)
wkt = "POLYGON ((" + ", ".join(f"{x:.4f} {y:.4f}" for x, y in coords[:2]) + ", ...))"
fig = plt.figure(figsize=(12, 4.8), dpi=200)
ax1 = fig.add_axes([0.01, 0.08, 0.50, 0.84]); ax1.axis("off")
rows = [["uuid", rec["uuid"]], ["start_date", rec["start_date"]], ["end_date", rec["end_date"]],
        ["area_km2", f"{rec['area_km2']:.2f}"], ["geometry", wkt]]
t = ax1.table(cellText=rows, colLabels=["Attribute", "Value"], loc="center", cellLoc="left", colWidths=[0.24, 0.76])
t.auto_set_font_size(False); t.set_fontsize(9.5); t.scale(1, 1.9)
for (i, j), cell in t.get_celld().items():
    cell.set_edgecolor("#52514e")
    if i == 0:
        cell.set_facecolor("#d9d9d9"); cell.set_text_props(weight="bold")
ax2 = fig.add_axes([0.60, 0.12, 0.38, 0.80])
for c in ["nairobi", "mathare", "ngong"]:
    catch[catch["catchment"] == c].plot(ax=ax2, color=FILL[c], alpha=0.35, edgecolor="white")
gpd.GeoSeries([shape]).plot(ax=ax2, facecolor="#d62728", edgecolor="#7a0f10", alpha=0.85)
minx, miny, maxx, maxy = shape.bounds
pad = 0.06
ax2.set_xlim(minx - pad, maxx + pad); ax2.set_ylim(miny - pad, maxy + pad)
ax2.legend(handles=[Patch(color="#d62728", label="Reported flood area"),
                    Patch(color=FILL["mathare"], alpha=0.35, label="Mathare catchment"),
                    Patch(color=FILL["nairobi"], alpha=0.35, label="Nairobi River catchment"),
                    Patch(color=FILL["ngong"], alpha=0.35, label="Ngong catchment")],
           loc="lower left", fontsize=8)
ax2.tick_params(labelsize=8); clean(ax2)
ax2.set_xlabel("Longitude (degrees)", fontsize=9); ax2.set_ylabel("Latitude (degrees)", fontsize=9)
plt.savefig(OUT + "fig_groundsource_record.png"); plt.close()
print("written to", OUT)
