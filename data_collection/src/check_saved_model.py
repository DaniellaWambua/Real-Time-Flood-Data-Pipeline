import json
import numpy as np, pandas as pd
from sequences import make_windows
from lstm_common import make_model

# Loads the saved model folder fresh, checks its 2024-2025 scores against the event_train.py "eventweight" scores
# the model was chosen from, and writes models/flood_lstm/evaluation.json, the figures the LSTM page quotes.
# Day-level counts use known labels only. Events and alarm episodes follow event_evaluate.py: an event is detected
# by an alarm in the same catchment from one day before it to one day after it, and an alarm episode (consecutive
# alarm days, unknown days included) is false when it overlaps no such event window.
# Usage: check_saved_model.py [full|fast]
import sys
KIND = sys.argv[1] if len(sys.argv) > 1 else "full"
D = "data_collection/data/08_model_ready/"
M = {"full": "models/flood_lstm/", "fast": "models/flood_lstm_fast/"}[KIND]
REF = {"full": "event_train_final_scores_eventweight_s0-7.csv",
       "fast": "event_train_final_scores_eventweight_no_rain_mm_s0-7.csv"}[KIND]
DAY = pd.Timedelta(days=1)
TEST = [2024, 2025]
CATCHMENT_YEARS = 3 * len(TEST)
NAMES = {"nairobi": "Nairobi River", "ngong": "Ngong", "mathare": "Mathare"}
cfg = json.load(open(M + "config.json"))
if cfg.get("tuned_in"):  # v3 and later: compare with the scores the Colab tuning notebook saved
    REF = f"final_tuning/final_scores_{KIND}.csv"
mu, sd = np.array(cfg["mean"]), np.array(cfg["std"])

X, meta = make_windows(path=D + cfg["labels"], t=cfg["window"])
from sequences import SEQ_FEATS, CATCHMENTS
ALL = SEQ_FEATS + [f"is_{c}" for c in CATCHMENTS]
X = X[:, :, [ALL.index(f) for f in cfg["features"]]]
va = meta["year"].isin(TEST).values
days = meta.loc[va, ["catchment", "date", "label_status", "event_id"]].reset_index(drop=True)
Xva = ((X[va] - mu) / sd).astype("float32")
for seed in cfg["seeds"]:
    model = make_model(X.shape[2], cfg["window"], cfg.get("units", 32), cfg.get("dropout", 0.3))
    model.load_weights(M + f"lstm_raw_seed{seed}.weights.h5")
    days[f"s{seed}"] = model.predict(Xva, verbose=0).ravel()
days["score"] = days[[f"s{s}" for s in cfg["seeds"]]].mean(axis=1)

ref = pd.read_csv(D + REF, parse_dates=["date"])
ref = ref.groupby(["catchment", "date"], as_index=False)["score"].mean().rename(columns={"score": "ref"})
chk = days.merge(ref, on=["catchment", "date"])
print("rows compared", len(chk), "max difference from the chosen scores", round(float((chk["score"] - chk["ref"]).abs().max()), 5))


def ap(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return float(np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(y) + 1)[last]))


ev = (days[days["label_status"] == "flood"].groupby("event_id")
      .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max")))
known = days[days["label_status"].isin(["flood", "no_flood"])]
yk, sk = known["label_status"].eq("flood").values, known["score"].values


def measure(thr):
    a = sk >= thr
    tp, fp, fn = int((a & yk).sum()), int((a & ~yk).sum()), int((~a & yk).sum())
    alarms = days[days["score"] >= thr]
    det = sum(bool(((alarms["catchment"] == e.catchment) & (alarms["date"] >= e.start - DAY) &
                    (alarms["date"] <= e.end + DAY)).any()) for e in ev.itertuples())
    eps = false_eps = 0
    for c, x in alarms.sort_values("date").groupby("catchment"):
        evc = ev[ev["catchment"] == c]
        for _, ep in x.groupby((x["date"].diff() != DAY).cumsum()):
            eps += 1
            false_eps += not ((evc["start"] - DAY <= ep["date"].max()) & (evc["end"] + DAY >= ep["date"].min())).any()
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn)
    er = det / len(ev)
    ep_p = (eps - false_eps) / eps if eps else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": int((~a & ~yk).sum()), "precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0, "events_detected": det, "event_recall": er,
            "alarm_episodes": eps, "false_episodes": false_eps, "event_precision": ep_p,
            "event_f1": 2 * ep_p * er / (ep_p + er) if ep_p + er else 0.0,
            "flagged_days": int((days["score"] >= thr).sum())}


thr = cfg["threshold"]
m = measure(thr)
flagged = days[days["score"] >= thr]
evaluation = {
    "model": f"{cfg.get('name', 'lstm_raw')} {cfg['version']}",
    "training": cfg.get("training", "class-weighted"),
    "threshold": thr,
    "method": ("Scored by the saved model (eight-seed mean) over 2024-2025 and compared against the audited labels in "
               "features_daily_audited.csv. Precision, recall and F1 count only days whose label is known; days labelled "
               "'unknown' are left out of those counts and reported as flagged_on_unlabelled_days. An event is detected "
               "when a flag falls in the same catchment from one day before it to one day after it. An alarm episode is a "
               "run of consecutive flagged days; it is false when it overlaps no event window. Event precision is the "
               "share of alarm episodes that are not false."),
    "test_period": [f"{TEST[0]}-01-01", f"{TEST[-1]}-12-31"],
    "train_years": cfg["train_years"],
    "days_scored": len(days),
    "days_with_label": len(known),
    "flood_days": int(yk.sum()),
    "true_positives": m["tp"], "false_positives": m["fp"], "false_negatives": m["fn"], "true_negatives": m["tn"],
    "flagged_total": m["flagged_days"],
    "flagged_on_unlabelled_days": int(flagged["label_status"].eq("unknown").sum()),
    "precision": round(m["precision"], 3), "recall": round(m["recall"], 3), "f1": round(m["f1"], 3),
    "average_precision": round(ap(yk, sk), 3),
    "events_total": len(ev), "events_detected": m["events_detected"], "event_recall": round(m["event_recall"], 3),
    "alarm_episodes": m["alarm_episodes"], "false_alarm_episodes": m["false_episodes"],
    "event_precision": round(m["event_precision"], 3), "event_f1": round(m["event_f1"], 3),
    "false_alarms_per_catchment_year": round(m["fp"] / CATCHMENT_YEARS, 2),
    "false_episodes_per_catchment_year": round(m["false_episodes"] / CATCHMENT_YEARS, 2),
    "flagged_by_catchment": {NAMES[c]: int(n) for c, n in flagged["catchment"].value_counts().items()},
    "computed_on": pd.Timestamp.today().strftime("%Y-%m-%d"),
    "computed_by": "data_collection/src/check_saved_model.py from the saved weights",
    "operating_points": {
        "note": ("Same scores, different flag lines, measured on the same held-out days. The deployed line was chosen on "
                 "the development years for the best day-level F1; the rest are for the write-up, not used by the system."),
        "points": []},
}
for t in sorted({thr, 0.6, 0.5, 0.4, 0.3}, reverse=True):
    q = measure(t)
    point = {"threshold": t, "precision": round(q["precision"], 3), "recall": round(q["recall"], 3),
             "f1": round(q["f1"], 3), "events_detected": q["events_detected"],
             "event_precision": round(q["event_precision"], 3), "event_f1": round(q["event_f1"], 3),
             "flagged_days": q["flagged_days"], "alarm_share": round(q["flagged_days"] / len(days), 3)}
    if t == thr:
        point["deployed"] = True
    evaluation["operating_points"]["points"].append(point)
with open(M + "evaluation.json", "w") as f:
    json.dump(evaluation, f, indent=2)
print(json.dumps({k: evaluation[k] for k in ("precision", "recall", "f1", "average_precision", "events_detected",
                                             "event_recall", "event_precision", "event_f1",
                                             "false_episodes_per_catchment_year")}, indent=1))
