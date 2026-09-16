"""Train the LSTM Autoencoder and evaluate it against held-out flood events."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import f1_score, precision_score, recall_score
from tensorflow.keras.callbacks import EarlyStopping

from src.config import (
    BATCH_SIZE,
    COLOUR_YALE_BLUE,
    EPOCHS,
    FIGURES_DIR,
    MODELS_DIR,
    THRESHOLD_PERCENTILE,
    VALIDATION_SPLIT,
    WINDOW_LENGTH,
)
from src.data_loading import load_raw_data
from src.model import build_lstm_autoencoder
from src.preprocessing import build_all_splits


def pool_splits(splits):
    """Concatenate every catchment's arrays into one pooled set."""
    X_train = np.concatenate([s.X_train for s in splits.values()])
    X_val = np.concatenate([s.X_val for s in splits.values()])
    y_val = np.concatenate([s.y_val for s in splits.values()])
    X_test = np.concatenate([s.X_test for s in splits.values()])
    y_test = np.concatenate([s.y_test for s in splits.values()])
    return X_train, X_val, y_val, X_test, y_test


def reconstruction_error(model, X):
    """Mean squared reconstruction error per window."""
    X_pred = model.predict(X, verbose=0)
    return np.mean(np.square(X - X_pred), axis=(1, 2))


def choose_threshold(errors_normal):
    """Anomaly cutoff: this percentile of error on normal windows."""
    return float(np.percentile(errors_normal, THRESHOLD_PERCENTILE))


def plot_training_curve(history):
    """Save the train/val loss curve for the report."""
    plt.figure(figsize=(8, 5))
    plt.plot(history.history["loss"], label="train loss", color=COLOUR_YALE_BLUE)
    plt.plot(history.history["val_loss"], label="val loss", color="#B33951")
    plt.xlabel("epoch")
    plt.ylabel("reconstruction loss (MSE)")
    plt.title("LSTM Autoencoder training")
    plt.legend()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIGURES_DIR / "training_curve.png", dpi=150, bbox_inches="tight")
    plt.close()


def main():
    df = load_raw_data()
    splits = build_all_splits(df)
    X_train, X_val, y_val, X_test, y_test = pool_splits(splits)

    n_features = X_train.shape[-1]
    model = build_lstm_autoencoder(WINDOW_LENGTH, n_features)
    model.summary()

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
    plot_training_curve(history)

    # Threshold comes from normal windows in the labelled validation set.
    val_errors = reconstruction_error(model, X_val)
    threshold = choose_threshold(val_errors[y_val == 0])

    test_errors = reconstruction_error(model, X_test)
    y_pred = (test_errors > threshold).astype(int)

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    print(f"threshold: {threshold:.5f}")
    print(f"test precision: {precision:.3f}")
    print(f"test recall: {recall:.3f}")
    print(f"test F1: {f1:.3f}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(MODELS_DIR / "lstm_autoencoder.keras")


if __name__ == "__main__":
    main()
