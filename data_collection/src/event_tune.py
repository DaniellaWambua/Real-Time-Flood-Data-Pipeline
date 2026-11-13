import numpy as np, pandas as pd

# Chooses the alarm threshold on the development years by an event-level rule, then applies it once to
# 2024-2025. The rule is fixed before looking: maximise the critical success index (events detected divided by
# events plus false alarm episodes), pooled over the three development folds; ties go to the higher threshold.
# Development scores: frozen lstm_raw, target today, eight-seed mean, trained on audited labels
# (placematch_dev_scores_lstm_raw_audited_s0-7.csv; folds 2015-18 -> 2019, 2015-20 -> 2021-22, 2015-22 -> 2023).
# Final scores: the deployed model, trained 2015-2023, scored on 2024-2025. Definitions as event_evaluate.py.
D = "data_collection/data/08_model_ready/"
DAY = pd.Timedelta(days=1)
GRID = np.round(np.arange(0.10, 0.901, 0.005), 3)
lab = pd.read_csv(D + "features_daily_audited.csv", parse_dates=["date"])[["catchment", "date", "label_status", "event_id"]]


def prepare(scores, group):
    m = scores.merge(lab, on=["catchment", "date"])
    parts = []
    for g, d in m.groupby(group):
        ev = (d[d["label_status"] == "flood"].groupby("event_id")
              .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max")))
        parts.append((d, ev))
    return parts


def counts(parts, thr):
    n = det = eps = false_eps = 0
    for d, ev in parts:
        alarms = d[d["score"] >= thr]
        for e in ev.itertuples():
            a = alarms[alarms["catchment"] == e.catchment]
            det += bool(((a["date"] >= e.start - DAY) & (a["date"] <= e.end + DAY)).any())
        n += len(ev)
        for c, a in alarms.sort_values("date").groupby("catchment"):
            evc = ev[ev["catchment"] == c]
            for _, ep in a.groupby((a["date"].diff() != DAY).cumsum()):
                eps += 1
                false_eps += not ((evc["start"] - DAY <= ep["date"].max()) & (evc["end"] + DAY >= ep["date"].min())).any()
    return {"events": n, "detected": det, "episodes": eps, "false_episodes": false_eps,
            "event_recall": det / n, "false_alarm_ratio": false_eps / eps if eps else np.nan,
            "csi": det / (n + false_eps)}


dev = pd.read_csv(D + "placematch_dev_scores_lstm_raw_audited_s0-7.csv", parse_dates=["date"])
dev = dev.groupby(["val", "catchment", "date"], as_index=False)["score"].mean()
dev_parts = prepare(dev, "val")
sweep = pd.DataFrame([{"threshold": t, **counts(dev_parts, t)} for t in GRID])
best = sweep.sort_values(["csi", "threshold"], ascending=[False, False]).iloc[0]
sweep.to_csv(D + "event_tune_dev_sweep.csv", index=False)

fin = pd.concat([pd.read_csv(D + f"retrain_final_scores_frozen_lstm_audited_s{r}.csv", parse_dates=["date"])
                 for r in ("0-2", "3-7")])
fin = fin[(fin["model"] == "lstm_raw") & (fin["target"] == "today")]
fin = fin.groupby(["catchment", "date"], as_index=False)["score"].mean().assign(split="final")
fin_parts = prepare(fin, "split")
rows = []
for name, t in [("deployed", 0.555), ("event-tuned", float(best["threshold"]))]:
    rows.append({"threshold": t, "choice": name, "dev_csi": counts(dev_parts, t)["csi"], **counts(fin_parts, t)})
res = pd.DataFrame(rows)
res.to_csv(D + "event_tune_final.csv", index=False)
print("development sweep, top 8 by CSI:")
print(sweep.sort_values(["csi", "threshold"], ascending=[False, False]).head(8).round(3).to_string(index=False))
print("\nchosen threshold:", best["threshold"])
print("\n2024-2025, applied once:")
print(res.round(3).to_string(index=False))
