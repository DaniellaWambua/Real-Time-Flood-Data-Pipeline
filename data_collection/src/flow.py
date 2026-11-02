import numpy as np
import matplotlib.pyplot as plt
from pysheds.grid import Grid

path = "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"
out = "data_collection/data/05_spatial/processed/flow_streams.png"

grid = Grid.from_raster(path)
dem = grid.read_raster(path)

pit_filled = grid.fill_pits(dem)
flooded = grid.fill_depressions(pit_filled)
inflated = grid.resolve_flats(flooded)

fdir = grid.flowdir(inflated)
acc = grid.accumulation(fdir)

acc_arr = np.asarray(acc)
streams = np.where(acc_arr > 1000, np.log10(acc_arr + 1), np.nan)
print("stream cells", np.isfinite(streams).sum())

plt.figure(figsize=(16, 13))
plt.imshow(dem, extent=grid.extent, cmap="Greys")
plt.imshow(streams, extent=grid.extent, cmap="winter", interpolation="nearest")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.savefig(out, dpi=150)