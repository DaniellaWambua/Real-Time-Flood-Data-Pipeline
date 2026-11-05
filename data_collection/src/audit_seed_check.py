import sys
import numpy as np, pandas as pd

# Robustness of the lstm_raw result to the seed (decisions.md D12). Combines the three D8 seeds with the
# extra seeds 3 to 7 and compares, seed by seed, training on original against training on audited labels.
sys.argv = sys.argv[:1] + ["dev"]
exec(open("data_collection/src/audit_evaluate.py").read().split("scores = pd.concat")[0])

out = []
for split in ["dev", "final"]:
    s = pd.concat([pd.read_csv(D + f"audit_{split}_scores_lstm{x}.csv", parse_dates=["date"])
                   for x in ("", "_extra_seeds")])
    for which in ["today", "tomorrow"]:
        T = {k: truth(p, which) for k, p in LABELS.items()}
        for el, tt in T.items():
            for seed in sorted(s["seed"].unique()):
                v = {}
                for tl in LABELS:
                    g = s[(s["target"] == which) & (s["train_labels"] == tl) & (s["seed"] == seed)]
                    g = g.merge(tt, on=["catchment", "date"])
                    v[tl] = ap(g["y"].values, g["score"].values)
                out.append({"split": split, "target": which, "eval_labels": el, "seed": seed,
                            "ap_train_original": v["original"], "ap_train_audited": v["audited"]})
res = pd.DataFrame(out)
res["diff"] = res["ap_train_audited"] - res["ap_train_original"]
res.to_csv(D + "audit_lstm_seed_check.csv", index=False)
summ = res.groupby(["split", "target", "eval_labels"]).agg(
    seeds=("seed", "size"), ap_original_mean=("ap_train_original", "mean"),
    ap_audited_mean=("ap_train_audited", "mean"), diff_mean=("diff", "mean"),
    diff_sd=("diff", "std"), seeds_better=("diff", lambda d: int((d > 0).sum())))
summ.to_csv(D + "audit_lstm_seed_summary.csv")
print(summ.round(3).to_string())
