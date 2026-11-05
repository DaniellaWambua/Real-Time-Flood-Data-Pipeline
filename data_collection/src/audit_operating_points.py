import sys
import numpy as np, pandas as pd

# Precision reachable at fixed recall levels on 2024-2025 (decisions.md D12), seed-mean scores.
# Thresholds are chosen in hindsight, so these are upper bounds, and the period was already seen (D9, D10).
sys.argv = sys.argv[:1] + ["final"]
exec(open("data_collection/src/audit_evaluate.py").read().split("scores = pd.concat")[0])

S = pd.concat([pd.read_csv(D + f"audit_final_scores_{f}.csv", parse_dates=["date"]) for f in ("trees", "lstm")])
rows = []
for which in ["today", "tomorrow"]:
    T = {k: truth(p, which) for k, p in LABELS.items()}
    for (tl, model), g in S[S["target"] == which].groupby(["train_labels", "model"]):
        for el in LABELS:
            m = g.groupby(["catchment", "date"])["score"].mean().reset_index().merge(T[el], on=["catchment", "date"])
            y = m["y"].values[np.argsort(-m["score"].values, kind="mergesort")]
            tp = np.cumsum(y)
            prec, rec = tp / np.arange(1, len(y) + 1), tp / y.sum()
            r = {"target": which, "model": model, "train": tl, "eval": el}
            for R in (0.25, 0.5, 0.75):
                r[f"best_prec_at_recall_{R}"] = round(prec[rec >= R].max(), 3)
            ok = np.where(prec >= 0.7)[0]
            r["max_recall_with_prec_0.7"] = round(rec[ok].max(), 3) if len(ok) else 0
            rows.append(r)
res = pd.DataFrame(rows)
res.to_csv(D + "audit_final_operating_points.csv", index=False)
print(res.to_string(index=False))
