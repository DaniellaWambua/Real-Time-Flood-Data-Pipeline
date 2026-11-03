import pandas as pd
from comparison_setup import load, FINAL_FOLD, OUT

# Sensitivity check for the rule: fixed threshold at the 95th percentile of rain_sum_3d on 2015-2023 labelled days
DAY = pd.Timedelta(days=1)
train_years, test_years = FINAL_FOLD
rows = []
for which in ["today", "tomorrow"]:
    d = load(which)
    thr = d.loc[d["year"].isin(train_years), "rain_sum_3d"].quantile(0.95)
    te = d[d["year"].isin(test_years)]
    alarms = te[te["rain_sum_3d"] >= thr]
    ev = te[te["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                              start=("tdate", "min"), end=("tdate", "max"))
    hit = sum(((alarms["catchment"] == e.catchment) & (alarms["tdate"] >= e.start - DAY) &
               (alarms["tdate"] <= e.end + DAY)).any() for e in ev.itertuples())
    cy = 3 * len(test_years)
    rows.append({"target": which, "val": "2024-2025", "threshold_mm": round(thr, 1),
                 "alarm_share_test": round(len(alarms) / len(te), 3), "events": len(ev), "detected": int(hit),
                 "event_recall": round(hit / len(ev), 3), "false_days": int((alarms["y"] == 0).sum()),
                 "false_days_per_cy": round((alarms["y"] == 0).sum() / cy, 1)})

res = pd.DataFrame(rows)
print(res.to_string(index=False))
res.to_csv(f"{OUT}/rule_fixed_threshold_results.csv", index=False)
