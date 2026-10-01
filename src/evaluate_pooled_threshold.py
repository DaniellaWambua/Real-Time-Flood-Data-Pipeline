"""Pools validation reconstruction error across all catchments to pick one
shared anomaly threshold, instead of each catchment tuning its own alone.

Nzoia River has zero flood-labelled days in the 2022-2023 validation
window (89 in train, 0 in val, 5 in test) so its own threshold search has
nothing to optimise against; every percentile ties at F1=0 and the
tie-break just returns the extreme 99.9th-percentile value by default,
not a tuned decision. Nyando River has only 3 validation positives, which
is enough to avoid that failure mode but too few to generalise. Pooling
validation windows across all seven catchments gives every catchment's
threshold search real positive examples to work with. This is valid
because each catchment's features are scaled by its own training-period
StandardScaler, so reconstruction error is already on a broadly
comparable scale across catchments before pooling.
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score
from tensorflow import keras

from src.config import CATCHMENTS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits
from src.scoring import choose_threshold, reconstruction_error, slugify


def main():
    df = load_raw_data()
    splits = build_all_splits(df)

    models = {
        name: keras.models.load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
        for name in CATCHMENTS
    }

    val_errors, val_labels, per_catchment_test = [], [], {}
    for name in CATCHMENTS:
        split = splits[name]
        model = models[name]

        errors_val = reconstruction_error(model, split.X_val)
        val_errors.append(errors_val)
        val_labels.append(split.y_val)

        errors_test = reconstruction_error(model, split.X_test)
        per_catchment_test[name] = (errors_test, split.y_test)

    pooled_errors_val = np.concatenate(val_errors)
    pooled_labels_val = np.concatenate(val_labels)
    shared_threshold = choose_threshold(pooled_errors_val, pooled_labels_val)

    print(
        f"Shared threshold (pooled validation, {len(pooled_labels_val)} windows, "
        f"{int(pooled_labels_val.sum())} positive): {shared_threshold:.5f}\n"
    )
    print(f"{'catchment':<18}{'precision':>10}{'recall':>10}{'f1':>10}")

    all_errors_test, all_labels_test = [], []
    for name in CATCHMENTS:
        errors_test, y_test = per_catchment_test[name]
        y_pred = (errors_test > shared_threshold).astype(int)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        print(f"{name:<18}{precision:>10.3f}{recall:>10.3f}{f1:>10.3f}")
        all_errors_test.append(errors_test)
        all_labels_test.append(y_test)

    pooled_errors_test = np.concatenate(all_errors_test)
    pooled_labels_test = np.concatenate(all_labels_test)
    y_pred = (pooled_errors_test > shared_threshold).astype(int)
    precision = precision_score(pooled_labels_test, y_pred, zero_division=0)
    recall = recall_score(pooled_labels_test, y_pred, zero_division=0)
    f1 = f1_score(pooled_labels_test, y_pred, zero_division=0)
    print(f"{'Pooled (all 7)':<18}{precision:>10.3f}{recall:>10.3f}{f1:>10.3f}")


if __name__ == "__main__":
    main()
