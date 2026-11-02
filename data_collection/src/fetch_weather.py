import ee, json, sys
import geopandas as gpd
import pandas as pd

ee.Initialize(project="flood-pipeline-nairobi")

CATCH = "data_collection/data/05_spatial/processed/catchments.geojson"
OUT = "data_collection/data/02_weather/processed/"

gdf = gpd.read_file(CATCH).to_crs(4326)[["catchment", "geometry"]]
fc = ee.FeatureCollection(json.loads(gdf.to_json())["features"])

SETS = {
    "chirps": dict(id="UCSB-CHG/CHIRPS/DAILY", bands=["precipitation"], scale=5566),
    "era5land": dict(
        id="ECMWF/ERA5_LAND/DAILY_AGGR",
        bands=["total_precipitation_sum", "temperature_2m", "dewpoint_temperature_2m",
               "surface_pressure", "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2"],
        scale=11132),
}

def extract(name, year):
    cfg = SETS[name]
    col = (ee.ImageCollection(cfg["id"])
           .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
           .select(cfg["bands"]))

    def per_image(img):
        stats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=cfg["scale"])
        date = img.date().format("YYYY-MM-dd")
        return stats.map(lambda f: f.set("date", date))

    rows = col.map(per_image).flatten().getInfo()["features"]
    df = pd.DataFrame([r["properties"] for r in rows])
    if "mean" in df.columns:
        df = df.rename(columns={"mean": cfg["bands"][0]})
    return df

name, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
frames = []
for y in range(start, end + 1):
    frames.append(extract(name, y))
    print(name, y, len(frames[-1]), "rows", flush=True)

df = pd.concat(frames).sort_values(["catchment", "date"])
df.to_csv(f"{OUT}{name}_daily_{start}_{end}.csv", index=False)
print(df.groupby("catchment").size())