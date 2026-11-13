import sys
import numpy as np, pandas as pd

# Event-level evaluation of the deployed model (lstm_raw v1, eight-seed mean, frozen setting, trained 2015-2023)
# on 2024-2025 against the audited labels. A flood event is one event_id (consecutive flood days in a catchment).
# Alarms are scored days at or above the threshold, including days labelled unknown; consecutive alarm days in a
# catchment form one alarm episode.
#   detected  an alarm in the same catchment from one day before the event to one day after it
#   on time   an alarm on the day before or the first day of the event
#   false     an alarm episode that overlaps no event window (event start - 1 day to event end + 1 day)
# Usage: event_evaluate.py [threshold ...]   default 0.555 (deployed), 0.5, 0.4, 0.35
D = "data_collection/data/08_model_ready/"
DAY = pd.Timedelta(days=1)
THRESHOLDS = [float(t) for t in sys.argv[1:]] or [0.555, 0.5, 0.4, 0.35]
CATCHMENT_YEARS = 3 * 2

s = pd.concat([pd.read_csv(D + f"retrain_final_scores_frozen_lstm_audited_s{r}.csv", parse_dates=["date"])
               for r in ("0-2", "3-7")])
s = s[(s["model"] == "lstm_raw") & (s["target"] == "today")]
assert s["seed"].nunique() == 8
scores = s.groupby(["catchment", "date"], as_index=False)["score"].mean()
lab = pd.read_csv(D + "features_daily_audited.csv", parse_dates=["date"])[["catchment", "date", "label_status", "event_id"]]
m = scores.merge(lab, on=["catchment", "date"])
ev = (m[m["label_status"] == "flood"].groupby("event_id")
      .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max"), days=("date", "size")))


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def evaluate(thr):
    alarms = m[m["score"] >= thr]
    rows = []
    for eid, e in ev.iterrows():
        a = alarms[alarms["catchment"] == e.catchment]
        rows.append({"event_id": eid, "catchment": e.catchment, "start": e.start.date(), "days": e.days,
                     "detected": bool(((a["date"] >= e.start - DAY) & (a["date"] <= e.end + DAY)).any()),
                     "on_time": bool(((a["date"] >= e.start - DAY) & (a["date"] <= e.start)).any())})
    per_event = pd.DataFrame(rows)
    eps, false_eps = 0, 0
    for c, a in alarms.sort_values("date").groupby("catchment"):
        evc = ev[ev["catchment"] == c]
        for _, ep in a.groupby((a["date"].diff() != DAY).cumsum()):
            eps += 1
            lo, hi = ep["date"].min(), ep["date"].max()
            false_eps += not ((evc["start"] - DAY <= hi) & (evc["end"] + DAY >= lo)).any()
    det, n = int(per_event["detected"].sum()), len(per_event)
    lo, hi = wilson(det, n)
    return per_event, {"threshold": thr, "events": n, "detected": det, "event_recall": det / n,
                       "event_recall_lo95": lo, "event_recall_hi95": hi,
                       "on_time": int(per_event["on_time"].sum()), "alarm_days": len(alarms),
                       "alarm_episodes": eps, "false_episodes": false_eps,
                       "false_alarm_ratio": false_eps / eps if eps else np.nan,
                       "csi": det / (n + false_eps),
                       "false_episodes_per_catchment_year": false_eps / CATCHMENT_YEARS}


summary, deployed = [], None
for t in THRESHOLDS:
    pe, r = evaluate(t)
    summary.append(r)
    if deployed is None:
        deployed = pe
summary = pd.DataFrame(summary)
summary.to_csv(D + "event_final_results.csv", index=False)
deployed.to_csv(D + "event_final_per_event.csv", index=False)
print(summary.round(3).T.to_string())
print("\nat", THRESHOLDS[0], "by catchment")
print(deployed.groupby("catchment").agg(events=("detected", "size"), detected=("detected", "sum"), on_time=("on_time", "sum")).to_string())
print("\nby event length")
print(deployed.assign(length=np.where(deployed["days"] == 1, "1 day", "2+ days"))
      .groupby("length").agg(events=("detected", "size"), detected=("detected", "sum")).to_string())
