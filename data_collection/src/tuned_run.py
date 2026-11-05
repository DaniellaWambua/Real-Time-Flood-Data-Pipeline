import sys, os, json
import pandas as pd
from comparison_setup import load, FEATS, DEV_FOLDS, FINAL_FOLD, SEEDS, OUT, score_rows
from tuning_common import build_tree, LSTM_VARIANTS

# Selected settings from select_tuned.py on the development folds, then one post-hoc look at 2024-2025 (D10).
# Usage: tuned_run.py dev | final. The rule_rain_3d baseline is carried unchanged as the reference.
split = sys.argv[1]
folds = DEV_FOLDS if split == "dev" else [FINAL_FOLD]
sel = pd.read_csv(f"{OUT}/tuning/selected.csv").set_index("family")
paths = {k: f"{OUT}/tuned_{split}_scores_{k}.csv" for k in ["trees", "lstm"]}
if split == "final":
    assert not any(os.path.exists(p) for p in paths.values()), "post-hoc test already run"

parts = []
for which in ["today", "tomorrow"]:
    d = load(which)
    for train_years, val_years in folds:
        tr = d["year"].isin(train_years).values
        va = d["year"].isin(val_years).values
        parts.append(score_rows(d, va, which, val_years, "rule_rain_3d", 0, d.loc[va, "rain_sum_3d"].values))
        feat = json.loads(sel.loc["rule", "config"])["feature"]
        parts.append(score_rows(d, va, which, val_years, "rule_tuned", 0, d.loc[va, feat].values))
        for fam in ["forest", "boosting", "extra_trees"]:
            cfg = json.loads(sel.loc[fam, "config"])
            for seed in SEEDS:
                m = build_tree(fam, cfg, seed)
                m.fit(d.loc[tr, FEATS], d.loc[tr, "y"])
                parts.append(score_rows(d, va, which, val_years, fam, seed, m.predict_proba(d.loc[va, FEATS])[:, 1]))
pd.concat(parts).to_csv(paths["trees"], index=False)
print("trees done", flush=True)

from lstm_common import load_windows, fit_predict_cfg
parts = []
for which in ["today", "tomorrow"]:
    for fam, (inputs, mode) in LSTM_VARIANTS.items():
        cfg = json.loads(sel.loc[fam, "config"])
        X, meta = load_windows(which, inputs, cfg["window"])
        y = meta["y"].values
        for train_years, val_years in folds:
            tr = meta["year"].isin(list(train_years)).values
            va = meta["year"].isin(val_years).values
            for seed in SEEDS:
                s = fit_predict_cfg(X, y, tr, va, seed, mode, cfg)
                parts.append(score_rows(meta, va, which, val_years, fam, seed, s))
        print(which, fam, "done", flush=True)
pd.concat(parts).to_csv(paths["lstm"], index=False)
