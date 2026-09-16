"""Windowing, scaling and chronological splitting for the LSTM Autoencoder.

The model is trained only on windows ending on a normal (non-flood) day, so
it learns what an ordinary sequence of rainfall and discharge looks like.
Validation and test sets keep both normal and flood windows, so reconstruction
error can be checked against labels the model never trained on.

Splits are chronological, not random, because shuffling would let the model
see information from the future during training, which a deployed early
warning system would never have.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.config import (
    CATCHMENTS,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    TEST_START_YEAR,
    VAL_START_YEAR,
    WINDOW_LENGTH,
)


@dataclass
class CatchmentSplit:
    catchment: str
    X_train: np.ndarray  # normal windows only, scaled
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    scaler: StandardScaler


def chronological_split(df: pd.DataFrame, catchment: str):
    """Split one catchment's rows into train, validation and test by year."""
    catchment_df = df[df["catchment"] == catchment].sort_values("date")
    train_df = catchment_df[catchment_df["year"] < VAL_START_YEAR]
    val_df = catchment_df[
        (catchment_df["year"] >= VAL_START_YEAR) & (catchment_df["year"] < TEST_START_YEAR)
    ]
    test_df = catchment_df[catchment_df["year"] >= TEST_START_YEAR]
    return train_df, val_df, test_df


def make_windows(df: pd.DataFrame, window_length: int = WINDOW_LENGTH):
    """Build sliding windows of ``window_length`` days.

    A window's label is the ``flood_event`` value on its last day, so the
    model judges each day using the days leading up to it, the same way an
    early warning system would see the data arrive in real time.
    """
    features = df[FEATURE_COLUMNS].to_numpy()
    labels = df[LABEL_COLUMN].to_numpy()

    n_windows = len(df) - window_length + 1
    if n_windows <= 0:
        raise ValueError(f"Not enough rows ({len(df)}) for a window length of {window_length}")

    X = np.stack([features[i : i + window_length] for i in range(n_windows)])
    y = labels[window_length - 1 :]
    return X, y


def build_catchment_split(df: pd.DataFrame, catchment: str) -> CatchmentSplit:
    """Build the scaled, windowed train, validation and test arrays for one catchment."""
    train_df, val_df, test_df = chronological_split(df, catchment)

    X_train_raw, y_train_raw = make_windows(train_df)
    X_val, y_val = make_windows(val_df)
    X_test, y_test = make_windows(test_df)

    # Train only on windows ending on a normal day.
    normal_mask = y_train_raw == 0
    X_train_raw = X_train_raw[normal_mask]

    # Fit the scaler on the training data only, so validation and test
    # statistics never leak into training.
    n_features = X_train_raw.shape[-1]
    scaler = StandardScaler()
    scaler.fit(X_train_raw.reshape(-1, n_features))

    def scale(X: np.ndarray) -> np.ndarray:
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    return CatchmentSplit(
        catchment=catchment,
        X_train=scale(X_train_raw),
        X_val=scale(X_val),
        y_val=y_val,
        X_test=scale(X_test),
        y_test=y_test,
        scaler=scaler,
    )


def build_all_splits(df: pd.DataFrame) -> dict[str, CatchmentSplit]:
    return {catchment: build_catchment_split(df, catchment) for catchment in CATCHMENTS}
