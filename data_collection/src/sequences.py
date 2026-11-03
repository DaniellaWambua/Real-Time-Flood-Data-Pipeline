import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

SEQ_FEATS = ["rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5",
             "era5_rain_mm", "soil_1", "soil_2", "temp_c", "dewpoint_depression",
             "pressure_hpa", "month_sin", "month_cos"]
CATCHMENTS = ["ngong", "mathare", "nairobi"]
T = 14

def make_windows(path="data_collection/data/08_model_ready/features_daily.csv", t=T):
    df = pd.read_csv(path, parse_dates=["date"]).sort_values(["catchment", "date"])
    for c in CATCHMENTS:
        df[f"is_{c}"] = (df["catchment"] == c).astype("float32")
    feats = SEQ_FEATS + [f"is_{c}" for c in CATCHMENTS]
    xs, metas = [], []
    for c, g in df.groupby("catchment"):
        vals = g[feats].values.astype("float32")
        xs.append(sliding_window_view(vals, (t, vals.shape[1]))[:, 0])
        m = g.iloc[t - 1:][["catchment", "date", "label_status", "next_status", "event_id"]].copy()
        metas.append(m)
    X = np.concatenate(xs)
    meta = pd.concat(metas).reset_index(drop=True)
    meta["year"] = meta["date"].dt.year
    return X, meta