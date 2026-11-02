import pandas as pd, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import average_precision_score

df = pd.read_csv("data_collection/data/08_model_ready/features_daily.csv", parse_dates=["date"])
df["year"] = df["date"].dt.year

FEATS = ["rain_mm", "rain_sum_3d", "rain_sum_7d", "rain_sum_14d", "rain_sum_30d",
         "era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa",
         "pressure_change_1d", "soil_1", "soil_2",
         "api", "days_since_rain", "month_sin", "month_cos", "rain_anom_7d"]
FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]

def make_target(d, which):
    col = "label_status" if which == "today" else "next_status"
    d = d[d[col].isin(["flood", "no_flood"])]
    return d, (d[col] == "flood").astype(int).values

def recall_top(y, s, q=0.05):
    k = max(1, int(len(y) * q))
    return y[np.argsort(-s)[:k]].sum() / y.sum()

def balance(X, y, ratio, seed):
    rng = np.random.default_rng(seed)
    pos = np.where(y == 1)[0]
    neg = np.where(y == 0)[0]
    keep = rng.choice(neg, size=min(len(neg), ratio * len(pos)), replace=False)
    idx = np.concatenate([pos, keep])
    return X.iloc[idx], y[idx]

def build(name, ratio, seed):
    full = ratio is None
    if name == "logistic":
        return make_pipeline(StandardScaler(),
                             LogisticRegression(class_weight="balanced" if full else None, max_iter=1000))
    return RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=seed, n_jobs=-1,
                                  class_weight="balanced_subsample" if full else None)

rows = []
for which in ["today", "tomorrow"]:
    d, y = make_target(df, which)
    for train_years, val_years in FOLDS:
        tr = d["year"].isin(train_years).values
        va = d["year"].isin(val_years).values
        Xtr, ytr = d.loc[tr, FEATS], y[tr]
        Xva, yva = d.loc[va, FEATS], y[va]
        for ratio in [1, 5, None]:
            seeds = [0, 1, 2] if ratio else [0]
            for name in ["logistic", "forest"]:
                aps, recs = [], []
                for seed in seeds:
                    Xb, yb = balance(Xtr, ytr, ratio, seed) if ratio else (Xtr, ytr)
                    m = build(name, ratio, seed)
                    m.fit(Xb, yb)
                    s = m.predict_proba(Xva)[:, 1]
                    aps.append(average_precision_score(yva, s))
                    recs.append(recall_top(yva, s))
                rows.append({"target": which, "val": val_years[0], "model": name,
                             "balance": "none" if ratio is None else f"{ratio}:1",
                             "base_rate": round(yva.mean(), 3),
                             "avg_precision": round(np.mean(aps), 3),
                             "recall_top5pct": round(np.mean(recs), 2)})

res = pd.DataFrame(rows)
print(res.to_string(index=False))
print()
print(res.groupby(["target", "model", "balance"])[["avg_precision", "recall_top5pct"]].mean().round(3))
res.to_csv("data_collection/data/08_model_ready/baseline_balanced_results.csv", index=False)
