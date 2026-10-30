"""Supervised LSTM classifier trained on a genuinely 1:1 balanced set.

The other half of the response to Dr Owuor's balancing feedback (see
src/train_flood_years.py for the autoencoder-side translation, which
that feedback does not map onto literally). This script instead swaps
the architecture: a classifier (build_lstm_classifier in src/model.py)
that is shown real flood and normal days directly, so "balance flood vs
normal day counts 1:1" has a literal, standard meaning here.

Per catchment, flood-active training years are the same FLOOD_YEARS used
in train_flood_years.py (2023 is the shared validation year for every
catchment; 2024-2025 is the fixed, untouched, real/imbalanced test set,
same as every other evaluation in this project). Within those years,
every flood-day window is kept and an equal number of normal-day windows
is drawn at random (seeded) from the same years/catchment. Training and
validation pool across all six catchments and share one scaler, since
several catchments (Nyando above all) have too few flood days on their
own to train a classifier - this is one shared model, not six.

Run with: python -m src.balanced_lstm_classifier
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.callbacks import EarlyStopping

from src.alternative_splits import _windows_allowing_gaps
from src.config import BATCH_SIZE, EPOCHS, RANDOM_SEED
from src.data_loading import load_raw_data
from src.model import build_lstm_classifier
from src.model_selection import best_f1_threshold, day_metrics
from src.train_flood_years import FLOOD_YEARS, TEST_END_YEAR, TEST_START_YEAR, VAL_YEAR
from src.walk_forward_validation import set_seeds

RNG = np.random.default_rng(RANDOM_SEED)


def balanced_sample(X, y):
    """Keep every flood window, draw an equal number of normal windows at
    random without replacement."""
    flood_idx = np.flatnonzero(y == 1)
    normal_idx = np.flatnonzero(y == 0)
    if len(flood_idx) == 0:
        return np.empty((0, *X.shape[1:])), np.empty((0,))
    n = min(len(flood_idx), len(normal_idx))
    if n < len(flood_idx):
        flood_idx = RNG.choice(flood_idx, size=n, replace=False)
    chosen_normal = RNG.choice(normal_idx, size=n, replace=False)
    idx = np.concatenate([flood_idx, chosen_normal])
    return X[idx], y[idx]


def main():
    set_seeds()
    df = load_raw_data()

    train_X, train_y, val_X, val_y, test_parts = [], [], [], [], []
    for catchment, train_years in FLOOD_YEARS.items():
        catchment_df = df[df["catchment"] == catchment].sort_values("date")

        X_train_raw, y_train_raw = _windows_allowing_gaps(catchment_df, train_years)
        X_val_raw, y_val_raw = _windows_allowing_gaps(catchment_df, [VAL_YEAR])
        X_test, y_test = _windows_allowing_gaps(
            catchment_df, list(range(TEST_START_YEAR, TEST_END_YEAR + 1))
        )

        X_tr_bal, y_tr_bal = balanced_sample(X_train_raw, y_train_raw)
        X_val_bal, y_val_bal = balanced_sample(X_val_raw, y_val_raw)

        if len(X_tr_bal) == 0 or len(X_val_bal) == 0:
            print(f"{catchment}: skipped, no flood days available to balance against")
            continue

        train_X.append(X_tr_bal)
        train_y.append(y_tr_bal)
        val_X.append(X_val_bal)
        val_y.append(y_val_bal)
        test_parts.append((catchment, X_test, y_test))

    X_train, y_train = np.concatenate(train_X), np.concatenate(train_y)
    X_val, y_val = np.concatenate(val_X), np.concatenate(val_y)

    n_features = X_train.shape[-1]
    scaler = StandardScaler().fit(X_train.reshape(-1, n_features))

    def scale(X):
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    X_train, X_val = scale(X_train), scale(X_val)

    print(
        f"Pooled balanced train: {len(X_train)} windows "
        f"({int(y_train.sum())} flood, {int((y_train == 0).sum())} normal)"
    )
    print(
        f"Pooled balanced val:   {len(X_val)} windows "
        f"({int(y_val.sum())} flood, {int((y_val == 0).sum())} normal)"
    )

    set_seeds()
    model = build_lstm_classifier(X_train.shape[1], n_features)
    early_stopping = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)
    model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stopping],
        verbose=0,
    )

    val_probs = model.predict(X_val, verbose=0).ravel()
    threshold = best_f1_threshold(y_val, val_probs)

    results = []
    for catchment, X_test, y_test in test_parts:
        if len(X_test) == 0:
            print(f"{catchment}: no 2024-2025 test windows")
            continue
        test_probs = model.predict(scale(X_test), verbose=0).ravel()
        pred = (test_probs >= threshold).astype(int)
        metrics = day_metrics(y_test, pred)
        print(
            f"{catchment:<15} test_pos={metrics['flood_days']:<4} "
            f"precision={metrics['precision']:.3f} recall={metrics['recall']:.3f} "
            f"f1={metrics['f1']:.3f} ({metrics['flagged_days']} flagged)"
        )
        results.append({"catchment": catchment, **metrics})

    if results:
        pooled_tp = sum(r["recall"] * r["flood_days"] for r in results)
        pooled_pos = sum(r["flood_days"] for r in results)
        pooled_recall = pooled_tp / pooled_pos if pooled_pos else 0.0
        mean_f1 = sum(r["f1"] for r in results) / len(results)
        print(f"\nThreshold={threshold:.3f}")
        print(f"Across {len(results)} catchments: mean F1={mean_f1:.3f}, pooled recall={pooled_recall:.3f}")


if __name__ == "__main__":
    main()
