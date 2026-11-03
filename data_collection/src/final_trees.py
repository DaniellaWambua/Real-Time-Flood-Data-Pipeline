import os
import pandas as pd
from comparison_setup import load, build, score_rows, FEATS, FINAL_FOLD, SEEDS, TREES, OUT

# Final test: rule and tree models trained on 2015-2023, scored once on 2024-2025
path = f"{OUT}/final_scores_trees.csv"
assert not os.path.exists(path), "final test already run"
train_years, test_years = FINAL_FOLD
parts = []
for which in ["today", "tomorrow"]:
    d = load(which)
    tr = d["year"].isin(train_years).values
    te = d["year"].isin(test_years).values
    parts.append(score_rows(d, te, which, test_years, "rule_rain_3d", 0, d.loc[te, "rain_sum_3d"].values))
    for name in TREES:
        for seed in SEEDS:
            m = build(name, seed)
            m.fit(d.loc[tr, FEATS], d.loc[tr, "y"])
            parts.append(score_rows(d, te, which, test_years, name, seed, m.predict_proba(d.loc[te, FEATS])[:, 1]))
    print(which, "train", int(tr.sum()), "test", int(te.sum()), "floods", int(d.loc[te, "y"].sum()), flush=True)

pd.concat(parts).to_csv(path, index=False)
