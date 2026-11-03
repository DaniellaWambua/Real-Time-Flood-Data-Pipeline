import pandas as pd, numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score
from sklearn.ensemble import HistGradientBoostingClassifier

df = pd.read_csv("data_collection/data/08_model_ready/features_daily.csv", parse_dates=["date"])
df["year"] = df["date"].dt.year

FEATS = ["rain_mm", "rain_sum_3d", "rain_sum_7d", "rain_sum_14d", "rain_sum_30d",
         "era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa",
         "pressure_change_1d", "soil_1", "soil_2", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5"]
FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]

def make_target(d, which):
    col = "label_status" if which == "today" else "next_status"
    d = d[d[col].isin(["flood", "no_flood"])]
    return d, (d[col] == "flood").astype(int).values

def recall_top(y, s, q=0.05):
    k = max(1, int(len(y) * q))
    return y[np.argsort(-s)[:k]].sum() / y.sum()

MODELS = {
    "rule_rain_3d": None,
    "boosting": HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                               class_weight="balanced", random_state=0),
    "forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=5,
                                     class_weight="balanced_subsample", random_state=0, n_jobs=-1),
}

rows = []
for which in ["today", "tomorrow"]:
    d, y = make_target(df, which)
    for train_years, val_years in FOLDS:
        tr = d["year"].isin(train_years).values
        va = d["year"].isin(val_years).values
        for name, model in MODELS.items():
            if model is None:
                s = d.loc[va, "rain_sum_3d"].values
            else:
                model.fit(d.loc[tr, FEATS], y[tr])
                s = model.predict_proba(d.loc[va, FEATS])[:, 1]
            rows.append({"target": which, "val": f"{val_years[0]}", "model": name,
                         "base_rate": round(y[va].mean(), 3),
                         "avg_precision": round(average_precision_score(y[va], s), 3),
                         "recall_top5pct": round(recall_top(y[va], s), 2)})

res = pd.DataFrame(rows)
print(res.to_string(index=False))
print()
print(res.groupby(["target", "model"])[["avg_precision", "recall_top5pct"]].mean().round(3))
res.to_csv("data_collection/data/08_model_ready/baseline_results.csv", index=False)