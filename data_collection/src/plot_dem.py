import rasterio
import matplotlib.pyplot as plt

path = "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"
out = "data_collection/data/04_environmental/processed/dem_overview.png"

with rasterio.open(path) as src:
    band = src.read(1, masked=True)
    b = src.bounds
    extent = (b.left, b.right, b.bottom, b.top)

plt.imshow(band, extent=extent, cmap="terrain")
plt.colorbar(label="Elevation (m)")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.savefig(out, dpi=150)