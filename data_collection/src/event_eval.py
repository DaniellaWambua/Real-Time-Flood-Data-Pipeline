import pandas as pd, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

df = pd.read_csv("data_collection/data/08_model_ready/features_daily.csv", parse_dates=["date"])
df["year"] = df["date"].dt.year

FEATS = ["rain_mm", "rain_sum_3d", "rain_sum_7d", "rain_sum_14d", "rain_sum_30d",
         "era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa",
         "pressure_change_1d", "soil_1", "soil_2",
         "api", "days_since_rain", "month_sin", "month_cos", "rain_anom_7d",
         "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5"]
FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]
DAY = pd.Timedelta(days=1)

d = df[df["label_status"].isin(["flood", "no_flood"])].copy()
d["y"] = (d["label_status"] == "flood").astype(int)

rows = []
for train_years, val_years in FOLDS:
    tr = d[d["year"].isin(train_years)]
    va = d[d["year"].isin(val_years)].copy()
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                       class_weight="balanced", random_state=0)
    m.fit(tr[FEATS], tr["y"])
    va["boosting"] = m.predict_proba(va[FEATS])[:, 1]
    va["rule"] = va["rain_sum_3d"]
    events = va[va["y"] == 1].groupby("event_id").agg(
        catchment=("catchment", "first"), start=("date", "min"), end=("date", "max"))
    for method in ["boosting", "rule"]:
        for q in (0.03, 0.05, 0.10):
            alarms = va[va[method] >= va[method].quantile(1 - q)]
            hit = 0
            for _, e in events.iterrows():
                a = alarms[(alarms["catchment"] == e["catchment"]) &
                           (alarms["date"] >= e["start"] - DAY) & (alarms["date"] <= e["end"] + DAY)]
                hit += len(a) > 0
            false_days = int((alarms["y"] == 0).sum())
            rows.append({"val": val_years[0], "method": method, "alarm_share": q,
                         "events": len(events), "detected": hit,
                         "false_days": false_days, "catchment_years": 3 * len(val_years)})

res = pd.DataFrame(rows)
print(res.to_string(index=False))
tot = res.groupby(["method", "alarm_share"])[["events", "detected", "false_days", "catchment_years"]].sum()
tot["event_recall"] = (tot["detected"] / tot["events"]).round(2)
tot["false_days_per_catchment_year"] = (tot["false_days"] / tot["catchment_years"]).round(1)
print()
print(tot[["events", "detected", "event_recall", "false_days_per_catchment_year"]])
res.to_csv("data_collection/data/08_model_ready/event_eval_results.csv", index=False)