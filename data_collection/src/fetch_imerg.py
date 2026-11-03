import ee, json, sys, time, calendar
import geopandas as gpd
import pandas as pd

ee.Initialize(project="flood-pipeline-nairobi")

CATCH = "data_collection/data/05_spatial/processed/catchments.geojson"
OUT = "data_collection/data/02_weather/processed/"

gdf = gpd.read_file(CATCH).to_crs(4326)[["catchment", "geometry"]]
fc = ee.FeatureCollection(json.loads(gdf.to_json())["features"])
col = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").select("precipitation")

def month_rows(year, month):
    ndays = calendar.monthrange(year, month)[1]
    first = ee.Date(f"{year}-{month:02d}-01")

    def day_image(offset):
        start = first.advance(ee.Number(offset), "day")
        day = col.filterDate(start, start.advance(1, "day"))
        peak = day.max().rename("imerg_max_rate")
        total = day.sum().multiply(0.5).rename("imerg_total_mm")
        hours5 = day.map(lambda im: im.gte(5)).sum().multiply(0.5).rename("imerg_hours_ge5")
        return peak.addBands(total).addBands(hours5)

    stack = ee.ImageCollection.fromImages(ee.List.sequence(0, ndays - 1).map(day_image)).toBands()
    feats = stack.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132).getInfo()["features"]

    rows = []
    for f in feats:
        p = f["properties"]
        for i in range(ndays):
            rows.append({
                "catchment": p["catchment"],
                "date": (pd.Timestamp(year, month, 1) + pd.Timedelta(days=i)).date(),
                "imerg_max_rate": p[f"{i}_imerg_max_rate"],
                "imerg_total_mm": p[f"{i}_imerg_total_mm"],
                "imerg_hours_ge5": p[f"{i}_imerg_hours_ge5"],
            })
    return pd.DataFrame(rows)

start_y, end_y = int(sys.argv[1]), int(sys.argv[2])
frames = []
for y in range(start_y, end_y + 1):
    for m in range(1, 13):
        for attempt in range(3):
            try:
                df = month_rows(y, m)
                break
            except Exception as e:
                print("retry", y, m, str(e)[:80], flush=True)
                time.sleep(10)
        else:
            raise SystemExit(f"failed {y}-{m}")
        frames.append(df)
        print(y, m, len(df), "rows", flush=True)

out = pd.concat(frames).sort_values(["catchment", "date"])
out.to_csv(f"{OUT}imerg_daily_{start_y}_{end_y}.csv", index=False)
print(out.groupby("catchment").size())