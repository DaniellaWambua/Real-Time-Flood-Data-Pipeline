import json, sys
import numpy as np, pandas as pd
import comparison_setup as cs

# Retraining on the original or audited labels (decisions.md D13). Every model scores every day of the
# validation years, so the scores can be judged against either label set by retrain_evaluate.py.
# Usage: retrain_scores.py frozen|tuned trees|lstm dev|final original|audited [first-last seed, default 0-2]
# "final" trains on 2015-2023 and scores 2024-2025, already seen in D9, D10 and D12, so not an unseen test.
D = "data_collection/data/08_model_ready/"
LABELS = {"original": D + "features_daily.csv", "audited": D + "features_daily_audited.csv"}
SETTING, FAMILY, SPLIT, TRAIN = sys.argv[1:5]
SEED_RANGE = sys.argv[5] if len(sys.argv) > 5 else "0-2"
lo, hi = map(int, SEED_RANGE.split("-"))
SEEDS = list(range(lo, hi + 1))
FOLDS = cs.DEV_FOLDS if SPLIT == "dev" else [cs.FINAL_FOLD]
OUT = D + f"retrain_{SPLIT}_scores_{SETTING}_{FAMILY}_{TRAIN}_s{SEED_RANGE}.csv"
assert SETTING in ("frozen", "tuned") and FAMILY in ("trees", "lstm") and SPLIT in ("dev", "final") and TRAIN in LABELS
cs.PATH = LABELS[TRAIN]
SEL = pd.read_csv(D + "tuning/selected.csv").set_index("family")


def cfg(family):
    return json.loads(SEL.loc[family, "config"])


def rows(meta, mask, which, val_years, model, seed, s):
    return pd.DataFrame({"setting": SETTING, "train_labels": TRAIN, "target": which,
                         "val": "-".join(map(str, sorted({val_years[0], val_years[-1]}))), "model": model,
                         "seed": seed, "catchment": meta.loc[mask, "catchment"].values,
                         "date": meta.loc[mask, "date"].values, "score": np.round(s, 7)})


parts = []
if FAMILY == "trees":
    from tuning_common import build_tree
    full = pd.read_csv(cs.PATH, parse_dates=["date"])
    full["year"] = full["date"].dt.year
    for which in ["today", "tomorrow"]:
        d = cs.load(which)
        for train_years, val_years in FOLDS:
            tr = d["year"].isin(train_years).values
            va = full["year"].isin(val_years).values
            if 0 in SEEDS:
                feat = "rain_sum_3d" if SETTING == "frozen" else cfg("rule")["feature"]
                parts.append(rows(full, va, which, val_years, "rule_rain_3d", 0, full.loc[va, feat].values))
            for name in cs.TREES:
                for seed in SEEDS:
                    m = cs.build(name, seed) if SETTING == "frozen" else build_tree(name, cfg(name), seed)
                    m.fit(d.loc[tr, cs.FEATS], d.loc[tr, "y"])
                    parts.append(rows(full, va, which, val_years, name, seed,
                                      m.predict_proba(full.loc[va, cs.FEATS])[:, 1]))
            print(SETTING, TRAIN, which, val_years[0], "train", int(tr.sum()), "floods", int(d.loc[tr, "y"].sum()), flush=True)
else:
    from sequences import make_windows
    from lstm_common import VARIANTS, fit_predict, fit_predict_cfg
    for which in ["today", "tomorrow"]:
        lab = cs.load(which)[["catchment", "date", "y"]]
        for variant, inputs, mode in VARIANTS:
            name = f"lstm_{variant}"
            c = cfg(name) if SETTING == "tuned" else None
            X, meta = make_windows(path=cs.PATH, t=c["window"] if c else 14)
            if inputs == "log":
                X[:, :, :5] = np.log1p(X[:, :, :5])
            meta = meta[["catchment", "date", "year"]].merge(lab, on=["catchment", "date"], how="left")
            y = meta["y"].fillna(0).astype(int).values
            for train_years, val_years in FOLDS:
                # train on labelled windows only, as lstm_common.load_windows; score every validation window
                tr = (meta["year"].isin(list(train_years)) & meta["y"].notna()).values
                va = meta["year"].isin(val_years).values
                for seed in SEEDS:
                    s = fit_predict(X, y, tr, va, seed, mode) if c is None else fit_predict_cfg(X, y, tr, va, seed, mode, c)
                    parts.append(rows(meta, va, which, val_years, name, seed, s))
                print(SETTING, TRAIN, which, name, val_years[0], "seeds", SEED_RANGE, flush=True)

pd.concat(parts).to_csv(OUT, index=False)
print("written", OUT)
