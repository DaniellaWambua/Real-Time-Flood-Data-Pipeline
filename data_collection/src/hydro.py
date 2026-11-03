from pysheds.grid import Grid

DEM = "data_collection/data/04_environmental/raw/nasadem/nasadem_nairobi_bbox.tif"

def compute_flow():
    grid = Grid.from_raster(DEM)
    dem = grid.read_raster(DEM)
    inflated = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)
    return grid, fdir, acc