"""Walk-forward (rolling-origin) validation: retrains across several
chronological folds, each with a later train/validation/test boundary than
the last, to test whether the validation-to-test reconstruction-error
drift found in the fixed 2022/2024 split (and the narrower 2023/2024 split
tried afterwards) is a structural property of these catchments and this
model, or an artefact specific to one particular test window.

Three new folds are trained here, each an expanding window (more training
years, same two-year validation and two-year test width), stepping forward
two years at a time: 2010-2015/2016-2017/2018-2019, then
2010-2017/2018-2019/2020-2021, then 2010-2019/2020-2021/2022-2023. The
fourth, most recent fold (2010-2022/2023/2024-2025) is not re-run here,
since it is already the current `src/config.py` split and its numbers are
already on record.

Models are trained fresh per fold with the same architecture, epochs and
early-stopping as `train.py`, but are not saved to `models/`, since the
point here is the drift pattern across folds, not a model to keep. The
production models trained under the current config are left untouched.
"""

from __future__ import annotations

import os
import random

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.callbacks import EarlyStopping

from src.config import (
    BATCH_SIZE,
    CATCHMENTS,
    EPOCHS,
    RANDOM_SEED,
    VALIDATION_SPLIT,
    WINDOW_LENGTH,
)
from src.data_loading import load_raw_data
from src.model import build_lstm_autoencoder
from src.preprocessing import make_windows
from src.scoring import choose_threshold, reconstruction_error

FOLDS = [
    {"label": "Fold A (train 2010-2015, val 2016-2017, test 2018-2019)", "val_start": 2016, "test_start": 2018, "test_end": 2019},
    {"label": "Fold B (train 2010-2017, val 2018-2019, test 2020-2021)", "val_start": 2018, "test_start": 2020, "test_end": 2021},
    {"label": "Fold C (train 2010-2019, val 2020-2021, test 2022-2023)", "val_start": 2020, "test_start": 2022, "test_end": 2023},
]


def set_seeds():
    os.environ["PYTHONHASHSEED"] = str(RANDOM_SEED)
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    tf.random.set_seed(RANDOM_SEED)


def bounded_split(df: pd.DataFrame, catchment: str, val_start: int, test_start: int, test_end: int):
    """Same windowing/scaling logic as preprocessing.build_catchment_split,
    but with explicit, caller-supplied year boundaries rather than reading
    them from config, so several folds can be evaluated in one run."""
    catchment_df = df[df["catchment"] == catchment].sort_values("date")
    train_df = catchment_df[catchment_df["year"] < val_start]
    val_df = catchment_df[(catchment_df["year"] >= val_start) & (catchment_df["year"] < test_start)]
    test_df = catchment_df[(catchment_df["year"] >= test_start) & (catchment_df["year"] <= test_end)]

    X_train_raw, y_train_raw, _ = make_windows(train_df)
    X_val, y_val, _ = make_windows(val_df)
    X_test, y_test, _ = make_windows(test_df)

    X_train_raw = X_train_raw[y_train_raw == 0]

    n_features = X_train_raw.shape[-1]
    scaler = StandardScaler().fit(X_train_raw.reshape(-1, n_features))

    def scale(X):
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    return scale(X_train_raw), scale(X_val), y_val, scale(X_test), y_test


def train_one(name, X_train, X_val, y_val, X_test, y_test):
    set_seeds()
    model = build_lstm_autoencoder(WINDOW_LENGTH, X_train.shape[-1])
    early_stopping = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)
    model.fit(
        X_train, X_train,
        validation_split=VALIDATION_SPLIT,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stopping],
        verbose=0,
    )

    errors_val = reconstruction_error(model, X_val)
    errors_test = reconstruction_error(model, X_test)
    drift_ratio = np.median(errors_test) / np.median(errors_val)

    threshold = choose_threshold(errors_val, y_val)
    y_pred = (errors_test > threshold).astype(int)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    return drift_ratio, precision, recall, f1, int(y_val.sum()), int(y_test.sum())


def main():
    df = load_raw_data()
    all_rows = []

    for fold in FOLDS:
        print(f"\n=== {fold['label']} ===")
        print(f"{'catchment':<18}{'val pos':>8}{'test pos':>9}{'drift ratio':>13}{'precision':>12}{'recall':>10}{'f1':>10}")
        for name in CATCHMENTS:
            X_train, X_val, y_val, X_test, y_test = bounded_split(
                df, name, fold["val_start"], fold["test_start"], fold["test_end"]
            )
            if len(X_train) == 0 or len(X_val) == 0 or len(X_test) == 0:
                print(f"{name:<18}{'skipped: empty split for this fold':>60}")
                continue
            drift_ratio, precision, recall, f1, n_val_pos, n_test_pos = train_one(
                name, X_train, X_val, y_val, X_test, y_test
            )
            print(
                f"{name:<18}{n_val_pos:>8}{n_test_pos:>9}{drift_ratio:>13.2f}"
                f"{precision:>12.3f}{recall:>10.3f}{f1:>10.3f}"
            )
            all_rows.append((fold["label"], name, drift_ratio, precision, recall, f1))

    print("\n=== Drift ratio by catchment across folds (this run only; current config's fold is on record separately) ===")
    summary = pd.DataFrame(all_rows, columns=["fold", "catchment", "drift_ratio", "precision", "recall", "f1"])
    pivot = summary.pivot(index="catchment", columns="fold", values="drift_ratio")
    print(pivot.to_string())


if __name__ == "__main__":
    main()
