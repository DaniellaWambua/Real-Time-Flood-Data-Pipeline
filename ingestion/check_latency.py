"""
How far behind today each Earth Engine dataset runs.

The live producer can only score a day once all three training datasets
(CHIRPS, IMERG, ERA5-Land) have published it, so the slowest one sets the lag.
A few faster alternatives are checked too, for comparison only.

Usage (from the project folder, in the data_collection environment):
    python ingestion/check_latency.py
"""
from datetime import datetime, timezone

import ee

ee.Initialize(project="flood-pipeline-nairobi")

USED_IN_TRAINING = {
    "CHIRPS daily": "UCSB-CHG/CHIRPS/DAILY",
    "IMERG V07": "NASA/GPM_L3/IMERG_V07",
    "ERA5-Land daily": "ECMWF/ERA5_LAND/DAILY_AGGR",
}
ALTERNATIVES = {
    "CHIRPS v3 daily (RNL)": "UCSB-CHC/CHIRPS/V3/DAILY_RNL",
    "CHIRPS v3 daily (SAT)": "UCSB-CHC/CHIRPS/V3/DAILY_SAT",
    "ERA5-Land hourly": "ECMWF/ERA5_LAND/HOURLY",
}

today = datetime.now(timezone.utc)
since = ee.Date(today.timestamp() * 1000).advance(-400, "day")


def latest(collection_id):
    """The newest image's date in the last 400 days, or the error message."""
    try:
        ms = ee.ImageCollection(collection_id).filterDate(since, ee.Date(today.timestamp() * 1000)) \
            .aggregate_max("system:time_start").getInfo()
        if ms is None:
            return "no images in the last 400 days"
        newest = datetime.fromtimestamp(ms / 1000, timezone.utc)
        return f"{newest:%Y-%m-%d}  ({(today - newest).days} days behind)"
    except ee.EEException as e:
        return f"not available: {str(e)[:60]}"


print(f"today (UTC): {today:%Y-%m-%d}\n")
print("Used in training")
for name, cid in USED_IN_TRAINING.items():
    print(f"  {name:24} {latest(cid)}")
print("\nAlternatives (comparison only)")
for name, cid in ALTERNATIVES.items():
    print(f"  {name:24} {latest(cid)}")
