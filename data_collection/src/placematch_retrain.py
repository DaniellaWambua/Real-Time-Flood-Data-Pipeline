import sys
import numpy as np, pandas as pd
sys.path.insert(0, "data_collection/src")
import comparison_setup as cs
from sequences import make_windows
from lstm_common import fit_predict

# Place-matching comparison: frozen lstm_raw, target "today", development folds, 8 seeds.
# Trains once on the audited labels and once on the place-matched labels, in the same environment,
# and scores every validation day. Usage: placematch_retrain.py audited|placematched first-last
D = "data_collection/data/08_model_ready/"
LABELS = {"audited": D + "features_daily_audited.csv", "placematched": D + "features_daily_placematched.csv"}
TRAIN = sys.argv[1]
lo, hi = map(int, sys.argv[2].split("-"))
cs.PATH = LABELS[TRAIN]
lab = cs.load("today")[["catchment", "date", "y"]]
X, meta = make_windows(path=cs.PATH)
meta = meta[["catchment", "date", "year"]].merge(lab, on=["catchment", "date"], how="left")
y = meta["y"].fillna(0).astype(int).values
parts = []
for train_years, val_years in cs.DEV_FOLDS:
    tr = (meta["year"].isin(list(train_years)) & meta["y"].notna()).values
    va = meta["year"].isin(val_years).values
    for seed in range(lo, hi + 1):
        s = fit_predict(X, y, tr, va, seed, "weights")
        parts.append(pd.DataFrame({"train_labels": TRAIN, "val": val_years[0], "seed": seed,
                                   "catchment": meta.loc[va, "catchment"].values,
                                   "date": meta.loc[va, "date"].values, "score": s}))
        print(TRAIN, val_years[0], "seed", seed, "train floods", int(y[tr].sum()), flush=True)
pd.concat(parts).to_csv(D + f"placematch_dev_scores_lstm_raw_{TRAIN}_s{lo}-{hi}.csv", index=False)
