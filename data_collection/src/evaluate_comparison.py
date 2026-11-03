import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve
from comparison_setup import OUT

# Scores every saved per-day score file (dev folds, and the final test once it exists).
# Optional argument: a file prefix, e.g. tuned_ for the D10 tuning run.
PREFIX = sys.argv[1] if len(sys.argv) > 1 else ""
MODELS = ["rule_rain_3d", "rule_tuned", "forest", "boosting", "extra_trees", "lstm_raw", "lstm_log", "lstm_batches"]
PRIMARY = {"rule_rain_3d", "boosting", "lstm_raw"}  # decisions.md D8
SHARES = (0.03, 0.05, 0.10)
B = 1000
DAY = pd.Timedelta(days=1)
KEYS = ["target", "val", "catchment", "date"]


def ap(y, s):
    # average precision with tied scores treated as one threshold, as in sklearn
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    prec = tp / (np.arange(1, len(y) + 1)[last])
    return np.sum(np.diff(np.r_[0, tp / tp[-1]]) * prec)


def max_f1(y, s):
    # best day-level F1 over all thresholds, chosen in hindsight, so an upper bound
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    n = np.arange(1, len(y) + 1)[last]
    return np.max(2 * tp / (n + y.sum()))


def top5_hits(y, s):
    k = max(1, int(len(y) * 0.05))
    return y[np.argsort(-s, kind="mergesort")[:k]].sum()


def event_hits(g, q):
    # event_eval.py rule: alarm on the top q share of days, event hit if an alarm in the same catchment within 1 day
    alarms = g[g["score"] >= g["score"].quantile(1 - q)]
    ev = g[g["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                            start=("tdate", "min"), end=("tdate", "max"))
    hit = np.array([((alarms["catchment"] == e.catchment) & (alarms["tdate"] >= e.start - DAY) &
                     (alarms["tdate"] <= e.end + DAY)).any() for e in ev.itertuples()])
    return ev, hit, int((alarms["y"] == 0).sum())


def fold_stats(g):
    y, s = g["y"].values, g["score"].values
    v = g["val"].iloc[0]
    nyears = int(v[-4:]) - int(v[:4]) + 1
    r = {"days": len(y), "flood_days": int(y.sum()), "catchment_years": 3 * nyears,
         "ap": ap(y, s), "top5": top5_hits(y, s)}
    for q in SHARES:
        ev, hit, fd = event_hits(g, q)
        r["events"], r[f"det_{q}"], r[f"fd_{q}"] = len(ev), hit.sum(), fd
        if q == 0.05:
            r["ev_table"] = ev.assign(hit=hit)
    return r


def summarise(stats, pooled_ap):
    """stats: list over seeds of lists over folds. Returns seed-averaged metrics."""
    per_seed = []
    for seed_folds, pap in zip(stats, pooled_ap):
        t = {k: sum(f[k] for f in seed_folds) for k in ["days", "flood_days", "catchment_years", "top5", "events"]
             + [f"det_{q}" for q in SHARES] + [f"fd_{q}" for q in SHARES]}
        m = {"avg_precision": pap, "recall_top5pct": t["top5"] / t["flood_days"]}
        for q in SHARES:
            m[f"event_recall_{int(q*100)}pct"] = t[f"det_{q}"] / t["events"]
            m[f"false_days_per_cy_{int(q*100)}pct"] = t[f"fd_{q}"] / t["catchment_years"]
        per_seed.append(m)
    ps = pd.DataFrame(per_seed)
    out = {"days": t["days"], "flood_days": t["flood_days"], "events": t["events"],
           "base_rate": t["flood_days"] / t["days"], "n_seeds": len(ps)}
    out.update(ps.mean().to_dict())
    out["ap_seed_sd"] = ps["avg_precision"].std(ddof=0)
    return out


def bootstrap(group):
    """Block bootstrap over catchment-months for the pooled rows of one target and split."""
    base = group[group["model"] == "rule_rain_3d"].sort_values(KEYS).reset_index(drop=True)
    block = base["catchment"] + base["tdate"].dt.strftime("%Y-%m")
    codes, uniq = pd.factorize(block)
    idx = [np.where(codes == i)[0] for i in range(len(uniq))]
    rng = np.random.default_rng(0)
    draws = rng.integers(0, len(uniq), (B, len(uniq)))
    rows = [np.concatenate([idx[i] for i in d]) for d in draws]
    counts = np.array([np.bincount(d, minlength=len(uniq)) for d in draws])
    y = base["y"].values
    res = {}
    for model, gm in group.groupby("model"):
        aps, recs = [], []
        for seed, gs in gm.groupby("seed"):
            gs = gs.sort_values(KEYS).reset_index(drop=True)
            assert (gs[KEYS].values == base[KEYS].values).all(), "row sets differ between models"
            s = gs["score"].values
            aps.append([ap(y[r], s[r]) for r in rows])
            evs, hits = [], []
            for _, gf in gs.groupby("val"):
                ev, hit, _ = event_hits(gf, 0.05)
                evs.append(ev), hits.append(hit)
            ev, hit = pd.concat(evs), np.concatenate(hits)
            eb = pd.Index(uniq).get_indexer(ev["catchment"] + ev["start"].dt.strftime("%Y-%m"))
            n = counts[:, eb]
            recs.append((n * hit).sum(1) / n.sum(1))
        res[model] = (np.mean(aps, 0), np.mean(recs, 0))
    out = {}
    for model, (a, r) in res.items():
        out[model] = {"ap_ci_low": np.percentile(a, 2.5), "ap_ci_high": np.percentile(a, 97.5),
                      "event_recall_5pct_ci_low": np.percentile(r, 2.5),
                      "event_recall_5pct_ci_high": np.percentile(r, 97.5)}
        if model != "rule_rain_3d":
            d = a - res["rule_rain_3d"][0]
            out[model].update({"ap_minus_rule_ci_low": np.percentile(d, 2.5),
                               "ap_minus_rule_ci_high": np.percentile(d, 97.5)})
    return out


def pr_plot(scores, split, path):
    colors = {"forest": "#2a78d6", "boosting": "#eb6834", "extra_trees": "#1baf7a",
              "lstm_raw": "#eda100", "lstm_log": "#e87ba4", "lstm_batches": "#008300", "rule_rain_3d": "#0b0b0b",
              "rule_tuned": "#6250d6"}
    styles = {"rule_rain_3d": "--", "rule_tuned": "--", "lstm_raw": "-.", "lstm_log": ":", "lstm_batches": (0, (5, 1, 1, 1, 1, 1))}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, which in zip(axes, ["today", "tomorrow"]):
        g = scores[(scores["target"] == which) & (scores["seed"] == 0)]
        for model in MODELS:
            gm = g[g["model"] == model]
            if gm.empty:
                continue
            p, r, _ = precision_recall_curve(gm["y"], gm["score"])
            ax.plot(r, p, color=colors[model], ls=styles.get(model, "-"), lw=2.6 if model in PRIMARY else 1.4,
                    label=model + (" (primary)" if model in PRIMARY else ""))
        br = g[g["model"] == "rule_rain_3d"]["y"].mean()
        ax.axhline(br, color="#898781", lw=1, label=f"base rate {br:.3f}")
        ax.set_title(f"Target: {which}", fontsize=11, loc="left", color="#0b0b0b")
        ax.set_xlabel("Recall (flood days)", color="#52514e")
        ax.grid(color="#e1e0d9", lw=0.6)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        for sp in ["left", "bottom"]:
            ax.spines[sp].set_color("#c3c2b7")
        ax.tick_params(colors="#898781")
    axes[0].set_ylabel("Precision", color="#52514e")
    axes[0].set_ylim(0, 1.02)
    for ax in axes:
        ax.legend(frameon=False, fontsize=9, loc="upper right")
    title = "Development folds pooled (2019, 2021-2022, 2023)" if split == "dev" else "Final test 2024-2025"
    fig.suptitle(f"Precision-recall, {title}, seed 0", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#fcfcfb")
    plt.close(fig)


def event_plot(table, split, path):
    ramp = {0.03: "#86b6ef", 0.05: "#2a78d6", 0.10: "#104281"}
    t = table[table["val"] == ("pooled_dev" if split == "dev" else "2024-2025")]
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.4), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for col, which in enumerate(["today", "tomorrow"]):
        tt = t[t["target"] == which].set_index("model").reindex([m for m in MODELS if m in set(t["model"])])
        x = np.arange(len(tt))
        for i, q in enumerate(SHARES):
            pct = int(q * 100)
            kw = dict(width=0.26, color=ramp[q], edgecolor="#fcfcfb", linewidth=2, label=f"{pct}% of days alarmed")
            axes[0, col].bar(x + (i - 1) * 0.27, tt[f"event_recall_{pct}pct"], **kw)
            axes[1, col].bar(x + (i - 1) * 0.27, tt[f"false_days_per_cy_{pct}pct"], **kw)
        axes[0, col].set_title(f"Target: {which}", fontsize=11, loc="left")
        axes[0, col].set_ylim(0, 1)
        axes[1, col].set_xticks(x, tt.index, rotation=20, fontsize=9)
        for ax in axes[:, col]:
            ax.grid(axis="y", color="#e1e0d9", lw=0.6)
            ax.set_axisbelow(True)
            for sp in ["top", "right"]:
                ax.spines[sp].set_visible(False)
            for sp in ["left", "bottom"]:
                ax.spines[sp].set_color("#c3c2b7")
            ax.tick_params(colors="#52514e")
    axes[0, 0].set_ylabel("Event recall (within 1 day)", color="#52514e")
    axes[1, 0].set_ylabel("False alarm days\nper catchment-year", color="#52514e")
    axes[0, 1].legend(frameon=False, fontsize=9, loc="upper right")
    n = int(t["events"].iloc[0]) if len(t) else 0
    title = "Development folds pooled" if split == "dev" else "Final test 2024-2025"
    fig.suptitle(f"Event recall against false alarms, {title} ({n} events today target), mean of seeds",
                 x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor="#fcfcfb")
    plt.close(fig)


def xy(g):
    return g["y"].values, g["score"].values


rows = []
for split in ["dev", "final"]:
    files = [f"{OUT}/{PREFIX}{split}_scores_{k}.csv" for k in ["trees", "lstm"]]
    files = [f for f in files if os.path.exists(f)]
    if not files:
        continue
    scores = pd.concat([pd.read_csv(f, parse_dates=["date", "tdate"], dtype={"val": str}) for f in files])
    for which in ["today", "tomorrow"]:
        st = scores[scores["target"] == which]
        ci = bootstrap(st)
        for model in [m for m in MODELS if m in set(st["model"])]:
            sm = st[st["model"] == model]
            seeds = sorted(sm["seed"].unique())
            folds = sorted(sm["val"].unique())
            per = {seed: [fold_stats(sm[(sm["seed"] == seed) & (sm["val"] == v)]) for v in folds] for seed in seeds}
            for i, v in enumerate(folds):
                if len(folds) > 1:
                    r = summarise([[per[s][i]] for s in seeds], [per[s][i]["ap"] for s in seeds])
                    r["max_f1_day"] = np.mean([max_f1(*xy(sm[(sm["seed"] == s) & (sm["val"] == v)])) for s in seeds])
                    rows.append({"target": which, "split": split, "val": v, "model": model, **r})
            pooled = [ap(sm[sm["seed"] == s]["y"].values, sm[sm["seed"] == s]["score"].values) for s in seeds]
            r = summarise([per[s] for s in seeds], pooled)
            r["max_f1_day"] = np.mean([max_f1(*xy(sm[sm["seed"] == s])) for s in seeds])
            r["ap_fold_mean"] = np.mean([[f["ap"] for f in per[s]] for s in seeds])
            rows.append({"target": which, "split": split, "val": "pooled_dev" if split == "dev" else folds[0],
                         "model": model, **r, **ci[model]})

res = pd.DataFrame(rows)
res["ap_lift"] = res["avg_precision"] / res["base_rate"]
res["ap_lift_ci_low"] = res["ap_ci_low"] / res["base_rate"]
res["ap_lift_ci_high"] = res["ap_ci_high"] / res["base_rate"]
res.insert(4, "role", np.where(res["model"].isin(PRIMARY), "primary", "secondary"))
cols = ["target", "split", "val", "model", "role", "n_seeds", "days", "flood_days", "events", "base_rate",
        "avg_precision", "ap_seed_sd", "ap_lift", "ap_lift_ci_low", "ap_lift_ci_high", "ap_fold_mean",
        "ap_ci_low", "ap_ci_high", "ap_minus_rule_ci_low",
        "ap_minus_rule_ci_high", "max_f1_day", "recall_top5pct"] + \
       [f"{m}_{int(q*100)}pct" for q in SHARES for m in ["event_recall", "false_days_per_cy"]] + \
       ["event_recall_5pct_ci_low", "event_recall_5pct_ci_high"]
res = res[cols].round(3)
res.to_csv(f"{OUT}/{PREFIX}comparison_results.csv", index=False)

pd.set_option("display.width", 250)
show = ["target", "split", "val", "model", "role", "base_rate", "avg_precision", "ap_lift", "ap_seed_sd",
        "ap_fold_mean", "ap_ci_low", "ap_ci_high",
        "ap_minus_rule_ci_low", "ap_minus_rule_ci_high", "max_f1_day", "recall_top5pct",
        "event_recall_3pct", "event_recall_5pct", "event_recall_10pct", "false_days_per_cy_5pct"]
print(res[show].to_string(index=False))

for split in res["split"].unique():
    sc = pd.concat([pd.read_csv(f, parse_dates=["date", "tdate"], dtype={"val": str})
                    for f in [f"{OUT}/{PREFIX}{split}_scores_{k}.csv" for k in ["trees", "lstm"]] if os.path.exists(f)])
    pr_plot(sc, split, f"{OUT}/{PREFIX}comparison_pr_{split}.png")
    event_plot(res, split, f"{OUT}/{PREFIX}comparison_events_{split}.png")
