"""Random Forest on Nyando River's two alternative validation splits.

Reuses the engineered features and model fitting from src.model_selection
unchanged. Unlike the earlier LSTM alternative splits (src.alternative_splits),
there is no window-gap concern here: model_selection.build_dataset() builds
each day's window once over the catchment's full chronological series before
any split is applied, so a day's feature row already reflects its true
lookback regardless of which split later assigns that day to train, val, or
test.

One fixed Random Forest configuration is used throughout (the midpoint of
model_selection's own tuning grid), rather than re-tuned per split: Nyando's
handful of flood days are too few to carve into further CV folds without
duplicating the whole tuning protocol on data that cannot support it.

Run with: python -m src.nyando_supervised_splits
"""

from __future__ import annotations

import numpy as np

from src.alternative_splits import CATCHMENT, STRATEGY_A, STRATEGY_B_FOLDS
from src.config import LABEL_COLUMN
from src.model_selection import best_f1_threshold, build_dataset, day_metrics, fit_predict

RF_PARAMS = {"max_depth": 8, "min_samples_leaf": 20, "max_features": "sqrt"}


def run_split(label, X, y, train_mask, val_mask, test_mask):
    if val_mask.sum() == 0 or test_mask.sum() == 0 or y[val_mask].sum() == 0:
        print(f"{label}: skipped, empty split or no validation positives")
        return None

    val_probs = fit_predict("Random Forest", RF_PARAMS, X[train_mask], y[train_mask], X[val_mask])
    threshold = best_f1_threshold(y[val_mask], val_probs)
    test_probs = fit_predict("Random Forest", RF_PARAMS, X[train_mask], y[train_mask], X[test_mask])
    metrics = day_metrics(y[test_mask], (test_probs >= threshold).astype(int))

    print(
        f"{label}\n"
        f"  train={train_mask.sum()}  val={val_mask.sum()}  test={test_mask.sum()}  "
        f"threshold={threshold:.3f}\n"
        f"  precision={metrics['precision']:.3f}  recall={metrics['recall']:.3f}  "
        f"f1={metrics['f1']:.3f}  ({metrics['flagged_days']} flagged, {metrics['flood_days']} flood days)"
    )
    return metrics


def main():
    X, meta = build_dataset()
    keep = (meta["catchment"] == CATCHMENT).to_numpy()
    X, meta = X[keep], meta[keep].reset_index(drop=True)
    y = meta[LABEL_COLUMN].to_numpy()
    years = meta["year"].to_numpy()

    print(f"=== Strategy A: catchment-specific chronological window ({CATCHMENT}) ===")
    print(
        f"train < {STRATEGY_A['val_start']}, val [{STRATEGY_A['val_start']}, {STRATEGY_A['test_start']}), "
        f"test [{STRATEGY_A['test_start']}, {STRATEGY_A['test_end']}]"
    )
    train_mask = years < STRATEGY_A["val_start"]
    val_mask = (years >= STRATEGY_A["val_start"]) & (years < STRATEGY_A["test_start"])
    test_mask = (years >= STRATEGY_A["test_start"]) & (years <= STRATEGY_A["test_end"])
    run_split("Strategy A", X, y, train_mask, val_mask, test_mask)

    print(f"\n=== Strategy B: leave-one-event-out ({CATCHMENT}) ===")
    results = []
    for fold in STRATEGY_B_FOLDS:
        train_mask = np.isin(years, fold["train_years"])
        val_mask = np.isin(years, fold["val_years"])
        test_mask = np.isin(years, fold["test_years"])
        r = run_split(fold["label"], X, y, train_mask, val_mask, test_mask)
        if r:
            results.append(r)

    if results:
        pooled_tp = sum(r["recall"] * r["flood_days"] for r in results)
        pooled_flood_days = sum(r["flood_days"] for r in results)
        pooled_recall = pooled_tp / pooled_flood_days if pooled_flood_days else 0.0
        mean_f1 = sum(r["f1"] for r in results) / len(results)
        print(
            f"\nStrategy B summary across {len(results)} usable folds: "
            f"mean F1={mean_f1:.3f}, pooled recall={pooled_recall:.3f}"
        )


if __name__ == "__main__":
    main()
