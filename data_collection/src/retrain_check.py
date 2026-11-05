import sys
import numpy as np, pandas as pd

# Reproduction check for D13: frozen settings trained and judged on the original labels must give the saved
# D8 numbers in comparison_results.csv to three decimals for the rule, boosting and the three LSTM variants.
# Forest and ExtraTrees are reported but not required (D12 found floating point differences between machines).
# Exits with an error if a required number differs. Usage: retrain_check.py [dev|final]
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "dev"
sys.argv = sys.argv[:1] + [SPLIT]
exec(open("data_collection/src/audit_evaluate.py").read().split("scores = pd.concat")[0])
REQUIRED = ["rule_rain_3d", "boosting", "lstm_raw", "lstm_log", "lstm_batches"]

scores = pd.concat([pd.read_csv(D + f"retrain_{SPLIT}_scores_frozen_{f}_original_s0-2.csv", parse_dates=["date"])
                    for f in ("trees", "lstm")])
scores["val"] = scores["val"].astype(str)
saved = pd.read_csv(D + "comparison_results.csv", dtype={"val": str})
saved = saved[(saved["split"] == SPLIT) & saved["val"].isin(["pooled_dev", "2024-2025"])].set_index(["target", "model"])

rows = []
for which in ["today", "tomorrow"]:
    tt = truth(LABELS["original"], which)
    for model, gm in scores[scores["target"] == which].groupby("model"):
        per = []
        for seed, gs in gm.groupby("seed"):
            g = gs.merge(tt, on=["catchment", "date"])
            r = evaluate(g, NYEARS)
            folds = [x for _, x in g.groupby("val")]
            r["ap_fold_mean"] = np.mean([ap(x["y"].values, x["score"].values) for x in folds])
            r["recall_top5pct"] = sum(x["y"].values[np.argsort(-x["score"].values, kind="mergesort")[:max(1, int(len(x) * 0.05))]].sum()
                                      for x in folds) / g["y"].sum()
            per.append(r)
        m = pd.DataFrame(per).mean()
        mine = {"avg_precision": m["ap"], "ap_fold_mean": m["ap_fold_mean"], "max_f1_day": m["max_f1"],
                "recall_top5pct": m["recall_top5pct"], "flood_days": m["flood_days"]}
        for k in (3, 5, 10):
            mine[f"event_recall_{k}pct"] = m[f"pod_{k}"]
            mine[f"false_days_per_cy_{k}pct"] = m[f"false_days_per_cy_{k}"]
        s = saved.loc[(which, model)]
        for metric, v in mine.items():
            rows.append({"split": SPLIT, "target": which, "model": model, "required": model in REQUIRED,
                         "metric": metric, "saved": s[metric], "retrained": round(v, 3),
                         "match": bool(abs(round(v, 3) - s[metric]) < 1e-9), "abs_diff": abs(v - s[metric])})

res = pd.DataFrame(rows)
res.to_csv(D + f"retrain_reproduction_{SPLIT}.csv", index=False)
print(res.groupby(["target", "model"]).agg(metrics=("match", "size"), matching=("match", "sum"),
                                           max_abs_diff=("abs_diff", "max")).round(4).to_string())
bad = res[res["required"] & ~res["match"]]
if len(bad):
    print(bad.to_string(index=False))
    sys.exit(f"{len(bad)} required numbers do not reproduce the saved {SPLIT} results")
print("all required numbers reproduce the saved", SPLIT, "results to three decimals")
