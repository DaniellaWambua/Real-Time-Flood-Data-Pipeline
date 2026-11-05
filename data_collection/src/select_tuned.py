import glob
import pandas as pd
from comparison_setup import OUT

# Pick one setting per model family from the development-fold search (decisions.md D10).
# Six numbers per setting: mean-of-folds AP, pooled event recall at 5% and pooled top-5% recall, for both targets.
# Preferred: settings at least as good as the frozen setting (00) on all six; among those, best mean rank.
# If none qualifies, the best mean rank is taken and the trade-off is flagged.
runs = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{OUT}/tuning/runs_*.csv"))])
seed = runs.groupby(["family", "config_id", "config", "target", "seed"]).agg(
    ap=("ap", "mean"), det5=("det5", "sum"), events=("events", "sum"),
    top5_hits=("top5_hits", "sum"), floods=("floods", "sum")).reset_index()
seed["event_recall_5pct"] = seed["det5"] / seed["events"]
seed["recall_top5pct"] = seed["top5_hits"] / seed["floods"]
agg = seed.groupby(["family", "config_id", "config", "target"])[["ap", "event_recall_5pct", "recall_top5pct"]].mean()
wide = agg.unstack("target")
wide.columns = [f"{m}_{t}" for m, t in wide.columns]
wide = wide.reset_index()
METRICS = [c for c in wide.columns if c.startswith(("ap_", "event_", "recall_"))]

picked = []
for fam, g in wide.groupby("family"):
    g = g.copy()
    base = g[g["config_id"].str.endswith("_00")][METRICS].iloc[0]
    g["n_metrics_better"] = (g[METRICS] > base + 1e-9).sum(1)
    g["n_metrics_worse"] = (g[METRICS] < base - 1e-9).sum(1)
    g["mean_rank"] = g[METRICS].rank(ascending=False).mean(1)
    g["improves_all"] = (g["n_metrics_worse"] == 0) & (g["n_metrics_better"] > 0)
    pool = g[g["improves_all"]] if g["improves_all"].any() else g
    best = pool.sort_values(["mean_rank", "config_id"]).iloc[0]
    picked.append({**best.to_dict(), **{f"frozen_{m}": base[m] for m in METRICS}})
    wide.loc[g.index, ["n_metrics_better", "n_metrics_worse", "mean_rank", "improves_all"]] = \
        g[["n_metrics_better", "n_metrics_worse", "mean_rank", "improves_all"]]

wide.round(3).to_csv(f"{OUT}/tuning/all_settings.csv", index=False)
sel = pd.DataFrame(picked).round(3)
sel.to_csv(f"{OUT}/tuning/selected.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 120)
for _, r in sel.iterrows():
    print(f"\n{r['family']}: {r['config_id']} {r['config']}  improves_all={r['improves_all']}  "
          f"better on {r['n_metrics_better']}, worse on {r['n_metrics_worse']} of 6")
    print("  " + "  ".join(f"{m} {r['frozen_' + m]:.3f}->{r[m]:.3f}" for m in METRICS))
