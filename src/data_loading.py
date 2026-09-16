"""Load and validate the merged features-and-labels dataset."""

from __future__ import annotations

import pandas as pd

from src.config import CATCHMENTS, FEATURE_COLUMNS, LABEL_COLUMN, RAW_FEATURES_LABELS_FILE


def load_raw_data(path=RAW_FEATURES_LABELS_FILE) -> pd.DataFrame:
    """Load, sort, and validate the raw dataset."""
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["catchment", "date"]).reset_index(drop=True)

    _validate(df)
    return df


def _validate(df: pd.DataFrame) -> None:
    """Check catchments, columns, missing values, and date gaps."""
    found_catchments = set(df["catchment"].unique())
    expected_catchments = set(CATCHMENTS)
    if found_catchments != expected_catchments:
        raise ValueError(
            f"Catchments in the data {found_catchments} do not match "
            f"the catchments in config.py {expected_catchments}"
        )

    required_columns = set(FEATURE_COLUMNS) | {LABEL_COLUMN, "date", "catchment"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"Missing expected columns: {missing_columns}")

    if df[FEATURE_COLUMNS].isnull().any().any():
        raise ValueError("Feature columns contain missing values")

    duplicate_rows = int(df.duplicated(subset=["catchment", "date"]).sum())
    if duplicate_rows:
        raise ValueError(f"Found {duplicate_rows} duplicate (catchment, date) rows")

    for catchment in CATCHMENTS:
        catchment_df = df[df["catchment"] == catchment]
        full_range = pd.date_range(catchment_df["date"].min(), catchment_df["date"].max(), freq="D")
        missing_dates = full_range.difference(catchment_df["date"])
        if len(missing_dates) > 0:
            raise ValueError(
                f"{catchment} is missing {len(missing_dates)} daily records "
                f"between {full_range.min().date()} and {full_range.max().date()}"
            )
