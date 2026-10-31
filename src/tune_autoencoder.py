"""Hyperparameter search for the LSTM autoencoder, scored by walk-forward validation.

Why walk-forward as the objective: the fixed 2023 validation year holds only
a handful of flood events per catchment, so any single-split score is mostly
noise. Here each candidate is trained and scored on three chronological folds
(A, B, C: the same ones as walk_forward_validation.py), and its score is the
mean test F1 over every (fold, catchment) pair that has test floods.

Fold D (train 2010-2022, val 2023, test 2024-2025, the current config.py
split) is deliberately NOT used for choosing hyperparameters. It is only
evaluated afterwards, for the baseline and the winning configuration, so it
remains an honest held-out check rather than something the search has seen.

Stages (--stage):
  search  random search over SEARCH_SPACE on folds A-C; results are appended
          to reports/tuning/trials_<dataset>.jsonl, so an interrupted Colab
          session resumes where it stopped instead of starting again.
  final   baseline vs best configuration on all four folds A-D.
  all     both, in order (default).

Unlike train.py this does not enable TensorFlow op-determinism: it forces
slow non-cuDNN kernels, and a search over hundreds of fits needs the GPU.
Seeds are still fixed, so differences between configurations are small-noise
rather than reproducible-to-the-bit; treat gaps under ~0.01 F1 as ties.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.callbacks import EarlyStopping

from src.config import CATCHMENTS, DATASET, EPOCHS, RANDOM_SEED, VALIDATION_SPLIT, WINDOW_LENGTH
from src.data_loading import load_raw_data
from src.model import build_lstm_autoencoder
from src.preprocessing import make_windows
from src.scoring import choose_threshold, reconstruction_error

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "tuning")

FOLDS = {
    "A": dict(val_start=2016, test_start=2018, test_end=2019),
    "B": dict(val_start=2018, test_start=2020, test_end=2021),
    "C": dict(val_start=2020, test_start=2022, test_end=2023),
    "D": dict(val_start=2023, test_start=2024, test_end=2025),  # held out from the search
}
SEARCH_FOLDS = ["A", "B", "C"]

BASELINE = dict(window_length=WINDOW_LENGTH, encoder_units=[64, 32], learning_rate=1e-3,
                batch_size=64, dropout=0.0)

SEARCH_SPACE = dict(
    window_length=[7, 14, 21, 30],
    encoder_units=[[32, 16], [64, 32], [128, 64], [64, 32, 16]],
    learning_rate=[3e-4, 1e-3, 3e-3],
    batch_size=[32, 64, 128],
    dropout=[0.0, 0.1, 0.2],
)


def set_seeds():
    os.environ["PYTHONHASHSEED"] = str(RANDOM_SEED)
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    tf.random.set_seed(RANDOM_SEED)


def fold_split(df, catchment, fold, window_length):
    """Windowed, scaled train/val/test for one catchment and fold."""
    cdf = df[df["catchment"] == catchment].sort_values("date")
    train_df = cdf[cdf["year"] < fold["val_start"]]
    val_df = cdf[(cdf["year"] >= fold["val_start"]) & (cdf["year"] < fold["test_start"])]
    test_df = cdf[(cdf["year"] >= fold["test_start"]) & (cdf["year"] <= fold["test_end"])]

    X_train, y_train, _ = make_windows(train_df, window_length)
    X_val, y_val, _ = make_windows(val_df, window_length)
    X_test, y_test, _ = make_windows(test_df, window_length)
    X_train = X_train[y_train == 0]

    n_features = X_train.shape[-1]
    scaler = StandardScaler().fit(X_train.reshape(-1, n_features))

    def scale(X):
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    return scale(X_train), scale(X_val), y_val, scale(X_test), y_test


def fit_and_score(df, catchment, fold_name, params):
    """Train one autoencoder and return test metrics, or None if the fold has
    no test floods (F1 would be undefined, not zero)."""
    X_train, X_val, y_val, X_test, y_test = fold_split(df, catchment, FOLDS[fold_name], params["window_length"])
    if y_test.sum() == 0 or y_val.sum() == 0:
        return None

    set_seeds()
    tf.keras.backend.clear_session()
    model = build_lstm_autoencoder(
        params["window_length"], X_train.shape[-1], dropout=params["dropout"],
        encoder_units=params["encoder_units"], learning_rate=params["learning_rate"],
    )
    model.fit(
        X_train, X_train, validation_split=VALIDATION_SPLIT, epochs=EPOCHS,
        batch_size=params["batch_size"], verbose=0,
        callbacks=[EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)],
    )
    errors_val = reconstruction_error(model, X_val)
    errors_test = reconstruction_error(model, X_test)
    threshold = choose_threshold(errors_val, y_val)
    y_pred = (errors_test > threshold).astype(int)
    return dict(
        catchment=catchment, fold=fold_name, test_pos=int(y_test.sum()),
        precision=precision_score(y_test, y_pred, zero_division=0),
        recall=recall_score(y_test, y_pred, zero_division=0),
        f1=f1_score(y_test, y_pred, zero_division=0),
        pr_auc=average_precision_score(y_test, errors_test),  # threshold-free ranking quality
    )


def evaluate(df, params, folds):
    rows = []
    for fold_name in folds:
        for catchment in CATCHMENTS:
            row = fit_and_score(df, catchment, fold_name, params)
            if row is not None:
                rows.append(row)
    return rows


def summarise(rows):
    r = pd.DataFrame(rows)
    return dict(f1=r.f1.mean(), precision=r.precision.mean(), recall=r.recall.mean(),
                pr_auc=r.pr_auc.mean(), n_scored=len(r))


def sample_configs(n_trials, rng):
    seen = {json.dumps(BASELINE, sort_keys=True)}
    configs = [BASELINE]  # trial 0 is always the baseline, scored the same way
    attempts = 0
    while len(configs) < n_trials and attempts < n_trials * 50:
        attempts += 1
        cfg = {k: rng.choice(v) for k, v in SEARCH_SPACE.items()}
        cfg["encoder_units"] = list(cfg["encoder_units"])
        key = json.dumps(cfg, sort_keys=True)
        if key not in seen:
            seen.add(key)
            configs.append(cfg)
    return configs


def load_trials(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def search(df, n_trials):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"trials_{DATASET}.jsonl")
    done = {json.dumps(t["params"], sort_keys=True) for t in load_trials(path)}
    configs = sample_configs(n_trials, random.Random(RANDOM_SEED))

    for i, params in enumerate(configs):
        if json.dumps(params, sort_keys=True) in done:
            print(f"[{i + 1}/{len(configs)}] already done, skipping")
            continue
        start = time.time()
        rows = evaluate(df, params, SEARCH_FOLDS)
        summary = summarise(rows)
        with open(path, "a") as f:
            f.write(json.dumps(dict(params=params, summary=summary, rows=rows), default=float) + "\n")
        print(f"[{i + 1}/{len(configs)}] F1={summary['f1']:.3f} P={summary['precision']:.3f} "
              f"R={summary['recall']:.3f} PR-AUC={summary['pr_auc']:.3f} "
              f"({time.time() - start:.0f}s) {params}", flush=True)

    trials = load_trials(path)
    trials.sort(key=lambda t: t["summary"]["f1"], reverse=True)
    print(f"\nTop 5 of {len(trials)} trials (mean F1 over folds {SEARCH_FOLDS}):")
    for t in trials[:5]:
        print(f"  F1={t['summary']['f1']:.3f} PR-AUC={t['summary']['pr_auc']:.3f}  {t['params']}")
    return trials


def final(df, trials):
    best = max(trials, key=lambda t: t["summary"]["f1"])["params"]
    print(f"\nBest configuration: {best}")
    all_rows = []
    for label, params in [("baseline", BASELINE), ("tuned", best)]:
        for row in evaluate(df, params, list(FOLDS)):
            all_rows.append(dict(config=label, **row))
    r = pd.DataFrame(all_rows)

    print("\n=== Walk-forward results, mean over catchments with test floods ===")
    print(r.groupby(["fold", "config"])[["precision", "recall", "f1", "pr_auc"]].mean().round(3).to_string())
    print("\n=== Fold D (held out from the search) per catchment ===")
    d = r[r.fold == "D"].pivot(index="catchment", columns="config", values=["precision", "recall", "f1"])
    print(d.round(3).to_string())

    os.makedirs(OUT_DIR, exist_ok=True)
    r.to_csv(os.path.join(OUT_DIR, f"walk_forward_{DATASET}.csv"), index=False)
    with open(os.path.join(OUT_DIR, f"best_params_{DATASET}.json"), "w") as f:
        json.dump(best, f, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["search", "final", "all"], default="all")
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()

    print(f"dataset={DATASET} gpu={tf.config.list_physical_devices('GPU')}")
    df = load_raw_data()
    trials = load_trials(os.path.join(OUT_DIR, f"trials_{DATASET}.jsonl"))
    if args.stage in ("search", "all"):
        trials = search(df, args.trials)
    if args.stage in ("final", "all"):
        final(df, trials)


if __name__ == "__main__":
    main()
