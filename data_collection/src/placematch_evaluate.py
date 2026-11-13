import numpy as np, pandas as pd

# Compares lstm_raw trained on audited labels with lstm_raw trained on place-matched labels.
# Both are judged against the same audited development-fold labels (identical to the place-matched
# labels in 2019 and 2021-2023). Eight-seed mean score per day; paired day bootstrap for the differences.
D = "data_collection/data/08_model_ready/"
THR = 0.555
B = 2000
DAY = pd.Timedelta(days=1)


# truth() and ap() copied from audit_evaluate.py, which runs its whole evaluation on import
def truth(path, which):
    df = pd.read_csv(path, parse_dates=["date"])
    col = "label_status" if which == "today" else "next_status"
    if which == "today":
        df["tdate"], df["teid"] = df["date"], df["event_id"]
    else:
        df["tdate"] = df["date"] + DAY
        df["teid"] = df.groupby("catchment")["event_id"].shift(-1)
    df = df[df[col].isin(["flood", "no_flood"])]
    return df.assign(y=(df[col] == "flood").astype(int))[["catchment", "date", "tdate", "teid", "y"]]


def ap(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(y) + 1)[last])



gold = truth(D + "features_daily_audited.csv", "today")


def ens(train):
    s = pd.read_csv(D + f"placematch_dev_scores_lstm_raw_{train}_s0-7.csv", parse_dates=["date"])
    return s.groupby(["val", "catchment", "date"], as_index=False)["score"].mean()


m = ens("audited").merge(ens("placematched"), on=["val", "catchment", "date"], suffixes=("_aud", "_pm"))
m = m.merge(gold, on=["catchment", "date"])  # labelled days only


def stats(y, s, teid):
    a = s >= THR
    tp = int((a & (y == 1)).sum())
    p = tp / max(a.sum(), 1)
    r = tp / max(y.sum(), 1)
    f = 2 * p * r / max(p + r, 1e-9)
    ev = pd.Series(a[y == 1]).groupby(teid[y == 1]).any()
    return {"AP": ap(y, s), "precision": p, "recall": r, "F1": f, "alarm_days": int(a.sum()),
            "events_hit": int(ev.sum()), "events": len(ev)}


rows = []
for name, g in [("pooled", m)] + [(str(v), g) for v, g in m.groupby("val")]:
    y, t = g["y"].values, g["teid"].values
    for col, lbl in [("score_aud", "audited-trained"), ("score_pm", "placematched-trained")]:
        rows.append({"fold": name, "model": lbl, "flood_days": int(y.sum()), **stats(y, g[col].values, t)})
res = pd.DataFrame(rows)
res.to_csv(D + "placematch_dev_results.csv", index=False)
print(res.round(3).to_string(index=False))

rng = np.random.default_rng(0)
y, sa, sp, t = m["y"].values, m["score_aud"].values, m["score_pm"].values, m["teid"].values
diffs = []
for _ in range(B):
    i = rng.integers(0, len(y), len(y))
    if y[i].sum() == 0:
        continue
    A, P = stats(y[i], sa[i], t[i]), stats(y[i], sp[i], t[i])
    diffs.append({k: P[k] - A[k] for k in ("AP", "precision", "recall", "F1")})
d = pd.DataFrame(diffs)
ci = pd.DataFrame({"mean_diff": d.mean(), "lo95": d.quantile(0.025), "hi95": d.quantile(0.975)})
ci.to_csv(D + "placematch_dev_bootstrap.csv")
print("\nplacematched minus audited, pooled development folds (95% bootstrap interval):")
print(ci.round(3).to_string())
print("\nmean absolute change in daily score:", round(float(np.abs(sp - sa).mean()), 4),
      "| days whose alarm flips:", int(((sa >= THR) != (sp >= THR)).sum()), "of", len(y))
