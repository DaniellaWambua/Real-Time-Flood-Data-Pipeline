import os, sys
import numpy as np, pandas as pd

# Scores the label audit comparison (decisions.md D11). Usage: audit_evaluate.py [dev|final]
# Every model trained on either label set is judged against either label set, so the effect of
# cleaner training labels and the effect of cleaner evaluation labels can be told apart.
D = "data_collection/data/08_model_ready/"
LABELS = {"original": D + "features_daily.csv", "audited": D + "features_daily_audited.csv"}
SHARES = (0.03, 0.05, 0.10)
DAY = pd.Timedelta(days=1)
B = 1000
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "dev"  # dev, or final (2024-2025, already seen in D9 and D10)
NYEARS = 4 if SPLIT == "dev" else 2  # 2019, 2021, 2022, 2023 or 2024, 2025


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


def max_f1(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return np.max(2 * tp / (np.arange(1, len(y) + 1)[last] + y.sum()))


def warn_stats(g, q):
    """One fold. Alarm on the top q share of labelled days (as event_eval.py). Day-level counts, event
    detection within 1 day in the same catchment, and alarm episodes (runs of consecutive alarm days)."""
    alarms = g[g["score"] >= g["score"].quantile(1 - q)]
    ev = g[g["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                            start=("tdate", "min"), end=("tdate", "max"))
    det = sum(((alarms["catchment"] == e.catchment) & (alarms["tdate"] >= e.start - DAY) &
               (alarms["tdate"] <= e.end + DAY)).any() for e in ev.itertuples())
    eps, false_eps = 0, 0
    for c, a in alarms.sort_values("tdate").groupby("catchment"):
        run = (a["tdate"].diff() != DAY).cumsum()
        evc = ev[ev["catchment"] == c]
        for _, ep in a.groupby(run):
            eps += 1
            lo, hi = ep["tdate"].min(), ep["tdate"].max()
            false_eps += not ((evc["start"] - DAY <= hi) & (evc["end"] + DAY >= lo)).any()
    return {"alarm_days": len(alarms), "tp_days": int(alarms["y"].sum()), "flood_days": int(g["y"].sum()),
            "events": len(ev), "detected": int(det), "false_days": int((alarms["y"] == 0).sum()),
            "episodes": eps, "false_episodes": false_eps}


def evaluate(g, nyears):
    """g: one seed, all three folds, labelled rows of one evaluation label set."""
    y, s = g["y"].values, g["score"].values
    r = {"days": len(y), "flood_days": int(y.sum()), "base_rate": y.mean(), "ap": ap(y, s), "max_f1": max_f1(y, s)}
    for q in SHARES:
        t = pd.DataFrame([warn_stats(gf, q) for _, gf in g.groupby("val")]).sum()
        p = t.tp_days / t.alarm_days
        rc = t.tp_days / t.flood_days
        k = int(q * 100)
        r.update({f"precision_{k}": p, f"recall_{k}": rc, f"f1_{k}": 2 * p * rc / (p + rc) if p + rc else 0.0,
                  f"events_{k}": t.events, f"pod_{k}": t.detected / t.events,
                  f"far_{k}": t.false_episodes / t.episodes,
                  f"csi_{k}": t.detected / (t.events + t.false_episodes),
                  f"false_days_per_cy_{k}": t.false_days / (3 * nyears)})
    return r


scores = pd.concat([pd.read_csv(D + f"audit_{SPLIT}_scores_{f}.csv", parse_dates=["date"])
                    for f in ("trees", "lstm") if os.path.exists(D + f"audit_{SPLIT}_scores_{f}.csv")])
scores["val"] = scores["val"].astype(str)
rows, boot = [], []
for which in ["today", "tomorrow"]:
    T = {k: truth(p, which) for k, p in LABELS.items()}
    sw = scores[scores["target"] == which]
    for (tl, model), gm in sw.groupby(["train_labels", "model"]):
        for el, tt in T.items():
            per_seed = []
            for seed, gs in gm.groupby("seed"):
                g = gs.merge(tt, on=["catchment", "date"], how="inner")
                per_seed.append(evaluate(g, NYEARS))
            ps = pd.DataFrame(per_seed)
            out = {"target": which, "model": model, "train_labels": tl, "eval_labels": el, "n_seeds": len(ps)}
            out.update(ps.mean().to_dict())
            out["ap_seed_sd"] = ps["ap"].std(ddof=0)
            rows.append(out)

res = pd.DataFrame(rows)
res.to_csv(D + f"audit_{SPLIT}_results.csv", index=False)

# Paired block bootstrap over catchment-months: audited-trained/audited-judged minus original/original.
for which in ["today", "tomorrow"]:
    T = {k: truth(p, which) for k, p in LABELS.items()}
    sw = scores[scores["target"] == which]
    blocks = pd.concat(T.values())[["catchment", "date"]].drop_duplicates()
    blocks = sorted((blocks["catchment"] + blocks["date"].dt.strftime("%Y-%m")).unique())
    rng = np.random.default_rng(0)
    draws = rng.integers(0, len(blocks), (B, len(blocks)))
    for model, gm in sw.groupby("model"):
        diffs = []
        prep = {}
        for tl in LABELS:
            mean_s = gm[gm["train_labels"] == tl].groupby(["catchment", "date"])["score"].mean().reset_index()
            g = mean_s.merge(T[tl], on=["catchment", "date"])
            b = pd.Index(blocks).get_indexer(g["catchment"] + g["date"].dt.strftime("%Y-%m"))
            idx = [np.where(b == i)[0] for i in range(len(blocks))]
            prep[tl] = (g["y"].values, g["score"].values, idx)
        for d in draws:
            v = []
            for tl in LABELS:
                y, s, idx = prep[tl]
                r = np.concatenate([idx[i] for i in d])
                v.append(ap(y[r], s[r]) if y[r].sum() else np.nan)
            diffs.append(v[1] - v[0])
        diffs = np.array(diffs)
        boot.append({"target": which, "model": model, "ap_diff_ci_low": np.nanpercentile(diffs, 2.5),
                     "ap_diff_ci_high": np.nanpercentile(diffs, 97.5)})
pd.DataFrame(boot).to_csv(D + f"audit_{SPLIT}_bootstrap.csv", index=False)

show = ["ap", "max_f1", "precision_5", "recall_5", "f1_5", "pod_5", "far_5", "csi_5", "false_days_per_cy_5"]
for which in ["today", "tomorrow"]:
    print("\n", which)
    print(res[res["target"] == which].set_index(["model", "train_labels", "eval_labels"])[["flood_days"] + show].round(3).to_string())
print(pd.DataFrame(boot).round(3).to_string(index=False))
