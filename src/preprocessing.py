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
from src.features import ENGINEERED_FEATURE_COLUMNS, add_engineered_features


@dataclass
class CatchmentSplit:
    catchment: str
    X_train: np.ndarray  # normal windows only, scaled
    X_val: np.ndarray
    y_val: np.ndarray
    dates_val: np.ndarray  # date each val window's label belongs to
    X_test: np.ndarray
    y_test: np.ndarray
    dates_test: np.ndarray  # date each test window's label belongs to
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


def make_windows(df: pd.DataFrame, window_length: int = WINDOW_LENGTH,
                 feature_columns: list[str] = FEATURE_COLUMNS):
    """Build sliding windows; a window's label is its last day's flood_event.

    feature_columns defaults to the plain 8 (src.config.FEATURE_COLUMNS) so
    every existing caller (alternative_splits.py, walk_forward_validation.py)
    keeps behaving exactly as before. The production autoencoder path
    (build_catchment_split below) passes ENGINEERED_FEATURE_COLUMNS instead,
    the same richer feature set src/model_selection.py already gives the
    other models (rank/seasonal/regional features, see src/features.py).
    """
    features = df[feature_columns].to_numpy()
    labels = df[LABEL_COLUMN].to_numpy()
    dates = df["date"].to_numpy()

    n_windows = len(df) - window_length + 1
    if n_windows <= 0:
        raise ValueError(f"Not enough rows ({len(df)}) for a window length of {window_length}")

    X = np.stack([features[i : i + window_length] for i in range(n_windows)])
    y = labels[window_length - 1 :]
    window_dates = dates[window_length - 1 :]
    return X, y, window_dates


def build_catchment_split(df: pd.DataFrame, catchment: str) -> CatchmentSplit:
    """Window, split, and scale one catchment's data.

    df must already have had add_engineered_features applied (see
    build_all_splits), since the regional and trailing-year rank features
    need the full, multi-catchment, un-split series to mean anything.
    """
    train_df, val_df, test_df = chronological_split(df, catchment)

    X_train_raw, y_train_raw, _ = make_windows(train_df, feature_columns=ENGINEERED_FEATURE_COLUMNS)
    X_val, y_val, dates_val = make_windows(val_df, feature_columns=ENGINEERED_FEATURE_COLUMNS)
    X_test, y_test, dates_test = make_windows(test_df, feature_columns=ENGINEERED_FEATURE_COLUMNS)

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
        dates_val=dates_val,
        X_test=scale(X_test),
        y_test=y_test,
        dates_test=dates_test,
        scaler=scaler,
    )


def build_all_splits(df: pd.DataFrame) -> dict[str, CatchmentSplit]:
    # Applied once, over every catchment together, before any splitting:
    # the regional features average across all catchments on the same
    # date, and the trailing-year ranks need the full chronological
    # series, not a year-bounded slice.
    df = add_engineered_features(df)
    return {catchment: build_catchment_split(df, catchment) for catchment in CATCHMENTS}
