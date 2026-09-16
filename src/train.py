"""Train the LSTM Autoencoder per catchment, then on all four combined."""

from __future__ import annotations

import os
import random

import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from sklearn.metrics import f1_score, precision_score, recall_score
from tensorflow.keras.callbacks import EarlyStopping

from src.config import (
    BATCH_SIZE,
    COLOUR_YALE_BLUE,
    EPOCHS,
    FIGURES_DIR,
    MODELS_DIR,
    RANDOM_SEED,
    THRESHOLD_SEARCH_MAX,
    THRESHOLD_SEARCH_MIN,
    THRESHOLD_SEARCH_STEP,
    VALIDATION_SPLIT,
    WINDOW_LENGTH,
)
from src.data_loading import load_raw_data
from src.model import build_lstm_autoencoder
from src.preprocessing import build_all_splits

# Reference percentiles printed for every model, so the precision/recall
# trade-off is visible, not just whichever point the search picks.
DIAGNOSTIC_PERCENTILES = [80, 85, 90, 95, 97, 99, 99.5]


def set_seeds():
    """Fix the random seed so runs are reproducible and comparable."""
    os.environ["PYTHONHASHSEED"] = str(RANDOM_SEED)
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    tf.random.set_seed(RANDOM_SEED)


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def reconstruction_error(model, X):
    """Reconstruction error on the final day of each window.

    The flood label belongs to the last day only, so scoring the whole
    window average dilutes that day's signal against the other thirteen,
    ordinary ones sitting next to it. Scoring just the last day isolates it.
    """
    X_pred = model.predict(X, verbose=0)
    return np.mean(np.square(X[:, -1, :] - X_pred[:, -1, :]), axis=1)


def print_threshold_curve(name, errors_val, y_val):
    """Show precision/recall at a few fixed percentiles, for transparency."""
    normal_errors = errors_val[y_val == 0]
    print(f"  threshold curve for {name}:")
    for percentile in DIAGNOSTIC_PERCENTILES:
        threshold = np.percentile(normal_errors, percentile)
        y_pred = (errors_val > threshold).astype(int)
        p = precision_score(y_val, y_pred, zero_division=0)
        r = recall_score(y_val, y_pred, zero_division=0)
        print(f"    p{percentile:>5.1f}  threshold={threshold:.5f}  precision={p:.3f}  recall={r:.3f}")


def choose_threshold(errors_val, y_val):
    """Percentile of normal error with the best F1 on validation.

    Many percentiles often tie on the same F1 when there are only a
    handful of flood windows in validation, so among ties the highest
    threshold (best precision) is kept, rather than the first one found.
    """
    normal_errors = errors_val[y_val == 0]
    candidates = []
    for percentile in np.arange(THRESHOLD_SEARCH_MIN, THRESHOLD_SEARCH_MAX, THRESHOLD_SEARCH_STEP):
        threshold = np.percentile(normal_errors, percentile)
        y_pred = (errors_val > threshold).astype(int)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        candidates.append((f1, threshold))
    best_f1 = max(f1 for f1, _ in candidates)
    return max(threshold for f1, threshold in candidates if f1 == best_f1)


def plot_training_curve(history, name):
    plt.figure(figsize=(8, 5))
    plt.plot(history.history["loss"], label="train loss", color=COLOUR_YALE_BLUE)
    plt.plot(history.history["val_loss"], label="val loss", color="#B33951")
    plt.xlabel("epoch")
    plt.ylabel("reconstruction loss (MSE)")
    plt.title(f"LSTM Autoencoder training: {name}")
    plt.legend()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIGURES_DIR / f"training_curve_{slugify(name)}.png", dpi=150, bbox_inches="tight")
    plt.close()


def train_and_evaluate(name, X_train, X_val, y_val, X_test, y_test):
    """Train one autoencoder, pick a threshold, evaluate it on the test set."""
    n_features = X_train.shape[-1]
    model = build_lstm_autoencoder(WINDOW_LENGTH, n_features)

    early_stopping = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)
    history = model.fit(
        X_train,
        X_train,
        validation_split=VALIDATION_SPLIT,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stopping],
        verbose=2,
    )
    plot_training_curve(history, name)

    val_errors = reconstruction_error(model, X_val)
    print_threshold_curve(name, val_errors, y_val)
    threshold = choose_threshold(val_errors, y_val)

    test_errors = reconstruction_error(model, X_test)
    y_pred = (test_errors > threshold).astype(int)

    result = {
        "name": name,
        "threshold": threshold,
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
    return result


def main():
    set_seeds()

    df = load_raw_data()
    splits = build_all_splits(df)

    results = []

    # Each catchment on its own first, the same order as the Colab work.
    for name, split in splits.items():
        result = train_and_evaluate(
            name, split.X_train, split.X_val, split.y_val, split.X_test, split.y_test
        )
        results.append(result)

    # Then the combined model, pooling all four catchments together.
    X_train = np.concatenate([s.X_train for s in splits.values()])
    X_val = np.concatenate([s.X_val for s in splits.values()])
    y_val = np.concatenate([s.y_val for s in splits.values()])
    X_test = np.concatenate([s.X_test for s in splits.values()])
    y_test = np.concatenate([s.y_test for s in splits.values()])
    results.append(train_and_evaluate("Combined", X_train, X_val, y_val, X_test, y_test))

    print(f"{'model':<16}{'threshold':>12}{'precision':>12}{'recall':>12}{'f1':>10}")
    for r in results:
        print(f"{r['name']:<16}{r['threshold']:>12.5f}{r['precision']:>12.3f}{r['recall']:>12.3f}{r['f1']:>10.3f}")


if __name__ == "__main__":
    main()
