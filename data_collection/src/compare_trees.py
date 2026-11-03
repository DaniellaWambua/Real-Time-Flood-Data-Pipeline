import pandas as pd
from comparison_setup import load, build, score_rows, FEATS, DEV_FOLDS, SEEDS, TREES, OUT

# Rule and tree models on the development folds, per-day scores saved for evaluate_comparison.py
parts = []
for which in ["today", "tomorrow"]:
    d = load(which)
    for train_years, val_years in DEV_FOLDS:
        tr = d["year"].isin(train_years).values
        va = d["year"].isin(val_years).values
        parts.append(score_rows(d, va, which, val_years, "rule_rain_3d", 0, d.loc[va, "rain_sum_3d"].values))
        for name in TREES:
            for seed in SEEDS:
                m = build(name, seed)
                m.fit(d.loc[tr, FEATS], d.loc[tr, "y"])
                parts.append(score_rows(d, va, which, val_years, name, seed,
                                        m.predict_proba(d.loc[va, FEATS])[:, 1]))
        print(which, val_years, "train", int(tr.sum()), "val", int(va.sum()), "floods", int(d.loc[va, "y"].sum()), flush=True)

pd.concat(parts).to_csv(f"{OUT}/dev_scores_trees.csv", index=False)
