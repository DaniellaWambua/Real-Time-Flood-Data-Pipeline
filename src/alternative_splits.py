"""Two alternative validation strategies for catchments too data-poor for
the standard chronological split, tried against Nyando River specifically
(3 validation-period positives under the current config, 0 under three of
the three walk-forward folds already run).

Nyando's 46 flood days (v9) fall into exactly four calendar clusters: a
single day in 2010, a 37-day event spanning Dec 2015-Jan 2016, a 3-day
event in April 2023, and a 5-day event in Dec 2024. No single contiguous
calendar window reliably covers more than one of these, which is why the
standard split (and every walk-forward fold tried so far) gives Nyando a
degenerate, untuned threshold.

Strategy A, catchment-specific window: give Nyando its own train/val/test
boundary, chosen so validation actually contains one of its clusters,
rather than sharing the six-catchment default. Still chronological (train
precedes val precedes test), reusing walk_forward_validation.bounded_split
unchanged.

Strategy B, leave-one-event-out: hold out one cluster as test, use a
second cluster as validation, train on every other year regardless of
chronological order. This needs a non-chronological split (train is not
simply "everything before"), so it is implemented separately as
flexible_split below, reusing the same windowing/scaling pattern.

Run with: python -m src.alternative_splits
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.config import FEATURE_COLUMNS, WINDOW_LENGTH
from src.data_loading import load_raw_data
from src.preprocessing import make_windows
from src.walk_forward_validation import bounded_split, set_seeds, train_one

CATCHMENT = "Nyando River"

# Strategy A: train 2010-2014, val 2015-2016 (catches the 37-day cluster),
# test 2017-2025 (catches the 2023 and 2024 clusters, 8 days combined).
STRATEGY_A = {"val_start": 2015, "test_start": 2017, "test_end": 2025}

# Strategy B folds: (label, train_years, val_years, test_years). Each
# holds out one cluster as test and uses a different cluster as
# validation; 2010's single day is never used as test or val (too little
# surrounding data to score precision/recall meaningfully on its own, and
# no training history exists before it anyway), but its year is still
# available for training.
ALL_YEARS = list(range(2010, 2026))


def _years_minus(*groups):
    excluded = {y for g in groups for y in g}
    return [y for y in ALL_YEARS if y not in excluded]


STRATEGY_B_FOLDS = [
    {
        "label": "Fold 1: test=2015-2016 cluster, val=2023 cluster",
        "test_years": [2015, 2016],
        "val_years": [2023],
        "train_years": _years_minus([2015, 2016], [2023]),
    },
    {
        "label": "Fold 2: test=2023 cluster, val=2015-2016 cluster",
        "test_years": [2023],
        "val_years": [2015, 2016],
        "train_years": _years_minus([2023], [2015, 2016]),
    },
    {
        "label": "Fold 3: test=2024 cluster, val=2015-2016 cluster",
        "test_years": [2024],
        "val_years": [2015, 2016],
        "train_years": _years_minus([2024], [2015, 2016]),
    },
]


def _contiguous_runs(years):
    """Split a list of years into maximal consecutive runs, e.g.
    [2010,2011,2012,2017,2018] -> [[2010,2011,2012],[2017,2018]]."""
    years = sorted(years)
    runs = []
    for y in years:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    return runs


def _windows_allowing_gaps(catchment_df, years):
    """make_windows, but applied separately to each contiguous run of
    years so a window is never built across a gap (e.g. training years
    2010-2014 plus 2017-2022 plus 2025 must not let a window's 14 days
    straddle 2014-12-31 and 2017-01-01 as if they were consecutive)."""
    Xs, ys = [], []
    for run in _contiguous_runs(years):
        run_df = catchment_df[catchment_df["year"].isin(run)]
        if len(run_df) < WINDOW_LENGTH:
            continue
        X, y, _ = make_windows(run_df)
        Xs.append(X)
        ys.append(y)
    if not Xs:
        return np.empty((0, WINDOW_LENGTH, len(FEATURE_COLUMNS))), np.empty((0,))
    return np.concatenate(Xs), np.concatenate(ys)


def flexible_split(df: pd.DataFrame, catchment: str, train_years, val_years, test_years):
    """Same windowing/scaling as walk_forward_validation.bounded_split, but
    by explicit year membership rather than chronological cutoffs, so
    train can include years after the test/val years (needed for genuine
    leave-one-event-out, where the held-out event need not be the most
    recent). Each of train/val/test may itself span disjoint year ranges,
    so windows are built per contiguous run (see _windows_allowing_gaps)
    rather than naively over the whole filtered, possibly gappy, frame.
    """
    catchment_df = df[df["catchment"] == catchment].sort_values("date")

    X_train_raw, y_train_raw = _windows_allowing_gaps(catchment_df, train_years)
    X_val, y_val = _windows_allowing_gaps(catchment_df, val_years)
    X_test, y_test = _windows_allowing_gaps(catchment_df, test_years)

    X_train_raw = X_train_raw[y_train_raw == 0]

    n_features = X_train_raw.shape[-1]
    scaler = StandardScaler().fit(X_train_raw.reshape(-1, n_features))

    def scale(X):
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    return scale(X_train_raw), scale(X_val), y_val, scale(X_test), y_test


def run_fold(label, X_train, X_val, y_val, X_test, y_test):
    if len(X_train) == 0 or len(X_val) == 0 or len(X_test) == 0 or y_val.sum() == 0:
        print(f"{label}: skipped, empty split or no validation positives")
        return None
    drift_ratio, precision, recall, f1, n_val_pos, n_test_pos = train_one(
        label, X_train, X_val, y_val, X_test, y_test
    )
    print(
        f"{label}\n"
        f"  val positives={n_val_pos}  test positives={n_test_pos}  drift ratio={drift_ratio:.2f}\n"
        f"  precision={precision:.3f}  recall={recall:.3f}  f1={f1:.3f}"
    )
    return {"label": label, "val_pos": n_val_pos, "test_pos": n_test_pos,
            "drift_ratio": drift_ratio, "precision": precision, "recall": recall, "f1": f1}


def main():
    set_seeds()
    df = load_raw_data()

    print(f"=== Strategy A: catchment-specific chronological window ({CATCHMENT}) ===")
    print(f"train < {STRATEGY_A['val_start']}, val [{STRATEGY_A['val_start']}, {STRATEGY_A['test_start']}), "
          f"test [{STRATEGY_A['test_start']}, {STRATEGY_A['test_end']}]")
    X_train, X_val, y_val, X_test, y_test = bounded_split(df, CATCHMENT, **STRATEGY_A)
    run_fold("Strategy A", X_train, X_val, y_val, X_test, y_test)

    print(f"\n=== Strategy B: leave-one-event-out ({CATCHMENT}) ===")
    results = []
    for fold in STRATEGY_B_FOLDS:
        X_train, X_val, y_val, X_test, y_test = flexible_split(
            df, CATCHMENT, fold["train_years"], fold["val_years"], fold["test_years"]
        )
        r = run_fold(fold["label"], X_train, X_val, y_val, X_test, y_test)
        if r:
            results.append(r)

    if results:
        pooled_tp = sum(r["recall"] * r["test_pos"] for r in results)
        pooled_test_pos = sum(r["test_pos"] for r in results)
        pooled_recall = pooled_tp / pooled_test_pos if pooled_test_pos else 0.0
        mean_f1 = sum(r["f1"] for r in results) / len(results)
        print(f"\nStrategy B summary across {len(results)} usable folds: "
              f"mean F1={mean_f1:.3f}, pooled recall={pooled_recall:.3f}")


if __name__ == "__main__":
    main()
