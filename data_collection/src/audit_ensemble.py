import sys
import numpy as np, pandas as pd

# Seed ensemble check for lstm_raw (decisions.md D12): the mean score of all eight seeds as one model.
# Judged on the development folds first; the 2024-2025 numbers are a post-test look (D9, D10).
sys.argv = sys.argv[:1] + ["dev"]
src = open("data_collection/src/audit_evaluate.py").read().split("scores = pd.concat")[0]
exec(src)
rows = []
for split, ny in [("dev", 4), ("final", 2)]:
    s = pd.concat([pd.read_csv(D + f"audit_{split}_scores_lstm{x}.csv", parse_dates=["date"]) for x in ("", "_extra_seeds")])
    s["val"] = s["val"].astype(str)
    for which in ["today", "tomorrow"]:
        T = {k: truth(p, which) for k, p in LABELS.items()}
        for tl in LABELS:
            g = s[(s["target"] == which) & (s["train_labels"] == tl)]
            ens = g.groupby(["val", "catchment", "date"])["score"].mean().reset_index()
            for el, tt in T.items():
                r = evaluate(ens.merge(tt, on=["catchment", "date"]), ny)
                single = np.mean([ap(x["y"].values, x["score"].values)
                                  for _, x in g.merge(tt, on=["catchment", "date"]).groupby("seed")])
                rows.append({"split": split, "target": which, "train_labels": tl, "eval_labels": el,
                             "mean_single_seed_ap": single, **r})
res = pd.DataFrame(rows)
res.to_csv(D + "audit_lstm_ensemble.csv", index=False)
print(res[["split", "target", "train_labels", "eval_labels", "mean_single_seed_ap", "ap", "max_f1",
           "precision_5", "recall_5", "f1_5", "pod_5", "far_5"]].round(3).to_string(index=False))
