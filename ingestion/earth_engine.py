"""
Live daily readings from Google Earth Engine.

Computed exactly as the training data was (data_collection/src/fetch_weather.py,
fetch_imerg.py and build_features.py): the same collections, catchment shapes,
scales and unit conversions, so the model receives what it was trained on.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import config

CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
ERA5 = "ECMWF/ERA5_LAND/DAILY_AGGR"
IMERG = "NASA/GPM_L3/IMERG_V07"
ERA5_BANDS = ["total_precipitation_sum", "temperature_2m", "dewpoint_temperature_2m",
              "surface_pressure", "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2"]

_ee = None


def connect():
    """Sign in to Earth Engine once: a service account key on the server, your own login locally."""
    global _ee
    if _ee is None:
        import ee
        key_file = os.environ.get("EE_SERVICE_ACCOUNT_KEY")
        if key_file:
            email = json.load(open(key_file))["client_email"]
            ee.Initialize(ee.ServiceAccountCredentials(email, key_file), project=config.EE_PROJECT)
        else:
            ee.Initialize(project=config.EE_PROJECT)
        _ee = ee
    return _ee


def _catchments(ee):
    features = json.load(open(config.CATCHMENTS_FILE))["features"]
    return ee.FeatureCollection([
        {"type": "Feature", "geometry": f["geometry"], "properties": {"catchment": f["properties"]["catchment"]}}
        for f in features])


def latest_complete_day(dataset, newest_ms):
    """The last whole day a dataset covers, from its newest image's start time."""
    newest = datetime.fromtimestamp(newest_ms / 1000, timezone.utc)
    if dataset == "imerg":  # half-hourly images: a day is complete once its 23:30 image exists
        return (newest + timedelta(minutes=30)).date() - timedelta(days=1)
    return newest.date()  # CHIRPS and ERA5-Land: one image per whole day


def latest_days():
    """{'chirps': date, 'imerg': date, 'era5': date}, the last complete day of each."""
    ee = connect()
    now = ee.Date(datetime.now(timezone.utc).timestamp() * 1000)
    since = now.advance(-400, "day")
    out = {}
    for name, cid in (("chirps", CHIRPS), ("imerg", IMERG), ("era5", ERA5)):
        ms = ee.ImageCollection(cid).filterDate(since, now).aggregate_max("system:time_start").getInfo()
        if ms is None:
            raise RuntimeError(f"{cid} has no images in the last 400 days")
        out[name] = latest_complete_day(name, ms)
    return out


def _num(props, key):
    value = props.get(key)
    return None if value is None else float(value)


def to_reading(chirps, era5, imerg):
    """The model's ten readings from one catchment-day's raw values, converted as in build_features.py.
    A missing raw value gives None, which the consumer rejects and logs."""
    rain, tp = _num(chirps, "precipitation"), _num(era5, "total_precipitation_sum")
    t, td = _num(era5, "temperature_2m"), _num(era5, "dewpoint_temperature_2m")
    sp = _num(era5, "surface_pressure")
    return {
        "rain_mm": None if rain is None else max(rain, 0.0),
        "imerg_max_rate": _num(imerg, "imerg_max_rate"),
        "imerg_total_mm": _num(imerg, "imerg_total_mm"),
        "imerg_hours_ge5": _num(imerg, "imerg_hours_ge5"),
        "era5_rain_mm": None if tp is None else max(tp, 0.0) * 1000,
        "soil_1": _num(era5, "volumetric_soil_water_layer_1"),
        "soil_2": _num(era5, "volumetric_soil_water_layer_2"),
        "temp_c": None if t is None else t - 273.15,
        "dewpoint_depression": None if t is None or td is None else t - td,
        "pressure_hpa": None if sp is None else sp / 100,
    }


def fetch(start, end):
    """Rows of {'date', 'catchment' (code), 'readings'} for every catchment and day from start to end."""
    ee = connect()
    fc = _catchments(ee)
    stop = (end + timedelta(days=1)).isoformat()

    def daily(cid, bands, scale):
        col = ee.ImageCollection(cid).filterDate(start.isoformat(), stop).select(bands)

        def per_image(img):
            stats = img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=scale)
            day = img.date().format("YYYY-MM-dd")
            return stats.map(lambda f: f.set("date", day))

        out = {}
        for feature in col.map(per_image).flatten().getInfo()["features"]:
            p = feature["properties"]
            if "mean" in p:  # a single band comes back as 'mean'
                p[bands[0]] = p.pop("mean")
            out[(p["catchment"], p["date"])] = p
        return out

    chirps = daily(CHIRPS, ["precipitation"], 5566)
    era5 = daily(ERA5, ERA5_BANDS, 11132)

    # IMERG: half-hourly rates summarised per day, as in fetch_imerg.py
    col = ee.ImageCollection(IMERG).select("precipitation")
    ndays = (end - start).days + 1
    first = ee.Date(start.isoformat())

    def day_image(offset):
        s = first.advance(ee.Number(offset), "day")
        day = col.filterDate(s, s.advance(1, "day"))
        peak = day.max().rename("imerg_max_rate")
        total = day.sum().multiply(0.5).rename("imerg_total_mm")
        hours5 = day.map(lambda im: im.gte(5)).sum().multiply(0.5).rename("imerg_hours_ge5")
        return peak.addBands(total).addBands(hours5)

    stack = ee.ImageCollection.fromImages(ee.List.sequence(0, ndays - 1).map(day_image)).toBands()
    imerg = {}
    for feature in stack.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=11132).getInfo()["features"]:
        p = feature["properties"]
        for i in range(ndays):
            day = (start + timedelta(days=i)).isoformat()
            imerg[(p["catchment"], day)] = {k: p.get(f"{i}_{k}") for k in
                                            ("imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5")}

    rows = []
    for i in range(ndays):
        day = (start + timedelta(days=i)).isoformat()
        for code in config.CATCHMENT_NAMES:
            key = (code, day)
            rows.append({"date": day, "catchment": code,
                         "readings": to_reading(chirps.get(key, {}), era5.get(key, {}), imerg.get(key, {}))})
    return rows
