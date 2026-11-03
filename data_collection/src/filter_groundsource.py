import glob
import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
import shapely

src = glob.glob("data_collection/data/01_flood_labels/raw/groundsource/*.parquet")[0]
catch_path = "data_collection/data/05_spatial/processed/catchments.geojson"
out = "data_collection/data/01_flood_labels/processed/groundsource_candidates.parquet"

region = gpd.read_file(catch_path).geometry.union_all()
shapely.prepare(region)

pf = pq.ParquetFile(src)
cols = ["uuid", "area_km2", "geometry", "start_date", "end_date"]
kept, total = [], 0

for batch in pf.iter_batches(batch_size=200_000, columns=cols):
    df = batch.to_pandas()
    total += len(df)
    geoms = shapely.from_wkb(df["geometry"].values)
    hit = shapely.intersects(geoms, region)
    if hit.any():
        sub = df[hit].copy()
        sub["geometry"] = geoms[hit]
        kept.append(sub)
    print("read", total, "kept", sum(len(k) for k in kept))

result = gpd.GeoDataFrame(pd.concat(kept), geometry="geometry", crs="EPSG:4326")
result.to_parquet(out)

print(len(result), "candidate events")
print(result["area_km2"].describe())
print(result["start_date"].str[:4].value_counts().sort_index())