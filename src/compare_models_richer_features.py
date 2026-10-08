"""Re-runs the model comparison with four additional engineered features,
on top of the same six inputs used in compare_models.py, to test whether
feature richness (not model choice, already ruled out) was the actual
ceiling.

Three of the four are the kind of thing single-day snapshots and short
rolling windows miss: a longer rainfall accumulation (30 days, versus the
existing 3 and 7 day windows), a discharge acceleration term (the day to
day change of discharge_change itself, i.e. is the river's rise speeding
up or slowing down), and a rainfall-discharge interaction term (compound
wet-and-high-flow conditions, which either feature alone does not
capture).

The fourth, a day's rainfall expressed as a percentile rank against its
own catchment's trailing 60 days rather than an absolute millimetre
figure, is aimed squarely at the walk-forward finding: performance was
best (Fold B) when validation and test happened to look alike, and worst
when they diverged in either direction (Fold C, and the current
2024-2025 test window). A self-relative feature should be far less
sensitive to whether a given period is wetter or calmer than another in
absolute terms, since it only ever asks "is this unusual for this
catchment right now," which is the same question validation answered
with 2010-2022 conditions and test has to answer with 2024-2025
conditions.

Only gradient boosting is re-run here (best combined F1 among the four
alternatives tried in compare_models.py); the point is whether richer
features move its ceiling, not to repeat the full four-model comparison.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tensorflow import keras

from src.config import CATCHMENTS, FEATURE_COLUMNS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits, chronological_split, make_windows
from src.scoring import reconstruction_error, slugify

RICH_FEATURE_COLUMNS = FEATURE_COLUMNS + [
    "rainfall_30day",
    "discharge_acceleration",
    "rainfall_discharge_interaction",
    "rainfall_rank60",
]


def add_rich_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["catchment", "date"]).copy()
    parts = []
    for catchment, group in df.groupby("catchment", sort=False):
        group = group.sort_values("date").copy()
        group["rainfall_30day"] = group["rainfall_mm"].rolling(30, min_periods=1).sum()
        group["discharge_acceleration"] = group["discharge_change"].diff().fillna(0.0)
        group["rainfall_discharge_interaction"] = group["rainfall_7day"] * group["river_discharge_m3s"]
        # Percentile rank of today's rainfall against this catchment's own
        # trailing 60 days (excluding today), self-relative rather than an
        # absolute figure. First 60 days of each catchment default to 50
        # (no history yet to rank against).
        rolling_rank = (
            group["rainfall_mm"]
            .rolling(60, min_periods=10)
            .apply(lambda window: 100.0 * (window.iloc[:-1] < window.iloc[-1]).mean() if len(window) > 1 else 50.0, raw=False)
        )
        group["rainfall_rank60"] = rolling_rank.fillna(50.0)
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


def build_labelled_table(df: pd.DataFrame, autoencoder_splits: dict, autoencoder_models: dict):
    rows = []
    for catchment in CATCHMENTS:
        train_df, val_df, test_df = chronological_split(df, catchment)
        scaler = autoencoder_splits[catchment].scaler
        model = autoencoder_models[catchment]

        for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
            # Reconstruction error still comes from the original 5-feature
            # window, scored with the already-trained autoencoder.
            X_raw_orig, y, dates = make_windows(split_df, )
            X_raw_5 = split_df[FEATURE_COLUMNS].to_numpy()
            n_windows = len(split_df) - 14 + 1
            X_windows_5 = np.stack([X_raw_5[i : i + 14] for i in range(n_windows)])
            n, w, f = X_windows_5.shape
            X_scaled = scaler.transform(X_windows_5.reshape(-1, f)).reshape(n, w, f)
            errors = reconstruction_error(model, X_scaled)

            rich_final_day = split_df[RICH_FEATURE_COLUMNS].to_numpy()[14 - 1 :]

            part = pd.DataFrame(rich_final_day, columns=RICH_FEATURE_COLUMNS)
            part["reconstruction_error"] = errors
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
    df = add_rich_features(df)
    autoencoder_splits = build_all_splits(df)
    autoencoder_models = {
        name: keras.models.load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
        for name in CATCHMENTS
    }

    table = build_labelled_table(df, autoencoder_splits, autoencoder_models)

    feature_cols = RICH_FEATURE_COLUMNS + ["reconstruction_error"]
    train = table[table.split == "train"]
    val = table[table.split == "val"]
    test = table[table.split == "test"]

    scaler = StandardScaler().fit(train[feature_cols])
    X_train = scaler.transform(train[feature_cols])
    X_val = scaler.transform(val[feature_cols])
    X_test = scaler.transform(test[feature_cols])
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
    all_preds, all_labels = [], []
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

    importances = pd.Series(gb.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nFeature importances (gradient boosting):")
    print(importances.to_string())


if __name__ == "__main__":
    main()
