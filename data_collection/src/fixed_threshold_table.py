import sys
import numpy as np, pandas as pd
from comparison_setup import load, FINAL_FOLD, OUT

# Day-level precision, recall and F1 on 2024-2025 at thresholds fixed before the test.
# Thresholds come from the pooled out-of-fold development scores (2019, 2021-2023), so no retraining.
# "f1" maximises F1 on those scores, "recall75" is the highest threshold with recall at least 0.75.
# Optional argument: a file prefix, e.g. tuned_ for the D10 tuning run.
PREFIX = sys.argv[1] if len(sys.argv) > 1 else ""
DAY = pd.Timedelta(days=1)
read = lambda k: pd.read_csv(f"{OUT}/{PREFIX}{k}.csv", parse_dates=["date", "tdate"], dtype={"val": str})
dev = pd.concat([read("dev_scores_trees"), read("dev_scores_lstm")])
fin = pd.concat([read("final_scores_trees"), read("final_scores_lstm")])


def thresholds(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp, n, t = np.cumsum(y)[last], np.arange(1, len(y) + 1)[last], s[last]
    rec = tp / y.sum()
    return {"f1": t[np.argmax(2 * tp / (n + y.sum()))], "recall75": t[np.argmax(rec >= 0.75)]}


def score(g, t):
    alarm = g["score"].values >= t
    y = g["y"].values
    tp = int((alarm & (y == 1)).sum())
    p = tp / alarm.sum() if alarm.sum() else 0.0
    r = tp / y.sum()
    al = g[alarm]
    ev = g[g["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                            start=("tdate", "min"), end=("tdate", "max"))
    hit = [((al["catchment"] == e.catchment) & (al["tdate"] >= e.start - DAY) & (al["tdate"] <= e.end + DAY)).any()
           for e in ev.itertuples()]
    return {"alarm_share": alarm.mean(), "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if tp else 0.0,
            "event_recall": np.mean(hit), "false_days_per_cy": int((alarm & (y == 0)).sum()) / 6}


rows = []
for (which, model, seed), gf in fin.groupby(["target", "model", "seed"]):
    gd = dev[(dev["target"] == which) & (dev["model"] == model) & (dev["seed"] == seed)]
    for rule, t in thresholds(gd["y"].values, gd["score"].values).items():
        rows.append({"target": which, "model": model, "seed": seed, "threshold_from": "dev out-of-fold 2019-2023",
                     "criterion": rule, "threshold": t, **score(gf, t)})

# the rule needs no model, so its threshold can also be fixed on every labelled day of 2015-2023
for which in ["today", "tomorrow"]:
    d = load(which)
    tr = d[d["year"].isin(FINAL_FOLD[0])]
    gf = fin[(fin["target"] == which) & (fin["model"] == "rule_rain_3d")]
    for rule, t in thresholds(tr["y"].values, tr["rain_sum_3d"].values).items():
        rows.append({"target": which, "model": "rule_rain_3d", "seed": 0, "threshold_from": "all labelled days 2015-2023",
                     "criterion": rule, "threshold": t, **score(gf, t)})

res = pd.DataFrame(rows)
keys = ["target", "criterion", "threshold_from", "model"]
out = res.groupby(keys, sort=False).agg(n_seeds=("seed", "size"), **{c: (c, "mean") for c in
      ["threshold", "alarm_share", "precision", "recall", "f1", "event_recall", "false_days_per_cy"]})
out = out.reset_index().sort_values(["target", "criterion", "threshold_from"], kind="stable").round(3)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
out.to_csv(f"{OUT}/{PREFIX}fixed_threshold_results.csv", index=False)
