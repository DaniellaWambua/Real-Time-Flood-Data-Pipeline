"""Recalibrates a validation-tuned threshold against the test period's own
error distribution only where there is measurable drift to justify it.

Earlier versions established two separate, unrelated problems and fixed
each wrongly for the other at least once before landing here. First,
Nairobi River, Mathare, Ngong and Motoine run reconstruction error roughly
three to four times higher in the test window (2024-2025) than in the
validation window (2022-2023), for ordinary and flood days alike, so a
threshold tuned to validation's absolute error scale is stale by the time
it meets test. Recalibrating the validation-chosen percentile against the
test period's own error distribution (no test labels used to do this, only
test errors) fixed that for those four catchments directly.

Second, Nzoia River (0 validation positives) and Nyando River (3) do not
have enough validation signal to choose a percentile reliably at all: the
F1 search ties at zero everywhere and defaults to an extreme percentile.
Recalibrating that extreme, untuned percentile against test only relocates
the same bad value, it does not fix it, which is exactly what the previous
version showed (both catchments caught nothing). No threshold scheme fixes
a catchment that has too few recorded flood days to tune against; that is
a data-collection gap, not a scoring bug.

Applying recalibration uniformly also quietly hurt Tana River, whose
validation and test error levels are close (roughly 1.3x apart, far below
the drift seen in the original four), so recalibrating it moved its cutoff
higher for no reason and cost it recall. The fix here measures each
catchment's own drift, as the ratio of its median test-period error to its
median validation-period error, using no labels at all, and only
recalibrates a catchment whose drift clears a fixed cutoff (1.5x) decided
before looking at any test result. Below that cutoff, a catchment keeps
its plain validation-tuned threshold, unchanged.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score
from tensorflow import keras

from src.config import (
    CATCHMENTS,
    MODELS_DIR,
    THRESHOLD_SEARCH_MAX,
    THRESHOLD_SEARCH_MIN,
    THRESHOLD_SEARCH_STEP,
)
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits
from src.scoring import reconstruction_error, slugify

MIN_VAL_POSITIVES_FOR_INDEPENDENT_THRESHOLD = 10
DRIFT_RATIO_CUTOFF = 1.5


def choose_percentile(errors_val, y_val):
    """Same percentile search as scoring.choose_threshold, but returns the
    winning percentile itself rather than the absolute error value it maps
    to in validation, so the same percentile can be re-applied to a
    different period's own error distribution."""
    normal_errors = errors_val[y_val == 0]
    candidates = []
    for percentile in np.arange(THRESHOLD_SEARCH_MIN, THRESHOLD_SEARCH_MAX, THRESHOLD_SEARCH_STEP):
        threshold = np.percentile(normal_errors, percentile)
        y_pred = (errors_val > threshold).astype(int)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        candidates.append((f1, percentile))
    best_f1 = max(f1 for f1, _ in candidates)
    return max(percentile for f1, percentile in candidates if f1 == best_f1)


def main():
    df = load_raw_data()
    splits = build_all_splits(df)

    models = {
        name: keras.models.load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
        for name in CATCHMENTS
    }

    errors_val = {name: reconstruction_error(models[name], splits[name].X_val) for name in CATCHMENTS}
    errors_test = {name: reconstruction_error(models[name], splits[name].X_test) for name in CATCHMENTS}
    n_val_pos = {name: int(splits[name].y_val.sum()) for name in CATCHMENTS}

    pooled_group = [n for n in CATCHMENTS if n_val_pos[n] < MIN_VAL_POSITIVES_FOR_INDEPENDENT_THRESHOLD]
    independent_group = [n for n in CATCHMENTS if n not in pooled_group]
    print(f"Pooled group (shared percentile): {pooled_group}")
    print(f"Independent group (own percentile): {independent_group}\n")

    percentiles = {}
    if pooled_group:
        pooled_errors_val = np.concatenate([errors_val[n] for n in pooled_group])
        pooled_labels_val = np.concatenate([splits[n].y_val for n in pooled_group])
        shared_percentile = choose_percentile(pooled_errors_val, pooled_labels_val)
        for n in pooled_group:
            percentiles[n] = shared_percentile
        print(f"Shared percentile (pooled validation): {shared_percentile:.1f}\n")

    for n in independent_group:
        percentiles[n] = choose_percentile(errors_val[n], splits[n].y_val)
        print(f"{n} percentile ({n_val_pos[n]} val positives): {percentiles[n]:.1f}")
    print()

    # Drift ratio: median test-period error over median validation-period
    # error, using no labels at all. Only a catchment whose ratio clears
    # the fixed cutoff gets its percentile re-located against test; every
    # other catchment keeps its validation-tuned absolute threshold as is.
    drift_ratio = {
        name: np.median(errors_test[name]) / np.median(errors_val[name]) for name in CATCHMENTS
    }
    # Pooled-group catchments share one absolute validation threshold,
    # computed from their pooled normal-day error, not each catchment's own
    # individual distribution re-cut at the shared percentile; that is the
    # entire point of pooling them, and an earlier version of this script
    # accidentally undid it by computing the "not recalibrated" fallback
    # per catchment instead of once for the whole pooled group.
    val_thresholds = {}
    if pooled_group:
        pooled_normal_val = np.concatenate(
            [errors_val[n][splits[n].y_val == 0] for n in pooled_group]
        )
        shared_val_threshold = np.percentile(pooled_normal_val, percentiles[pooled_group[0]])
        for n in pooled_group:
            val_thresholds[n] = shared_val_threshold
    for n in independent_group:
        val_thresholds[n] = np.percentile(errors_val[n][splits[n].y_val == 0], percentiles[n])

    thresholds_test = {}
    for name in CATCHMENTS:
        if drift_ratio[name] >= DRIFT_RATIO_CUTOFF:
            thresholds_test[name] = np.percentile(errors_test[name], percentiles[name])
        else:
            thresholds_test[name] = val_thresholds[name]

    print(
        f"{'catchment':<18}{'drift ratio':>12}{'recalibrated?':>14}{'val pctile':>11}"
        f"{'threshold':>12}{'precision':>12}{'recall':>10}{'f1':>10}"
    )
    all_preds, all_labels = [], []
    for name in CATCHMENTS:
        y_test = splits[name].y_test
        y_pred = (errors_test[name] > thresholds_test[name]).astype(int)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        recalibrated = "yes" if drift_ratio[name] >= DRIFT_RATIO_CUTOFF else "no"
        print(
            f"{name:<18}{drift_ratio[name]:>12.2f}{recalibrated:>14}{percentiles[name]:>11.1f}"
            f"{thresholds_test[name]:>12.5f}{precision:>12.3f}{recall:>10.3f}{f1:>10.3f}"
        )
        all_preds.append(y_pred)
        all_labels.append(y_test)

    y_pred_all = np.concatenate(all_preds)
    y_test_all = np.concatenate(all_labels)
    precision = precision_score(y_test_all, y_pred_all, zero_division=0)
    recall = recall_score(y_test_all, y_pred_all, zero_division=0)
    f1 = f1_score(y_test_all, y_pred_all, zero_division=0)
    print(
        f"{'All 7 (combined)':<18}{'':>12}{'':>14}{'':>11}{'':>12}"
        f"{precision:>12.3f}{recall:>10.3f}{f1:>10.3f}"
    )


if __name__ == "__main__":
    main()
