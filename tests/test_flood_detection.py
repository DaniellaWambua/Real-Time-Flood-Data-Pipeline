"""
Tests for backend/flood_detection.py on two real days from the features table
whose 8-seed scores are known from the saved-model check.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import flood_detection as fd  # noqa: E402

FEATURES = pd.read_csv(ROOT / "data_collection/data/08_model_ready/features_daily_audited.csv",
                       parse_dates=["date"])


def days(code, day):
    """The 14 rows of the features table ending on day for one catchment."""
    end = pd.Timestamp(day)
    return FEATURES[(FEATURES["catchment"] == code) & (FEATURES["date"] <= end)
                    & (FEATURES["date"] > end - pd.Timedelta(days=14))]


def fake_rows(code, day, drop=None):
    """What the database query would return, newest first, built from the features table."""
    cfg, _ = fd.load_models()
    rows = []
    for _, r in days(code, day).iterrows():
        if drop and r["date"] == pd.Timestamp(drop):
            continue
        row = {"day": r["date"].date()}
        for f in cfg["features"]:
            if not f.startswith(("is_", "month_")):
                row[fd.DB_COLUMN.get(f, f)] = float(r[f])
        rows.append(row)
    return rows[::-1]


def run(code, day, drop=None):
    with patch("flood_detection.db.query_all", return_value=fake_rows(code, day, drop)), \
         patch("flood_detection.db.query_one", return_value={"code": code}):
        return fd.build_window(1, pd.Timestamp(day).date())


@pytest.mark.parametrize("code, day, stored, flagged", [
    ("mathare", "2024-04-29", 0.7532, True),
    ("ngong", "2024-07-15", 0.0006, False),
])
def test_window_and_score_match_the_offline_model(code, day, stored, flagged):
    cfg, _ = fd.load_models()
    window, reason = run(code, day)
    assert reason is None and window.shape == (14, 15)
    g = days(code, day)
    for f in cfg["features"]:
        expected = (g["catchment"] == f[3:]).astype(float) if f.startswith("is_") else g[f]
        assert np.allclose(window[:, cfg["features"].index(f)], expected.values, atol=1e-5), f
    score = fd.score_window(window)
    assert abs(score - stored) < 0.06  # saved and stored 8-seed averages differ by at most 0.056
    assert (score >= cfg["threshold"]) == flagged


def test_missing_day_is_refused():
    window, reason = run("mathare", "2024-04-29", drop="2024-04-25")
    assert window is None and "consecutive" in reason