"""
Downloads Open-Meteo forecasts for the three catchments, as a live system would have seen them,
for the forecast test (forecast_test.py).

  lead 0  Historical Forecast API, 2022-2025 (2022-2023 only used to match values to the training data)
  lead 1  Previous Runs API, 2024-2025: each day as forecast one day earlier
  lead 2  the same, two days earlier

Each catchment averages up to four grid points inside its boundary; hourly values become UTC days.

Run from the project folder (needs internet, about 20 minutes):
    python data_collection/src/fetch_forecast_archive.py
Writes data_collection/data/02_weather/processed/openmeteo_forecast_archive_2022_2025.csv
"""
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATCHMENTS = ROOT / "data_collection/data/05_spatial/processed/catchments.geojson"
OUT = ROOT / "data_collection/data/02_weather/processed/openmeteo_forecast_archive_2022_2025.csv"
HISTORICAL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREVIOUS = "https://previous-runs-api.open-meteo.com/v1/forecast"
VARIABLES = ["precipitation", "temperature_2m", "dew_point_2m", "surface_pressure",
             "soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm",  # ECMWF-style layers, as in ERA5-Land
             "soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm", "soil_moisture_3_to_9cm",
             "soil_moisture_9_to_27cm"]  # other models' layers, used when the first two are missing
POINTS_PER_CATCHMENT = 4
GRID = 0.05  # degrees between candidate points
PAUSE = 8  # seconds between requests


def inside(lon, lat, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def sample_points():
    """{catchment: [(lat, lon), ...]} up to POINTS_PER_CATCHMENT grid points inside each boundary."""
    out = {}
    for f in json.load(open(CATCHMENTS))["features"]:
        code, geom = f["properties"]["catchment"], f["geometry"]
        rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for p in geom["coordinates"] for r in p]
        outer, holes = rings[0], rings[1:]
        xs, ys = [p[0] for p in outer], [p[1] for p in outer]
        pts = []
        lat = math.floor(min(ys) / GRID) * GRID
        while lat <= max(ys):
            lon = math.floor(min(xs) / GRID) * GRID
            while lon <= max(xs):
                if inside(lon, lat, outer) and not any(inside(lon, lat, h) for h in holes):
                    pts.append((round(lat, 4), round(lon, 4)))
                lon += GRID
            lat += GRID
        if not pts:  # very small shape: its average vertex
            pts = [(round(sum(ys) / len(ys), 4), round(sum(xs) / len(xs), 4))]
        step = max(1, len(pts) // POINTS_PER_CATCHMENT)
        out[code] = pts[::step][:POINTS_PER_CATCHMENT]
    return out


def get(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(full, timeout=180) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if e.code == 429 or e.code >= 500:
                wait = 60 * (attempt + 1)
                print(f"  {e.code}, waiting {wait} s: {body}")
                time.sleep(wait)
                continue
            sys.exit(f"request refused ({e.code}): {body}")
        except urllib.error.URLError as e:
            print(f"  network error {e.reason}, retrying")
            time.sleep(30)
    sys.exit("gave up after repeated failures")


def fetch(url, points, start, end, suffix=""):
    """{(catchment, point index): {variable: [hourly values]}, 'time': [...]} for one period."""
    flat = [(c, i, p) for c, pts in points.items() for i, p in enumerate(pts)]
    hourly = [v + suffix for v in VARIABLES]
    reply = get(url, {"latitude": ",".join(str(p[0]) for _, _, p in flat),
                      "longitude": ",".join(str(p[1]) for _, _, p in flat),
                      "hourly": ",".join(hourly), "start_date": start.isoformat(), "end_date": end.isoformat(),
                      "timezone": "GMT"})
    replies = reply if isinstance(reply, list) else [reply]
    out = {}
    for (c, i, _), r in zip(flat, replies):
        h = r["hourly"]
        out[(c, i)] = {"time": h["time"], **{v: h.get(v + suffix) for v in VARIABLES}}
    return out


def periods(first, last, months=6):
    start = first
    while start <= last:
        end = min(date(start.year + (start.month - 1 + months) // 12, (start.month - 1 + months) % 12 + 1, 1)
                  - timedelta(days=1), last)
        yield start, end
        start = end + timedelta(days=1)


def daily(series):
    """Hourly values of one point -> {day: features}, with UTC days as in the training data."""
    by_day = defaultdict(lambda: defaultdict(list))
    for k, t in enumerate(series["time"]):
        day = t[:10]
        for v in VARIABLES:
            values = series.get(v)
            if values is not None and values[k] is not None:
                by_day[day][v].append(values[k])
    out = {}
    for day, vals in by_day.items():
        if len(vals["precipitation"]) < 24 or len(vals["temperature_2m"]) < 24:
            continue  # incomplete day
        mean = lambda v: sum(vals[v]) / len(vals[v]) if vals[v] else None  # noqa: E731
        p = vals["precipitation"]
        soil_1, soil_2 = mean("soil_moisture_0_to_7cm"), mean("soil_moisture_7_to_28cm")
        layers = {k: mean(f"soil_moisture_{k}") for k in ("0_to_1cm", "1_to_3cm", "3_to_9cm", "9_to_27cm")}
        if soil_1 is None and None not in layers.values():  # depth-weighted onto 0-7 and 7-28 cm
            soil_1 = (layers["0_to_1cm"] * 1 + layers["1_to_3cm"] * 2 + layers["3_to_9cm"] * 4) / 7
            soil_2 = (layers["3_to_9cm"] * 2 + layers["9_to_27cm"] * 19) / 21
        t, td = mean("temperature_2m"), mean("dew_point_2m")
        out[day] = {"era5_rain_mm": sum(p), "temp_c": t, "dewpoint_depression": None if td is None else t - td,
                    "pressure_hpa": mean("surface_pressure"), "soil_1": soil_1, "soil_2": soil_2,
                    "fc_max_rate": max(p), "fc_total_mm": sum(p), "fc_hours_ge5": sum(1 for x in p if x >= 5)}
    return out


def main():
    points = sample_points()
    for c, pts in points.items():
        print(f"{c}: {len(pts)} points {pts}")
    rows = {}
    jobs = [(0, HISTORICAL, "", date(2022, 1, 1), date(2025, 12, 31))] + \
           [(lead, PREVIOUS, f"_previous_day{lead}", date(2024, 1, 1), date(2025, 12, 31)) for lead in (1, 2)]
    available = defaultdict(set)
    for lead, url, suffix, first, last in jobs:
        for start, end in periods(first, last):
            print(f"lead {lead}: {start} to {end}", flush=True)
            data = fetch(url, points, start, end, suffix)
            per_catchment = defaultdict(list)
            for (c, _), series in data.items():
                for v in VARIABLES:
                    if series.get(v) and any(x is not None for x in series[v]):
                        available[lead].add(v)
                per_catchment[c].append(daily(series))
            for c, dailies in per_catchment.items():
                for day in sorted(set().union(*dailies)):
                    vals = [d[day] for d in dailies if day in d]
                    row = {"date": day, "catchment": c, "lead": lead, "points": len(vals)}
                    for k in vals[0]:
                        xs = [v[k] for v in vals if v[k] is not None]
                        row[k] = sum(xs) / len(xs) if xs else None
                    rows[(day, c, lead)] = row
            time.sleep(PAUSE)
    cols = ["date", "catchment", "lead", "points", "era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa",
            "soil_1", "soil_2", "fc_max_rate", "fc_total_mm", "fc_hours_ge5"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        f.write(",".join(cols) + "\n")
        for key in sorted(rows):
            r = rows[key]
            f.write(",".join("" if r.get(c) is None else (f"{r[c]:.5g}" if isinstance(r[c], float) else str(r[c]))
                             for c in cols) + "\n")
    print(f"\nwrote {len(rows)} catchment-days to {OUT}")
    for lead in sorted(available):
        missing = [v for v in VARIABLES if v not in available[lead]]
        print(f"lead {lead}: variables with data {sorted(available[lead])}; none returned for {missing}")
    print(f"finished {datetime.now():%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main()
