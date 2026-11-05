"""Compares the current LSTM-autoencoder-plus-threshold approach against
several supervised and unsupervised alternatives, to see whether a
different model closes the gap to a 50% precision / 65% recall target
that threshold placement alone could not reach.

The autoencoder's own threshold search was always limited to the signal
sitting in each catchment's VALIDATION period (13 positives or fewer for
six of seven catchments), because the autoencoder itself is trained only
on normal days, never on a labelled flood day. A supervised classifier
does not have that restriction: it can learn directly from every labelled
flood day in the much longer TRAINING period (2010-2021), which is checked
and printed below before anything is trained, since that gap is the whole
reason to expect a supervised model to do better.

Every candidate model uses the same six engineered inputs for the final
day of each 14-day window: the five raw features already used for the
LSTM (rainfall_mm, river_discharge_m3s, rainfall_3day, rainfall_7day,
discharge_change) plus that catchment's own trained LSTM autoencoder's
reconstruction error on that window, so the comparison is additive to the
existing pipeline rather than a replacement for it. All catchments are
pooled together for training, with the catchment itself included as a
feature, since pooling is what makes the richer training-period signal
usable for catchments that have very little of it on their own (Nzoia,
Nyando). Thresholds are chosen on pooled validation, by F1, exactly as
for the LSTM threshold work, and never on test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tensorflow import keras

from src.config import CATCHMENTS, FEATURE_COLUMNS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits, chronological_split, make_windows
from src.scoring import reconstruction_error, slugify


def build_labelled_table(df: pd.DataFrame, autoencoder_splits: dict, autoencoder_models: dict):
    """One row per (catchment, window), every split, with every day's true
    label kept (train included), plus the autoencoder's own reconstruction
    error as an extra column."""
    rows = []
    for catchment in CATCHMENTS:
        train_df, val_df, test_df = chronological_split(df, catchment)
        scaler = autoencoder_splits[catchment].scaler
        model = autoencoder_models[catchment]

        for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
            X_raw, y, dates = make_windows(split_df)
            n, w, f = X_raw.shape
            X_scaled = scaler.transform(X_raw.reshape(-1, f)).reshape(n, w, f)
            errors = reconstruction_error(model, X_scaled)
            final_day = X_raw[:, -1, :]

            part = pd.DataFrame(final_day, columns=FEATURE_COLUMNS)
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


def evaluate(name, scores_test, y_test, catchments_test, threshold):
    y_pred = (scores_test > threshold).astype(int)
    rows = []
    for catchment in CATCHMENTS:
        mask = catchments_test == catchment
        if mask.sum() == 0:
            continue
        precision = precision_score(y_test[mask], y_pred[mask], zero_division=0)
        recall = recall_score(y_test[mask], y_pred[mask], zero_division=0)
        f1 = f1_score(y_test[mask], y_pred[mask], zero_division=0)
        rows.append((name, catchment, precision, recall, f1))
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    rows.append((name, "All 7 (combined)", precision, recall, f1))
    return rows


def main():
    df = load_raw_data()
    autoencoder_splits = build_all_splits(df)
    autoencoder_models = {
        name: keras.models.load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
        for name in CATCHMENTS
    }

    table = build_labelled_table(df, autoencoder_splits, autoencoder_models)

    print("Training-period positives per catchment (never available to the autoencoder itself):")
    print(table[table.split == "train"].groupby("catchment")["label"].sum().to_string())
    print()

    feature_cols = FEATURE_COLUMNS + ["reconstruction_error"]
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

    results = []

    log_reg = LogisticRegression(class_weight="balanced", max_iter=1000).fit(X_train, y_train)
    scores_val = log_reg.predict_proba(X_val)[:, 1]
    scores_test = log_reg.predict_proba(X_test)[:, 1]
    threshold = best_f1_threshold(scores_val, y_val)
    results += evaluate("LogisticRegression", scores_test, y_test, catchments_test, threshold)

    rf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced", max_depth=8, random_state=42
    ).fit(X_train, y_train)
    scores_val = rf.predict_proba(X_val)[:, 1]
    scores_test = rf.predict_proba(X_test)[:, 1]
    threshold = best_f1_threshold(scores_val, y_val)
    results += evaluate("RandomForest", scores_test, y_test, catchments_test, threshold)

    gb = GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=42).fit(
        X_train, y_train, sample_weight=sample_weight
    )
    scores_val = gb.predict_proba(X_val)[:, 1]
    scores_test = gb.predict_proba(X_test)[:, 1]
    threshold = best_f1_threshold(scores_val, y_val)
    results += evaluate("GradientBoosting", scores_test, y_test, catchments_test, threshold)

    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=42).fit(
        X_train[y_train == 0]
    )
    scores_val = -iso.score_samples(X_val)
    scores_test = -iso.score_samples(X_test)
    threshold = best_f1_threshold(scores_val, y_val)
    results += evaluate("IsolationForest", scores_test, y_test, catchments_test, threshold)

    results_df = pd.DataFrame(results, columns=["model", "catchment", "precision", "recall", "f1"])
    pd.set_option("display.width", 120)
    for model_name in results_df["model"].unique():
        print(f"\n{model_name}")
        print(results_df[results_df.model == model_name].drop(columns="model").to_string(index=False))


if __name__ == "__main__":
    main()
