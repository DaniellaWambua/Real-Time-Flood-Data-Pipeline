import glob, re, sys
import numpy as np, pandas as pd

# Scores the retraining comparison (decisions.md D13) with the metric functions of audit_evaluate.py.
# One row per run: split, target, setting, model, training labels, evaluation labels and seed set.
# LSTMs have rows for seeds 0-2, seeds 0-7 and the 8-seed ensemble (mean score per day).
# Choices are read from the development rows only. The final rows (2024-2025) were already seen in D9, D10
# and D12, so they are a secondary check and not an unseen test.
sys.argv = sys.argv[:1] + ["dev"]
exec(open("data_collection/src/audit_evaluate.py").read().split("scores = pd.concat")[0])
NOTE = {"dev": "development folds", "final": "2024-2025, already seen, not an unseen test"}
LSTMS = ["lstm_raw", "lstm_log", "lstm_batches"]


def wap(y, s, w):
    """AP for every bootstrap draw at once: w (draws x rows) counts how often each row is drawn.
    Equal to ap() on the concatenated resample, ties included."""
    o = np.argsort(-s, kind="mergesort")
    y, s, w = y[o], s[o], w[:, o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(w * y, axis=1)[:, last]
    n = np.cumsum(w, axis=1)[:, last]
    rec = tp / tp[:, -1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(n > 0, tp / n, 0.0)
    return np.sum(np.diff(np.c_[np.zeros(len(w)), rec], axis=1) * prec, axis=1)


def load_scores(split):
    parts = []
    for f in sorted(glob.glob(D + f"retrain_{split}_scores_*.csv")):
        parts.append(pd.read_csv(f, parse_dates=["date"], dtype={"val": str}))
    s = pd.concat(parts)
    assert not s.duplicated(["setting", "train_labels", "target", "model", "seed", "catchment", "date"]).any()
    # the rule has no training, so it must give the same scores in every run; keep one copy as the reference
    r = s[s["model"] == "rule_rain_3d"].pivot_table(index=["target", "catchment", "date"],
                                                    columns=["setting", "train_labels"], values="score")
    assert (r.nunique(axis=1) == 1).all(), "rule scores differ between runs"
    return s


def run_sets(s):
    """(setting, model, train_labels, seed set, scores) for every run. The tuned rule keeps rain_sum_3d (D10),
    so it is the frozen rule and is listed once, with train_labels none."""
    out = []
    rule = s[(s["model"] == "rule_rain_3d") & (s["setting"] == "frozen") & (s["train_labels"] == "original")]
    out.append(("frozen", "rule_rain_3d", "none", "0", rule))
    for (setting, model, tl), g in s[s["model"] != "rule_rain_3d"].groupby(["setting", "model", "train_labels"]):
        seeds = sorted(g["seed"].unique())
        out.append((setting, model, tl, "0-2", g[g["seed"].isin([0, 1, 2])]))
        if model in LSTMS and seeds == list(range(8)):
            out.append((setting, model, tl, "0-7", g))
            ens = g.groupby(["target", "val", "catchment", "date"])["score"].mean().reset_index().assign(seed=-1)
            out.append((setting, model, tl, "ensemble 0-7", ens))
    return out


rows, seed_rows = [], []
for split, nyears in [("dev", 4), ("final", 2)]:
    if not glob.glob(D + f"retrain_{split}_scores_*.csv"):
        continue
    s = load_scores(split)
    runs = run_sets(s)
    for which in ["today", "tomorrow"]:
        T = {k: truth(p, which) for k, p in LABELS.items()}
        for el, tt in T.items():
            blocks = (tt["catchment"] + tt["date"].dt.strftime("%Y-%m"))
            uniq = sorted(blocks.unique())
            draws = np.random.default_rng(0).integers(0, len(uniq), (B, len(uniq)))
            counts = np.stack([np.bincount(d, minlength=len(uniq)) for d in draws])
            boot = {}
            for setting, model, tl, seeds, g in runs:
                g = g[g["target"] == which].merge(tt, on=["catchment", "date"], how="inner")
                per, b = [], []
                for seed, gs in g.groupby("seed"):
                    gs = gs.sort_values(["catchment", "date"]).reset_index(drop=True)
                    r = evaluate(gs, nyears)
                    r["ap_fold_mean"] = np.mean([ap(x["y"].values, x["score"].values) for _, x in gs.groupby("val")])
                    per.append(r)
                    w = counts[:, pd.Index(uniq).get_indexer(gs["catchment"] + gs["date"].dt.strftime("%Y-%m"))]
                    b.append(wap(gs["y"].values, gs["score"].values, w))
                    if seeds == "0-7":
                        seed_rows.append({"split": split, "target": which, "setting": setting, "model": model,
                                          "train_labels": tl, "eval_labels": el, "seed": seed, "ap": r["ap"]})
                ps = pd.DataFrame(per)
                boot[(setting, model, tl, seeds)] = np.mean(b, axis=0)
                out = {"split": split, "period": NOTE[split], "target": which, "setting": setting, "model": model,
                       "train_labels": tl, "eval_labels": el, "seeds": seeds, "n_seeds": len(ps)}
                out.update(ps.mean().to_dict())
                out.update({"ap_seed_sd": ps["ap"].std(ddof=0), "ap_seed_min": ps["ap"].min(),
                            "ap_seed_max": ps["ap"].max()})
                rows.append(out)
            ref = boot[("frozen", "rule_rain_3d", "none", "0")]
            for key, a in boot.items():
                d = a - ref
                i = [k for k, r in enumerate(rows) if (r["split"], r["target"], r["eval_labels"]) == (split, which, el)
                     and (r["setting"], r["model"], r["train_labels"], r["seeds"]) == key][0]
                rows[i].update({"ap_ci_low": np.nanpercentile(a, 2.5), "ap_ci_high": np.nanpercentile(a, 97.5),
                                "ap_minus_rule_ci_low": np.nanpercentile(d, 2.5),
                                "ap_minus_rule_ci_high": np.nanpercentile(d, 97.5)})
        print(split, which, "done", flush=True)

res = pd.DataFrame(rows)
rule = res[res["model"] == "rule_rain_3d"].set_index(["split", "target", "eval_labels"])["ap"]
res["ap_minus_rule"] = res["ap"] - rule.reindex(pd.MultiIndex.from_frame(res[["split", "target", "eval_labels"]])).values

# Seed by seed for the 8-seed LSTM runs: does audited training beat original training, and tuned beat frozen?
sr = pd.DataFrame(seed_rows)
k = ["split", "target", "setting", "model", "eval_labels", "seed"]
if sr.empty:
    print("no 8-seed LSTM runs found, seed comparison skipped")
else:
    lab = sr.pivot_table(index=k, columns="train_labels", values="ap").reset_index()
    lab["gain"] = lab["audited"] - lab["original"]
    g1 = lab.groupby(k[:-1]).agg(train_gain_mean=("gain", "mean"), train_gain_sd=("gain", "std"),
                                 seeds_audited_training_better=("gain", lambda x: int((x > 0).sum()))).reset_index()
    tun = sr.pivot_table(index=["split", "target", "model", "train_labels", "eval_labels", "seed"],
                         columns="setting", values="ap").reset_index()
    tun["gain"] = tun["tuned"] - tun["frozen"]
    g2 = tun.groupby(["split", "target", "model", "train_labels", "eval_labels"]).agg(
        tuned_gain_mean=("gain", "mean"), tuned_gain_sd=("gain", "std"),
        seeds_tuned_better=("gain", lambda x: int((x > 0).sum()))).reset_index()
    res = res.merge(g1.assign(seeds="0-7", train_labels="audited"), on=k[:-1] + ["seeds", "train_labels"], how="left")
    res = res.merge(g2.assign(seeds="0-7", setting="tuned"),
                    on=["split", "target", "model", "train_labels", "eval_labels", "seeds", "setting"], how="left")
    lab.to_csv(D + "retrain_lstm_seeds.csv", index=False)

cols = ["split", "period", "target", "setting", "model", "train_labels", "eval_labels", "seeds", "n_seeds", "days",
        "flood_days", "base_rate", "ap", "ap_fold_mean", "ap_seed_sd", "ap_seed_min", "ap_seed_max", "ap_ci_low",
        "ap_ci_high", "ap_minus_rule", "ap_minus_rule_ci_low", "ap_minus_rule_ci_high", "max_f1"]
cols += [f"{m}_{q}" for q in (3, 5, 10) for m in ["precision", "recall", "f1", "events", "pod", "far", "csi",
                                                    "false_days_per_cy"]]
for c in ["train_gain_mean", "train_gain_sd", "seeds_audited_training_better", "tuned_gain_mean", "tuned_gain_sd",
          "seeds_tuned_better"]:
    res[c] = res.get(c, np.nan)
cols += ["train_gain_mean", "train_gain_sd", "seeds_audited_training_better", "tuned_gain_mean", "tuned_gain_sd",
         "seeds_tuned_better"]
res = res[cols].round(4)
res.to_csv(D + "retrain_results.csv", index=False)

pd.set_option("display.width", 250)
show = ["setting", "model", "train_labels", "eval_labels", "seeds", "ap", "ap_fold_mean", "ap_seed_sd",
        "ap_minus_rule_ci_low", "ap_minus_rule_ci_high", "precision_5", "recall_5", "pod_5", "far_5"]
for (split, which), g in res.groupby(["split", "target"]):
    print("\n", split, which)
    print(g.sort_values(["eval_labels", "ap"], ascending=[True, False])[show].round(3).to_string(index=False))
