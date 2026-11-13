"""
Would ERA5-Land hourly, summed or averaged into days here, give the same values as the ERA5-Land daily
dataset the models were trained on? Hourly runs about 3 days ahead of daily, so if it matches, the fast
model could score a day about 5 days after it happens instead of about 8.

Compares the last 20 days both datasets cover, for each catchment, band by band, as the producer reads
them (catchment means at the same scale). Days run 00:00 to 24:00 UTC, as in the daily dataset.

Usage (from the project folder, in the data_collection environment):
    python ingestion/check_era5_hourly.py
"""
from datetime import datetime, timedelta, timezone

import config
import earth_engine

DAYS = 20
SUMMED = {"total_precipitation_sum": "total_precipitation_hourly"}
AVERAGED = ["temperature_2m", "dewpoint_temperature_2m", "surface_pressure",
            "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2"]

ee = earth_engine.connect()
fc = earth_engine._catchments(ee)
now = ee.Date(datetime.now(timezone.utc).timestamp() * 1000)
last_ms = ee.ImageCollection(earth_engine.ERA5).filterDate(now.advance(-60, "day"), now) \
    .aggregate_max("system:time_start").getInfo()
last = datetime.fromtimestamp(last_ms / 1000, timezone.utc).date()
first = last - timedelta(days=DAYS - 1)
hourly = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")


def from_hourly(day):
    start = ee.Date(day.isoformat())
    hours = hourly.filterDate(start, start.advance(1, "day"))
    img = hours.select(AVERAGED).mean()
    for daily_band, hourly_band in SUMMED.items():
        img = img.addBands(hours.select(hourly_band).sum().rename(daily_band))
    return img


worst = {b: 0.0 for b in list(SUMMED) + AVERAGED}
compared = 0
for i in range(DAYS):
    day = first + timedelta(days=i)
    daily = ee.ImageCollection(earth_engine.ERA5).filterDate(day.isoformat(), (day + timedelta(days=1)).isoformat()) \
        .first().select(list(SUMMED) + AVERAGED)
    a = daily.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132).getInfo()["features"]
    b = from_hourly(day).reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132).getInfo()["features"]
    by_catchment = {f["properties"]["catchment"]: f["properties"] for f in b}
    for f in a:
        pa, pb = f["properties"], by_catchment[f["properties"]["catchment"]]
        compared += 1
        for band in worst:
            if pa.get(band) is not None and pb.get(band) is not None:
                worst[band] = max(worst[band], abs(pa[band] - pb[band]))

print(f"{compared} catchment-days compared, {first} to {last}")
print("largest difference, daily dataset minus hourly summed or averaged:")
units = {"total_precipitation_sum": ("mm", 1000), "surface_pressure": ("hPa", 0.01)}
for band, diff in worst.items():
    unit, factor = units.get(band, ("", 1))
    print(f"  {band:32} {diff * factor:.4f} {unit}")
print("\nIf rainfall differs by well under 1 mm and the rest by about rounding, hourly can replace daily.")
