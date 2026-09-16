"""Windowing, scaling, and chronological train/val/test splitting."""

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
    """Split one catchment's rows into train, validation, and test by year."""
    catchment_df = df[df["catchment"] == catchment].sort_values("date")
    train_df = catchment_df[catchment_df["year"] < VAL_START_YEAR]
    val_df = catchment_df[
        (catchment_df["year"] >= VAL_START_YEAR) & (catchment_df["year"] < TEST_START_YEAR)
    ]
    test_df = catchment_df[catchment_df["year"] >= TEST_START_YEAR]
    return train_df, val_df, test_df


def make_windows(df: pd.DataFrame, window_length: int = WINDOW_LENGTH):
    """Build sliding windows; a window's label is its last day's flood_event."""
    features = df[FEATURE_COLUMNS].to_numpy()
    labels = df[LABEL_COLUMN].to_numpy()

    n_windows = len(df) - window_length + 1
    if n_windows <= 0:
        raise ValueError(f"Not enough rows ({len(df)}) for a window length of {window_length}")

    X = np.stack([features[i : i + window_length] for i in range(n_windows)])
    y = labels[window_length - 1 :]
    return X, y


def build_catchment_split(df: pd.DataFrame, catchment: str) -> CatchmentSplit:
    """Window, split, and scale one catchment's data."""
    train_df, val_df, test_df = chronological_split(df, catchment)

    X_train_raw, y_train_raw = make_windows(train_df)
    X_val, y_val = make_windows(val_df)
    X_test, y_test = make_windows(test_df)

    # Keep only normal windows for training.
    normal_mask = y_train_raw == 0
    X_train_raw = X_train_raw[normal_mask]

    # Fit the scaler on training data only.
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
