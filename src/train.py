"""Train the LSTM Autoencoder per catchment, then on all four combined."""

from __future__ import annotations

import json
import os
import random

import joblib
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
    VALIDATION_SPLIT,
    WINDOW_LENGTH,
)
from src.data_loading import load_raw_data
from src.features import ENGINEERED_FEATURE_COLUMNS
from src.model import build_lstm_autoencoder
from src.preprocessing import build_all_splits
from src.scoring import choose_threshold, reconstruction_error, slugify

# Reference percentiles printed for every model, so the precision/recall
# trade-off is visible, not just whichever point the search picks.
DIAGNOSTIC_PERCENTILES = [80, 85, 90, 95, 97, 99, 99.5]


def set_seeds():
    """Fix the random seed so runs are reproducible and comparable.

    Seeding alone does not make GPU training reproducible: cuDNN's LSTM
    kernels use non-deterministic reduction ops in the backward pass unless
    TensorFlow's op-determinism switch is explicitly enabled. Without this,
    two runs with the same seed can still diverge substantially on GPU (as
    seen 2026-10-25/27: Mathare's F1 moved from 0.667 to 0.160 between runs
    with no code or data change). This may fall back to a slightly slower
    non-cuDNN kernel for some ops, which is immaterial at this dataset size.
    """
    os.environ["PYTHONHASHSEED"] = str(RANDOM_SEED)
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    tf.random.set_seed(RANDOM_SEED)
    tf.config.experimental.enable_op_determinism()


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


def train_and_evaluate(name, X_train, X_val, y_val, X_test, y_test, scaler=None):
    """Train one autoencoder, pick a threshold, evaluate it on the test set.

    scaler is the StandardScaler already fit on this catchment's training
    data (see preprocessing.build_catchment_split). Passed through so it
    and the chosen threshold can be saved alongside the model: without
    them, nothing downstream (the model-hosting service added for live
    inference) could reproduce this exact scoring at serving time, since
    both were previously computed in memory and never written to disk.
    Left as None for the pooled "Combined" pseudo-model, which has no
    single meaningful scaler of its own and is never served live.
    """
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
    # Weights only, not the full architecture+config: a newer Keras release
    # can add a field to a layer's saved config (e.g. quantization_config)
    # that an older local Keras refuses to load, while a weights file is
    # just named numeric arrays. model_service/app.py's _load_autoencoder
    # rebuilds this same architecture from src.model.build_lstm_autoencoder
    # (always config.py's defaults here, never overridden) before loading
    # these weights. See src/model_selection.py's run_model() for the same
    # fix applied to the supervised classifiers.
    model.save_weights(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.weights.h5")

    if scaler is not None:
        joblib.dump(scaler, MODELS_DIR / f"scaler_{slugify(name)}.joblib")
        metadata = {
            "catchment": name,
            "threshold": threshold,
            "window_length": WINDOW_LENGTH,
            "feature_columns": ENGINEERED_FEATURE_COLUMNS,
        }
        with open(MODELS_DIR / f"metadata_{slugify(name)}.json", "w") as f:
            json.dump(metadata, f, indent=2)

    return result


def main():
    set_seeds()

    df = load_raw_data()
    splits = build_all_splits(df)

    results = []

    # Each catchment on its own first, the same order as the Colab work.
    for name, split in splits.items():
        result = train_and_evaluate(
            name, split.X_train, split.X_val, split.y_val, split.X_test, split.y_test,
            scaler=split.scaler,
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
