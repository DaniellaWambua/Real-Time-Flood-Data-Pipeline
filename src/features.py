"""Engineered features for the supervised flood classifiers.

The raw features describe each day in absolute terms (millimetres, cubic
metres per second). Phase 8 showed the 2024-2025 test period is simply
wetter than 2010-2022, so absolute values drift: a day that looked
extreme in training looks ordinary in test. These features instead ask
"how unusual is today for this catchment, compared with its own past
year?", which means the same thing in any period.

Every feature only looks backwards in time (trailing windows), so it
could be computed live from the ingestion stream on the day itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import CATCHMENTS, FEATURE_COLUMNS

# How many past days each "how unusual is today" rank compares against.
RANK_HISTORY_DAYS = 365
# Ranks need some history before they mean anything; until then, use 0.5
# (middle of the range, i.e. "nothing unusual").
RANK_MIN_HISTORY_DAYS = 60

# Soil moisture only exists in the v7 dataset (see config.DATASET).
HAS_SOIL_MOISTURE = "soil_moisture_m3m3" in FEATURE_COLUMNS

LOCAL_FEATURE_COLUMNS = [
    "rainfall_30day",
    "discharge_rank",
    "rainfall_7day_rank",
    "rainfall_30day_rank",
    *(["soil_moisture_rank"] if HAS_SOIL_MOISTURE else []),
    "season_sin",
    "season_cos",
]

# Same-day averages across every catchment. Floods in this register come
# with region-wide rain (the long and short rains), so how wet the whole
# region is today helps separate a genuine flood season from a single
# catchment's local downpour. All catchments arrive together in the
# ingestion stream, so this is available live too.
REGIONAL_FEATURE_COLUMNS = [
    "regional_rainfall_7day_rank",
    "regional_rainfall_30day_rank",
    "regional_discharge_rank",
    *(["regional_soil_moisture_rank"] if HAS_SOIL_MOISTURE else []),
]

CATCHMENT_COLUMNS = [f"is_{c.lower().replace(' ', '_')}" for c in CATCHMENTS]

ENGINEERED_FEATURE_COLUMNS = (
    FEATURE_COLUMNS + LOCAL_FEATURE_COLUMNS + REGIONAL_FEATURE_COLUMNS + CATCHMENT_COLUMNS
)


def _trailing_rank(series: pd.Series) -> pd.Series:
    """Today's percentile (0-1) within this catchment's trailing year."""
    rank = series.rolling(RANK_HISTORY_DAYS, min_periods=RANK_MIN_HISTORY_DAYS).rank(pct=True)
    return rank.fillna(0.5)


def _add_local_features(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("date").copy()
    group["rainfall_30day"] = group["rainfall_mm"].rolling(30, min_periods=1).sum()
    group["discharge_rank"] = _trailing_rank(group["river_discharge_m3s"])
    group["rainfall_7day_rank"] = _trailing_rank(group["rainfall_7day"])
    group["rainfall_30day_rank"] = _trailing_rank(group["rainfall_30day"])
    if HAS_SOIL_MOISTURE:
        group["soil_moisture_rank"] = _trailing_rank(group["soil_moisture_m3m3"])
    # Day of year as a point on a circle, so 31 December sits next to 1 January.
    angle = 2 * np.pi * group["date"].dt.dayofyear / 365.25
    group["season_sin"] = np.sin(angle)
    group["season_cos"] = np.cos(angle)
    return group


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with every column in ENGINEERED_FEATURE_COLUMNS added."""
    df = pd.concat(
        [_add_local_features(group) for _, group in df.groupby("catchment", sort=False)],
        ignore_index=True,
    )

    local_ranks = [c.removeprefix("regional_") for c in REGIONAL_FEATURE_COLUMNS]
    regional = df.groupby("date")[local_ranks].mean()
    regional.columns = REGIONAL_FEATURE_COLUMNS
    df = df.join(regional, on="date")

    for catchment, column in zip(CATCHMENTS, CATCHMENT_COLUMNS):
        df[column] = (df["catchment"] == catchment).astype(float)

    return df.sort_values(["catchment", "date"]).reset_index(drop=True)
