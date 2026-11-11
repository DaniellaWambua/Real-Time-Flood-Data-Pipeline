import numpy as np, pandas as pd

# Applies the event_tune.py procedure to every comparison model (frozen setting, audited labels, target today).
# Each model handles the class imbalance in training (comparison_setup.build, lstm_common.fit_predict):
#   forest, extra_trees   class_weight="balanced_subsample"
#   boosting              class_weight="balanced"
#   lstm_raw, lstm_log    flood days weighted by sqrt(dry days / flood days)
#   lstm_batches          balanced batches, each chunk of dry days paired with an equal draw of flood days
#   rule_rain_3d          no training, 3-day rainfall total as the score
# Seed scores are averaged per day (trees 3 seeds, LSTMs 8). Two thresholds are chosen per model on the
# development folds only, then each is applied once to 2024-2025:
#   day-F1     best day-level F1 on labelled development days (how the deployed 0.555 was chosen)
#   event-CSI  best critical success index, events detected / (events + false alarm episodes)
# Scores differ in scale between models (the rule is in mm), so candidate thresholds are development-score
# quantiles from 0.90 to 0.999, so a model may alarm on at most 10% of days. Without this cap event-CSI
# favours near-constant alarms, which merge many false alarms into a few long episodes. Ties go to the higher threshold. Event definitions as event_evaluate.py.
D = "data_collection/data/08_model_ready/"
DAY = pd.Timedelta(days=1)
QS = np.round(np.arange(0.90, 0.9991, 0.001), 3)
lab = pd.read_csv(D + "features_daily_audited.csv", parse_dates=["date"])[["catchment", "date", "label_status", "event_id"]]


def load(split):
    files = [f"retrain_{split}_scores_frozen_trees_audited_s0-2.csv",
             f"retrain_{split}_scores_frozen_lstm_audited_s0-2.csv", f"retrain_{split}_scores_frozen_lstm_audited_s3-7.csv"]
    s = pd.concat([pd.read_csv(D + f, parse_dates=["date"], low_memory=False) for f in files])
    s = s[s["target"] == "today"]
    return s.groupby(["model", "val", "catchment", "date"], as_index=False).agg(score=("score", "mean"), seeds=("seed", "nunique"))


def prepare(d):
    m = d.merge(lab, on=["catchment", "date"])
    parts = []
    for _, g in m.groupby("val"):
        ev = (g[g["label_status"] == "flood"].groupby("event_id")
              .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max")))
        known = g[g["label_status"].isin(["flood", "no_flood"])]
        parts.append((g, ev, known["label_status"].eq("flood").values, known["score"].values))
    return parts


def ap(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(y) + 1)[last])


def stats(parts, thr, catchment_years):
    n = det = eps = false_eps = tp = fp = fn = 0
    for g, ev, y, s in parts:
        a = s >= thr
        tp += int((a & y).sum()); fp += int((a & ~y).sum()); fn += int((~a & y).sum())
        alarms = g[g["score"] >= thr]
        for e in ev.itertuples():
            x = alarms[alarms["catchment"] == e.catchment]
            det += bool(((x["date"] >= e.start - DAY) & (x["date"] <= e.end + DAY)).any())
        n += len(ev)
        for c, x in alarms.sort_values("date").groupby("catchment"):
            evc = ev[ev["catchment"] == c]
            for _, ep in x.groupby((x["date"].diff() != DAY).cumsum()):
                eps += 1
                false_eps += not ((evc["start"] - DAY <= ep["date"].max()) & (evc["end"] + DAY >= ep["date"].min())).any()
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn)
    er = det / n
    ep_p = (eps - false_eps) / eps if eps else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "events": n, "detected": det, "event_recall": er, "episodes": eps, "false_episodes": false_eps,
            "episode_precision": ep_p, "event_f1": 2 * ep_p * er / (ep_p + er) if ep_p + er else 0.0,
            "csi": det / (n + false_eps), "false_eps_per_cy": false_eps / catchment_years}


dev, fin = load("dev"), load("final")
rows, sweeps = [], []
for model in sorted(dev["model"].unique()):
    dp, fp_ = prepare(dev[dev["model"] == model]), prepare(fin[fin["model"] == model])
    ydev = np.concatenate([p[2] for p in dp]); sdev = np.concatenate([p[3] for p in dp])
    yfin = np.concatenate([p[2] for p in fp_]); sfin = np.concatenate([p[3] for p in fp_])
    grid = np.unique(np.quantile(dev.loc[dev["model"] == model, "score"], QS))
    sw = pd.DataFrame([{"model": model, "threshold": t, **stats(dp, t, 12)} for t in grid])
    sweeps.append(sw)
    for rule, col in [("day-F1", "f1"), ("event-CSI", "csi")]:
        b = sw.sort_values([col, "threshold"], ascending=[False, False]).iloc[0]
        rows.append({"model": model, "seeds": int(fin.loc[fin["model"] == model, "seeds"].iloc[0]), "rule": rule,
                     "threshold": round(float(b["threshold"]), 4), "dev_" + col: b[col],
                     "dev_ap": ap(ydev, sdev), "ap": ap(yfin, sfin), **stats(fp_, b["threshold"], 6)})
res = pd.DataFrame(rows)
res.to_csv(D + "compare_event_tune_final.csv", index=False)
pd.concat(sweeps).to_csv(D + "compare_event_tune_dev_sweep.csv", index=False)
cols = ["model", "seeds", "rule", "threshold", "dev_ap", "ap", "precision", "recall", "f1",
        "detected", "events", "episode_precision", "event_recall", "event_f1", "false_eps_per_cy", "csi"]
print(res[cols].round(3).to_string(index=False))
