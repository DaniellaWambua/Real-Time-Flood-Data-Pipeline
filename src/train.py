"""Train the LSTM Autoencoder per catchment, then on all four combined."""

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
    THRESHOLD_SEARCH_MAX,
    THRESHOLD_SEARCH_MIN,
    THRESHOLD_SEARCH_STEP,
    VALIDATION_SPLIT,
    WINDOW_LENGTH,
)
from src.data_loading import load_raw_data
from src.model import build_lstm_autoencoder
from src.preprocessing import build_all_splits


def slugify(name: str) -> str:
    return name.lower().replace(" ", "_")


def reconstruction_error(model, X):
    """Mean squared reconstruction error per window."""
    X_pred = model.predict(X, verbose=0)
    return np.mean(np.square(X - X_pred), axis=(1, 2))


def choose_threshold(errors_val, y_val):
    """Percentile of normal error that gives the best F1 on validation."""
    normal_errors = errors_val[y_val == 0]
    best_threshold, best_f1 = None, -1.0
    for percentile in np.arange(THRESHOLD_SEARCH_MIN, THRESHOLD_SEARCH_MAX, THRESHOLD_SEARCH_STEP):
        threshold = np.percentile(normal_errors, percentile)
        y_pred = (errors_val > threshold).astype(int)
        f1 = f1_score(y_val, y_pred, zero_division=0)
        if f1 > best_f1:
            best_f1, best_threshold = f1, threshold
    return best_threshold


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
