import numpy as np, pandas as pd

# Compares the event_train.py variants. For each: eight-seed mean score per day, threshold chosen on the
# development folds by best day-level F1 (candidates are development-score quantiles 0.90 to 0.999, ties to the
# higher threshold), then applied once to 2024-2025. All variants are judged against the same audited day labels
# and the same event definitions as event_evaluate.py.
D = "data_collection/data/08_model_ready/"
DAY = pd.Timedelta(days=1)
QS = np.round(np.arange(0.90, 0.9991, 0.001), 3)
import os
VARIANTS = [v for v in ["day", "eventweight", "window", "anyday", "eventweight_no_rain_mm"]
            if os.path.exists(f"data_collection/data/08_model_ready/event_train_dev_scores_{v}_s0-7.csv")]
# eventweight_no_rain_mm: the event-weighted model without CHIRPS (rain_mm), which does not wait ~40 days for it
lab = pd.read_csv(D + "features_daily_audited.csv", parse_dates=["date"])[["catchment", "date", "label_status", "event_id"]]


def prepare(d):
    m = d.merge(lab, on=["catchment", "date"])
    parts = []
    for _, g in m.groupby("val"):
        ev = (g[g["label_status"] == "flood"].groupby("event_id")
              .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max"), days=("date", "size")))
        known = g[g["label_status"].isin(["flood", "no_flood"])]
        parts.append((g, ev, known["label_status"].eq("flood").values, known["score"].values))
    return parts


def ap(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(y) + 1)[last])


def stats(parts, thr, cy):
    n = det = det1 = n1 = eps = false_eps = tp = fp = fn = 0
    for g, ev, y, s in parts:
        a = s >= thr
        tp += int((a & y).sum()); fp += int((a & ~y).sum()); fn += int((~a & y).sum())
        alarms = g[g["score"] >= thr]
        for e in ev.itertuples():
            x = alarms[alarms["catchment"] == e.catchment]
            hit = bool(((x["date"] >= e.start - DAY) & (x["date"] <= e.end + DAY)).any())
            det += hit
            if e.days == 1:
                n1 += 1; det1 += hit
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
            "events": n, "detected": det, "one_day_detected": f"{det1}/{n1}", "multi_day_detected": f"{det - det1}/{n - n1}",
            "event_recall": er, "episodes": eps, "false_episodes": false_eps, "episode_precision": ep_p,
            "event_f1": 2 * ep_p * er / (ep_p + er) if ep_p + er else 0.0, "false_eps_per_cy": false_eps / cy}


rows = []
for v in VARIANTS:
    dev = pd.read_csv(D + f"event_train_dev_scores_{v}_s0-7.csv", parse_dates=["date"])
    fin = pd.read_csv(D + f"event_train_final_scores_{v}_s0-7.csv", parse_dates=["date"])
    dev = dev.groupby(["val", "catchment", "date"], as_index=False)["score"].mean()
    fin = fin.groupby(["val", "catchment", "date"], as_index=False)["score"].mean()
    dp, fp_ = prepare(dev), prepare(fin)
    grid = np.unique(np.quantile(dev["score"], QS))
    sw = pd.DataFrame([{"threshold": t, **stats(dp, t, 12)} for t in grid])
    b = sw.sort_values(["f1", "threshold"], ascending=[False, False]).iloc[0]
    ydev = np.concatenate([p[2] for p in dp]); sdev = np.concatenate([p[3] for p in dp])
    yfin = np.concatenate([p[2] for p in fp_]); sfin = np.concatenate([p[3] for p in fp_])
    rows.append({"variant": v, "threshold": round(float(b["threshold"]), 4), "dev_ap": ap(ydev, sdev),
                 "dev_f1": b["f1"], "dev_event_recall": b["event_recall"], "ap": ap(yfin, sfin), **stats(fp_, b["threshold"], 6)})
res = pd.DataFrame(rows)
res.to_csv(D + "event_train_results.csv", index=False)
print(res.round(3).T.to_string())
