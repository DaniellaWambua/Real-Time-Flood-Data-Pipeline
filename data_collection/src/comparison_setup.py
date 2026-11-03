import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier

PATH = "data_collection/data/08_model_ready/features_daily.csv"
OUT = "data_collection/data/08_model_ready"

# 20-feature list from baselines_balanced.py
FEATS = ["rain_mm", "rain_sum_3d", "rain_sum_7d", "rain_sum_14d", "rain_sum_30d",
         "era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa",
         "pressure_change_1d", "soil_1", "soil_2",
         "api", "days_since_rain", "month_sin", "month_cos", "rain_anom_7d",
         "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5"]
DEV_FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]
FINAL_FOLD = (range(2015, 2024), [2024, 2025])
SEEDS = [0, 1, 2]
TREES = ["forest", "boosting", "extra_trees"]


def load(which):
    """Rows with a known label for the target. tdate and teid refer to the day being predicted."""
    df = pd.read_csv(PATH, parse_dates=["date"])
    assert df.equals(df.sort_values(["catchment", "date"]))
    df["year"] = df["date"].dt.year
    col = "label_status" if which == "today" else "next_status"
    if which == "today":
        df["tdate"], df["teid"] = df["date"], df["event_id"]
    else:
        df["tdate"] = df["date"] + pd.Timedelta(days=1)
        df["teid"] = df.groupby("catchment")["event_id"].shift(-1)
    d = df[df[col].isin(["flood", "no_flood"])].copy()
    d["y"] = (d[col] == "flood").astype(int)
    return d.reset_index(drop=True)


def build(name, seed):
    if name == "boosting":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                              class_weight="balanced", random_state=seed)
    cls = RandomForestClassifier if name == "forest" else ExtraTreesClassifier
    return cls(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
               random_state=seed, n_jobs=-1)


def score_rows(d, va, which, val_years, model, seed, s):
    out = d.loc[va, ["catchment", "date", "tdate", "y", "teid"]].copy()
    out.insert(0, "target", which)
    out.insert(1, "val", "-".join(map(str, sorted({val_years[0], val_years[-1]}))))
    out.insert(2, "model", model)
    out.insert(3, "seed", seed)
    out["score"] = np.round(s, 7)
    return out
