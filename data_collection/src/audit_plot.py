import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Before and after the label audit (D11, D12): today target, mean of seeds.
D = "data_collection/data/08_model_ready/"
MODELS = ["rule_rain_3d", "boosting", "lstm_raw", "forest", "extra_trees"]
NAMES = {"rule_rain_3d": "3-day rule", "boosting": "Boosting", "lstm_raw": "LSTM (raw)", "forest": "Forest",
         "extra_trees": "ExtraTrees"}
CASES = [("original", "original", "Original labels", "#9aa3ad"),
         ("original", "audited", "Same model, audited labels to judge", "#2a78d6"),
         ("audited", "audited", "Trained and judged on audited labels", "#eb6834")]

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
for row, split in enumerate(["dev", "final"]):
    r = pd.read_csv(D + f"audit_{split}_results.csv")
    r = r[r["target"] == "today"]
    title = "Development folds (2019, 2021-22, 2023)" if split == "dev" else "2024-2025, already seen in D9 (not an unseen test)"
    for col, (metric, label) in enumerate([("ap", "Average precision"), ("precision_5", "Precision at a 5% alarm share")]):
        ax = axes[row, col]
        models = [m for m in MODELS if m in set(r["model"])]
        w = 0.8 / len(CASES)
        for i, (tl, el, name, colour) in enumerate(CASES):
            v = [r[(r["model"] == m) & (r["train_labels"] == tl) & (r["eval_labels"] == el)][metric].iloc[0] for m in models]
            ax.bar([x + (i - 1) * w for x in range(len(models))], v, w, label=name, color=colour)
        ax.set_xticks(range(len(models)), [NAMES[m] for m in models])
        ax.set_ylabel(label)
        ax.set_title(title, fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
h, l = axes[0, 0].get_legend_handles_labels()
fig.legend(h, l, frameon=False, fontsize=9, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 0.95))
fig.suptitle("Effect of the label audit, today target, mean of the 3 D8 seeds")
fig.text(0.5, 0.005, "With 8 seeds the LSTM training gain is smaller and within seed noise (audit_lstm_seed_summary.csv).",
         ha="center", fontsize=8, color="#555555")
fig.tight_layout(rect=(0, 0.02, 1, 0.93))
fig.savefig(D + "audit_comparison.png", dpi=150)
