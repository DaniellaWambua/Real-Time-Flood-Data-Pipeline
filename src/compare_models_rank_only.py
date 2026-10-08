"""Tests whether removing every absolute-scale feature, keeping only
self-relative percentile ranks, fixes what the richer-feature experiment
just showed: a model given both absolute and self-relative features
leans almost entirely on the absolute ones (rainfall_30day carried 0.40
of gradient boosting's feature importance, rainfall_rank60 only 0.015),
because absolute rainfall accumulation is a strong predictor on the
training years and the model has no reason to prefer a weaker-looking
but more robust signal over a stronger-looking but drift-sensitive one.

This version does not give it the choice. The only inputs are rainfall_mm
and river_discharge_m3s, each expressed as a percentile rank against that
catchment's own trailing 60 days, nothing absolute, not even the
autoencoder's reconstruction error, since that has shown the same
drift sensitivity as the raw features it is computed from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

from src.config import CATCHMENTS
from src.data_loading import load_raw_data
from src.preprocessing import chronological_split, make_windows

RANK_FEATURE_COLUMNS = ["rainfall_rank60", "discharge_rank60"]


def percentile_rank(series: pd.Series, window: int = 60, min_periods: int = 10) -> pd.Series:
    rank = series.rolling(window, min_periods=min_periods).apply(
        lambda w: 100.0 * (w.iloc[:-1] < w.iloc[-1]).mean() if len(w) > 1 else 50.0, raw=False
    )
    return rank.fillna(50.0)


def add_rank_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["catchment", "date"]).copy()
    parts = []
    for catchment, group in df.groupby("catchment", sort=False):
        group = group.sort_values("date").copy()
        group["rainfall_rank60"] = percentile_rank(group["rainfall_mm"])
        group["discharge_rank60"] = percentile_rank(group["river_discharge_m3s"])
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


def build_labelled_table(df: pd.DataFrame):
    rows = []
    for catchment in CATCHMENTS:
        train_df, val_df, test_df = chronological_split(df, catchment)
        for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
            _, y, dates = make_windows(split_df)
            rank_final_day = split_df[RANK_FEATURE_COLUMNS].to_numpy()[14 - 1 :]
            part = pd.DataFrame(rank_final_day, columns=RANK_FEATURE_COLUMNS)
            part["catchment"] = catchment
            part["split"] = split_name
            part["label"] = y
            part["date"] = dates
            rows.append(part)
    return pd.concat(rows, ignore_index=True)


def best_f1_threshold(scores, y):
    candidates = np.unique(scores)
    if len(candidates) > 200:
        candidates = np.quantile(scores, np.linspace(0, 1, 200))
    best = (-1.0, candidates[0])
    for t in candidates:
        f1 = f1_score(y, (scores > t).astype(int), zero_division=0)
        if f1 > best[0]:
            best = (f1, t)
    return best[1]


def main():
    df = load_raw_data()
    df = add_rank_features(df)
    table = build_labelled_table(df)

    train = table[table.split == "train"]
    val = table[table.split == "val"]
    test = table[table.split == "test"]

    scaler = StandardScaler().fit(train[RANK_FEATURE_COLUMNS])
    X_train = scaler.transform(train[RANK_FEATURE_COLUMNS])
    X_val = scaler.transform(val[RANK_FEATURE_COLUMNS])
    X_test = scaler.transform(test[RANK_FEATURE_COLUMNS])
    y_train = train["label"].to_numpy()
    y_val = val["label"].to_numpy()
    y_test = test["label"].to_numpy()
    catchments_test = test["catchment"].to_numpy()

    n_pos, n_neg = int(y_train.sum()), int((y_train == 0).sum())
    sample_weight = np.where(y_train == 1, n_neg / n_pos, 1.0)

    gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=42).fit(
        X_train, y_train, sample_weight=sample_weight
    )
    scores_val = gb.predict_proba(X_val)[:, 1]
    scores_test = gb.predict_proba(X_test)[:, 1]
    threshold = best_f1_threshold(scores_val, y_val)
    y_pred = (scores_test > threshold).astype(int)

    print(f"{'catchment':<18}{'precision':>12}{'recall':>10}{'f1':>10}")
    for name in CATCHMENTS:
        mask = catchments_test == name
        if mask.sum() == 0:
            continue
        precision = precision_score(y_test[mask], y_pred[mask], zero_division=0)
        recall = recall_score(y_test[mask], y_pred[mask], zero_division=0)
        f1 = f1_score(y_test[mask], y_pred[mask], zero_division=0)
        print(f"{name:<18}{precision:>12.3f}{recall:>10.3f}{f1:>10.3f}")

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    print(f"{'All 7 (combined)':<18}{precision:>12.3f}{recall:>10.3f}{f1:>10.3f}")

    importances = pd.Series(gb.feature_importances_, index=RANK_FEATURE_COLUMNS).sort_values(ascending=False)
    print("\nFeature importances (gradient boosting):")
    print(importances.to_string())


if __name__ == "__main__":
    main()
