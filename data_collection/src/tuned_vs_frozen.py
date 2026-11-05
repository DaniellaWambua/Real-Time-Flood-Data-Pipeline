import pandas as pd
from comparison_setup import OUT

# Frozen D8/D9 settings next to the D10 tuned settings, pooled development and 2024-2025 rows.
# Development AP is the mean of folds (what tuning selected on). F1 uses the dev-fixed max-F1 threshold.
COLS = ["ap_fold_mean", "ap_lift", "event_recall_5pct", "false_days_per_cy_5pct", "recall_top5pct"]
MODELS = ["rule_rain_3d", "forest", "boosting", "extra_trees", "lstm_raw", "lstm_log", "lstm_batches"]


def side(prefix):
    r = pd.read_csv(f"{OUT}/{prefix}comparison_results.csv", dtype={"val": str})
    r = r[r["val"].isin(["pooled_dev", "2024-2025"]) & r["model"].isin(MODELS)]
    f = pd.read_csv(f"{OUT}/{prefix}fixed_threshold_results.csv")
    f = f[(f["criterion"] == "f1") & (f["threshold_from"] == "dev out-of-fold 2019-2023") & f["model"].isin(MODELS)]
    r = r.merge(f[["target", "model", "precision", "recall", "f1"]].assign(split="final"),
                on=["target", "split", "model"], how="left")
    return r.set_index(["target", "split", "model"])[COLS + ["precision", "recall", "f1"]]


out = side("").merge(side("tuned_"), left_index=True, right_index=True, suffixes=("_frozen", "_tuned"))
for c in COLS + ["f1"]:
    out[f"{c}_change"] = out[f"{c}_tuned"] - out[f"{c}_frozen"]
out = out.reset_index()
out["model"] = pd.Categorical(out["model"], MODELS)
out = out.sort_values(["split", "target", "model"]).round(3)
pd.set_option("display.width", 250)
show = ["target", "split", "model"] + [f"{c}_{s}" for c in ["ap_fold_mean", "event_recall_5pct", "f1"]
                                       for s in ["frozen", "tuned"]]
print(out[show].to_string(index=False))
out.to_csv(f"{OUT}/tuned_vs_frozen.csv", index=False)
