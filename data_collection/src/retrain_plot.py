import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Retraining comparison (D13): pooled AP judged on the audited labels, per approach, both training label sets.
# Whiskers span the seeds (3 for trees, 8 for LSTMs). The dashed line is the 3-day rule.
D = "data_collection/data/08_model_ready/"
NAMES = {"forest": "Forest", "boosting": "Boosting", "extra_trees": "ExtraTrees", "lstm_raw": "LSTM raw",
         "lstm_log": "LSTM log", "lstm_batches": "LSTM batches"}
TRAIN = [("original", "Trained on original labels", "#2a78d6", "o"), ("audited", "Trained on audited labels", "#eb6834", "D")]

r = pd.read_csv(D + "retrain_results.csv")
r = r[r["eval_labels"] == "audited"]
approaches = []
for m in NAMES:
    for setting in ["frozen", "tuned"]:
        if m.startswith("lstm"):
            approaches += [(m, setting, "0-7", f"{NAMES[m]}, {setting}, 8 seeds"),
                           (m, setting, "ensemble 0-7", f"{NAMES[m]}, {setting}, ensemble")]
        else:
            approaches.append((m, setting, "0-2", f"{NAMES[m]}, {setting}"))

fig, axes = plt.subplots(2, 2, figsize=(12, 9.5), sharey=True)
for row, split in enumerate(["dev", "final"]):
    for col, which in enumerate(["today", "tomorrow"]):
        ax = axes[row, col]
        g = r[(r["split"] == split) & (r["target"] == which)]
        rule = g[g["model"] == "rule_rain_3d"]["ap"].iloc[0]
        ax.axvline(rule, color="#52514e", ls="--", lw=1)
        ax.text(rule, -1.3, f" rule {rule:.3f}", fontsize=8, color="#52514e", va="center")
        for i, (tl, label, colour, marker) in enumerate(TRAIN):
            for y, (m, setting, seeds, _) in enumerate(approaches):
                x = g[(g["model"] == m) & (g["setting"] == setting) & (g["seeds"] == seeds) & (g["train_labels"] == tl)]
                if x.empty:
                    continue
                x = x.iloc[0]
                yy = y + (i - 0.5) * 0.3
                if x["n_seeds"] > 1:
                    ax.plot([x["ap_seed_min"], x["ap_seed_max"]], [yy, yy], color=colour, lw=1.2, alpha=0.6)
                ax.plot(x["ap"], yy, marker=marker, ms=6, color=colour, mec="#fcfcfb", mew=1,
                        label=label if y == 0 else None, ls="none")
        ax.set_yticks(range(len(approaches)), [a[3] for a in approaches], fontsize=8.5)
        ax.invert_yaxis()
        ax.set_ylim(len(approaches) - 0.5, -1.8)
        title = "Development folds" if split == "dev" else "2024-2025, already seen (not an unseen test)"
        ax.set_title(f"{title}, target {which}", fontsize=10, loc="left")
        ax.grid(axis="x", color="#e1e0d9", lw=0.6)
        ax.set_axisbelow(True)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
        for sp in ["left", "bottom"]:
            ax.spines[sp].set_color("#c3c2b7")
        ax.tick_params(colors="#52514e")
        if row == 1:
            ax.set_xlabel("Average precision, pooled, judged on audited labels", color="#52514e")
h, l = axes[0, 0].get_legend_handles_labels()
fig.legend(h, l, frameon=False, fontsize=9, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 0.955))
fig.suptitle("Retraining on audited labels (D13): marker is the mean over seeds, line is the seed range",
             x=0.01, ha="left", fontsize=12)
fig.tight_layout(rect=(0, 0, 1, 0.935))
fig.savefig(D + "retrain_comparison.png", dpi=150, facecolor="#fcfcfb")
