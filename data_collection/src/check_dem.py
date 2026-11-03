import rasterio

path = "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"

with rasterio.open(path) as src:
    print("CRS", src.crs)
    print("Cell size", src.res)
    print("Bounds", src.bounds)
    print("Shape", src.shape)
    print("Nodata", src.nodata)
    band = src.read(1, masked=True)
    print("Min, max, mean", band.min(), band.max(), band.mean())