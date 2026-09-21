"""Compares reconstruction error across splits to check whether the model
is overfitting the training years rather than learning a generalisable
sense of "normal", which would also help explain low precision: if
validation and test normal windows already look unusually anomalous to
the model, the threshold has to be set high just to control that, before
flood windows are even considered.
"""

from __future__ import annotations

import numpy as np
from tensorflow.keras.models import load_model

from src.config import CATCHMENTS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits
from src.scoring import reconstruction_error, slugify


def diagnose(name, split):
    model = load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")

    # X_train already contains normal windows only; val/test are filtered
    # to normal windows here so the comparison isn't skewed by floods.
    train_err = reconstruction_error(model, split.X_train)
    val_err = reconstruction_error(model, split.X_val[split.y_val == 0])
    test_err = reconstruction_error(model, split.X_test[split.y_test == 0])

    print(f"\n{name}")
    print(f"  train (normal)  mean {train_err.mean():.4f}  median {np.median(train_err):.4f}")
    print(f"  val   (normal)  mean {val_err.mean():.4f}  median {np.median(val_err):.4f}")
    print(f"  test  (normal)  mean {test_err.mean():.4f}  median {np.median(test_err):.4f}")
    print(f"  val/train ratio  {val_err.mean() / train_err.mean():.2f}x")
    print(f"  test/train ratio {test_err.mean() / train_err.mean():.2f}x")


def main():
    df = load_raw_data()
    splits = build_all_splits(df)
    for name, split in splits.items():
        diagnose(name, split)


if __name__ == "__main__":
    main()
