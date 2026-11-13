"""
Builds the 2026 holdout set: data_collection/data/01_flood_labels/holdout_2026/features_holdout_2026.csv

Readings: readings_2026.csv, exported from hydro_data_records (source earth-engine, CHIRPS included),
1 January to 30 September 2026, one row per catchment and day.

Labels: written from dated news, Red Cross, police and ReliefWeb reports only, before any model was scored on 2026
(the rule and every source are in LABELS_2026.md). Rule:
  - flood: a credible dated report describes flooding that day at a named place in one of the catchment's wards
  - unknown: the two days either side of a flood day; days whose reports name only "Nairobi" or a general area;
    days with an official flood warning or evacuation for the catchment but no reported flooding
  - no_flood: every other day
Flood days in one catchment less than three days apart form one event (the GAP = 2 rule used for training).
"""
import numpy as np
import pandas as pd

D = "data_collection/data/01_flood_labels/holdout_2026/"

FLOOD = {  # catchment -> flood days
    "ngong": ["2026-03-05", "2026-03-06", "2026-03-07", "2026-03-14", "2026-03-15",
              "2026-04-28", "2026-04-30", "2026-05-01"],
    "nairobi": ["2026-03-05", "2026-03-06", "2026-03-07", "2026-03-14", "2026-03-15",
                "2026-04-27", "2026-04-28", "2026-04-30", "2026-05-01"],
    "mathare": ["2026-03-06", "2026-03-07", "2026-03-08", "2026-03-14", "2026-03-15",
                "2026-04-30", "2026-05-01"],
}
UNKNOWN = {  # catchment -> days with only general reports, warnings or evacuations
    "ngong": ["2026-02-17", "2026-03-20", "2026-03-26", "2026-04-29"],
    "nairobi": ["2026-02-17", "2026-03-26", "2026-04-29"],
    "mathare": ["2026-02-17", "2026-03-05", "2026-03-26", "2026-04-28", "2026-04-29"],
}
BUFFER = pd.Timedelta(days=2)

r = pd.read_csv(D + "readings_2026.csv", parse_dates=["date"])
r["month_sin"] = np.sin(2 * np.pi * r["date"].dt.month / 12)
r["month_cos"] = np.cos(2 * np.pi * r["date"].dt.month / 12)
r["label_status"] = "no_flood"
r["event_id"] = ""
for c, days in FLOOD.items():
    days = pd.to_datetime(days)
    for d in days:  # buffer first, flood days overwrite it
        m = (r["catchment"] == c) & (r["date"] >= d - BUFFER) & (r["date"] <= d + BUFFER)
        r.loc[m & (r["label_status"] == "no_flood"), "label_status"] = "unknown"
    for d in pd.to_datetime(UNKNOWN[c]):
        m = (r["catchment"] == c) & (r["date"] == d) & (r["label_status"] == "no_flood")
        r.loc[m, "label_status"] = "unknown"
    s = pd.Series(sorted(days))
    group = (s.diff().dt.days.fillna(0) > 2).cumsum()
    for _, g in s.groupby(group):
        eid = f"H26-{c}-{g.iloc[0].date()}"
        r.loc[(r["catchment"] == c) & r["date"].isin(g), ["label_status", "event_id"]] = ["flood", eid]
r.to_csv(D + "features_holdout_2026.csv", index=False)
print(r["label_status"].value_counts().to_dict())
print(r[r["label_status"] == "flood"].groupby("catchment")["event_id"].nunique().to_dict(),
      r["event_id"].replace("", np.nan).nunique(), "events")
