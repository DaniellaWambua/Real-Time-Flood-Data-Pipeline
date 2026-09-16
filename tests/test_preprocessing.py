"""Sanity checks for make_windows using a small synthetic table."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.preprocessing import make_windows


def _toy_dataframe(n_days: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rainfall_mm": np.arange(n_days, dtype=float),
            "river_discharge_m3s": np.arange(n_days, dtype=float),
            "rainfall_3day": np.arange(n_days, dtype=float),
            "rainfall_7day": np.arange(n_days, dtype=float),
            "discharge_change": np.arange(n_days, dtype=float),
            "rainfall_anomaly": np.arange(n_days, dtype=float),
            "flood_event": [0] * (n_days - 1) + [1],
        }
    )


def test_make_windows_shape():
    df = _toy_dataframe(20)
    X, y = make_windows(df, window_length=14)
    assert X.shape == (7, 14, 6)
    assert y.shape == (7,)


def test_make_windows_label_is_last_day():
    df = _toy_dataframe(20)
    X, y = make_windows(df, window_length=14)
    assert y[-1] == 1
    assert (y[:-1] == 0).all()


def test_make_windows_too_short_raises():
    df = _toy_dataframe(5)
    try:
        make_windows(df, window_length=14)
    except ValueError:
        return
    raise AssertionError("expected a ValueError for too few rows")


if __name__ == "__main__":
    test_make_windows_shape()
    test_make_windows_label_is_last_day()
    test_make_windows_too_short_raises()
    print("all tests passed")
