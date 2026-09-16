"""Data loading for the flood pipeline model training code.

Reads the merged features-and-labels CSV, validates it against the
expected catchments and columns, and returns a tidy, sorted DataFrame.
"""

from __future__ import annotations

import pandas as pd

from src.config import CATCHMENTS, FEATURE_COLUMNS, LABEL_COLUMN, RAW_FEATURES_LABELS_FILE


def load_raw_data(path=RAW_FEATURES_LABELS_FILE) -> pd.DataFrame:
    """Load the merged features-and-labels dataset.

    The file already has one row per catchment per day, with the
    ``flood_event`` label merged in, so no separate join is needed here.
    This function parses dates, sorts the rows, and checks the data is
    what the rest of the pipeline expects before anything else touches it.
    """
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["catchment", "date"]).reset_index(drop=True)

    _validate(df)
    return df


def _validate(df: pd.DataFrame) -> None:
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
