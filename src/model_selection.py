"""Tune four supervised flood classifiers, then pick the best one.

Models: LSTM (primary), 1D CNN, gradient boosting, random forest, plus
one combination, the LSTM and random forest averaged together. The LSTM
and CNN read a window of past days; the two tree models read the final
day's features, which already summarise the past through the rolling and
rank features in src/features.py.

Protocol (the 2024-2025 test set is never used to make a decision):

1. Hyperparameters are tuned with expanding-window cross-validation on
   2010-2023: train on every year before a block, validate on the block,
   for four blocks that each contain flood events. A config's score is
   its mean average precision across the four blocks.
2. A single small neural network trained once is mostly luck on ~400
   flood days (the same LSTM config scores anywhere from 0.17 to 0.26
   depending only on its random seed). So the LSTM and CNN are tuned in
   two stages: a quick single-seed pass over the whole grid, then the
   top configs re-scored as an average of ENSEMBLE_SEEDS networks, which
   is also what the final model is.
3. The best config's out-of-fold predictions (every 2015-2023 day,
   predicted by a model that never saw it) are pooled, and the
   probability cut-off with the best F1 is chosen there.
4. That config is refitted on all of 2010-2023 and scored once on test.
5. The best model is the one with the highest out-of-fold F1.

Run from the repository root:  python -m src.model_selection
(--models LSTM re-runs one model; the others' saved results are kept.
FLOOD_DATASET=v6 runs the whole comparison on the v6 dataset instead.)
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import joblib
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.metrics import (
    average_precision_score, f1_score, precision_recall_curve, precision_score, recall_score,
    roc_curve,
)

from src.config import CATCHMENTS, DATASET, LABEL_COLUMN, MODELS_DIR, RANDOM_SEED, TEST_START_YEAR
from src.data_loading import load_raw_data
from src.features import ENGINEERED_FEATURE_COLUMNS, add_engineered_features
from src.model import build_cnn_classifier, build_lstm_classifier

# Seeding alone does not make GPU training reproducible: cuDNN's LSTM
# kernels use non-deterministic reduction ops unless this is explicitly
# enabled (see src/train.py's set_seeds() for the full explanation).
tf.config.experimental.enable_op_determinism()

# Results and models are kept per dataset (see config.DATASET), so a v6
# run never overwrites v7's.
RESULTS_DIR = MODELS_DIR.parent / "reports" / "model_selection" / DATASET
CLASSIFIERS_DIR = MODELS_DIR / "flood_classifiers" / DATASET

# Every evaluated day gets a window this long, so all four models are
# scored on exactly the same days whatever window length they use.
MAX_WINDOW = 30

# (first year, last year) of each validation block; training is every
# year before the first year.
CV_FOLDS = [(2015, 2016), (2017, 2019), (2020, 2021), (2022, 2023)]

# A flagged day within this many days of a labelled flood day counts as
# "near" it in the tolerant metrics (flood register dates are reported
# event dates, which often sit a few days off the rainfall/discharge peak).
TOLERANCE_DAYS = 3

EPOCHS = 20
BATCH_SIZE = 128

# Neural networks: how many networks are averaged, and how many of the
# best single-seed configs get re-scored that way.
ENSEMBLE_SEEDS = 5
STAGE_TWO_CONFIGS = 3

PARAM_GRIDS = {
    "LSTM": {
        # Architecture fixed to the already-confirmed 5-seed stage-two
        # winner (CV AP 0.218 on v9), so this sweep isolates pos_weight_scale
        # on its own rather than re-tuning architecture and weight jointly.
        # The imbalanced-LSTM literature treats this weight as a continuous
        # hyperparameter, not the two-point 0.25/1.0 switch tried before.
        "window": [14],
        "units": [32],
        "dropout": [0.2],
        "pos_weight_scale": [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0],
    },
    "1D CNN": {
        "window": [14, 30],
        "filters": [32, 64],
        "kernel_size": [3, 5],
        "pos_weight_scale": [0.25, 1.0],
    },
    "Gradient Boosting": {
        "learning_rate": [0.01, 0.03, 0.1],
        "max_depth": [2, 3, 5],
        "max_iter": [150, 400],
        "l2_regularization": [1.0],
    },
    "Random Forest": {
        "max_depth": [8, None],
        "min_samples_leaf": [10, 20, 50, 100],
        "max_features": ["sqrt", 0.3],
    },
    "XGBoost": {
        "learning_rate": [0.01, 0.03, 0.1],
        "max_depth": [2, 3, 5],
        "n_estimators": [150, 400],
    },
}
SEQUENCE_MODELS = {"LSTM", "1D CNN"}
COMBINED_MODEL = ("LSTM", "Random Forest")


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("+", "and")


# ---------------------------------------------------------------- data

def build_dataset():
    """Windows of every engineered feature, one per (catchment, day)."""
    df = add_engineered_features(load_raw_data())
    X_parts, meta_parts = [], []
    for catchment in CATCHMENTS:
        group = df[df["catchment"] == catchment].sort_values("date")
        values = group[ENGINEERED_FEATURE_COLUMNS].to_numpy(np.float32)
        ends = np.arange(MAX_WINDOW - 1, len(group))
        X_parts.append(np.stack([values[i - MAX_WINDOW + 1 : i + 1] for i in ends]))
        meta_parts.append(group.iloc[ends][["catchment", "date", "year", LABEL_COLUMN]])
    meta = pd.concat(meta_parts, ignore_index=True)
    return np.concatenate(X_parts), meta


def split_masks(meta):
    years = meta["year"].to_numpy()
    is_test = years >= TEST_START_YEAR
    in_cv = (years >= CV_FOLDS[0][0]) & ~is_test
    return is_test, in_cv


def fit_scaler(X):
    flat = X[:, -1, :]
    return flat.mean(axis=0), flat.std(axis=0) + 1e-6


# -------------------------------------------------------------- models

def fit_predict(name, params, X_train, y_train, X_eval, n_seeds=1, return_model=False):
    """Fit a model on X_train, return P(flood) for X_eval.

    For the LSTM and CNN, n_seeds networks are trained from different
    random starting points and their probabilities averaged.
    """
    mean, std = fit_scaler(X_train)
    X_train = (X_train - mean) / std
    X_eval = (X_eval - mean) / std
    n_pos = y_train.sum()
    pos_weight = (len(y_train) - n_pos) / n_pos

    if name in SEQUENCE_MODELS:
        window = params["window"]
        X_train, X_eval = X_train[:, -window:, :], X_eval[:, -window:, :]
        model, all_probs = [], []
        for seed in range(RANDOM_SEED, RANDOM_SEED + n_seeds):
            tf.keras.utils.set_random_seed(seed)
            if name == "LSTM":
                net = build_lstm_classifier(window, X_train.shape[-1], params["units"], params["dropout"])
            else:
                net = build_cnn_classifier(window, X_train.shape[-1], params["filters"], params["kernel_size"])
            net.fit(X_train, y_train, epochs=EPOCHS, batch_size=BATCH_SIZE, verbose=0,
                    class_weight={0: 1.0, 1: pos_weight * params["pos_weight_scale"]})
            all_probs.append(net.predict(X_eval, batch_size=1024, verbose=0).ravel())
            model.append(net)
        probs = np.mean(all_probs, axis=0)
    else:
        X_train, X_eval = X_train[:, -1, :], X_eval[:, -1, :]
        if name == "Gradient Boosting":
            model = HistGradientBoostingClassifier(random_state=RANDOM_SEED, **params)
            model.fit(X_train, y_train, sample_weight=np.where(y_train == 1, pos_weight, 1.0))
        elif name == "XGBoost":
            model = XGBClassifier(scale_pos_weight=pos_weight, random_state=RANDOM_SEED,
                                  eval_metric="logloss", n_jobs=-1, **params)
            model.fit(X_train, y_train)
        else:
            model = RandomForestClassifier(n_estimators=300, class_weight="balanced_subsample",
                                           n_jobs=-1, random_state=RANDOM_SEED, **params)
            model.fit(X_train, y_train)
        probs = model.predict_proba(X_eval)[:, 1]

    if return_model:
        return probs, model, (mean, std)
    return probs


def cross_validate(name, params, X, meta, n_seeds=1):
    """Out-of-fold probabilities and mean average precision across folds."""
    y, years = meta[LABEL_COLUMN].to_numpy(), meta["year"].to_numpy()
    oof = np.full(len(y), np.nan)
    fold_aps = []
    for first, last in CV_FOLDS:
        train = years < first
        val = (years >= first) & (years <= last)
        oof[val] = fit_predict(name, params, X[train], y[train], X[val], n_seeds)
        fold_aps.append(average_precision_score(y[val], oof[val]))
    return oof, float(np.mean(fold_aps)), fold_aps


# ------------------------------------------------------------- metrics

def best_f1_threshold(y, probs):
    """Probability cut-off with the best F1; ties go to the higher cut-off."""
    precision, recall, thresholds = precision_recall_curve(y, probs)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    best = np.flatnonzero(f1 == f1.max())[-1]
    return float(thresholds[best])


def youden_threshold(y, probs):
    """Probability cut-off maximising Youden's J (recall + specificity - 1).

    A second, independent criterion reported alongside best_f1_threshold,
    not in place of it: the imbalanced-sequence literature treats
    threshold selection as a lever separate from training-time class
    weighting, and notes the F1-optimal and Youden cut-offs can land on
    genuinely different precision/recall trade-offs from the same
    trained model. roc_curve's thresholds are returned in decreasing
    order, so index [0] among ties is the higher cut-off, matching
    best_f1_threshold's own tie-break.
    """
    fpr, tpr, thresholds = roc_curve(y, probs)
    j = tpr - fpr
    best = np.flatnonzero(j == j.max())[0]
    return float(thresholds[best])


def day_metrics(y, pred):
    return {
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "flagged_days": int(pred.sum()),
        "flood_days": int(y.sum()),
    }


def tolerant_metrics(meta, pred, tol=TOLERANCE_DAYS):
    """Event-level view: is each flag near a flood, is each flood flagged?

    precision: share of flagged days within `tol` days of a labelled flood day.
    event_recall: share of flood events (consecutive labelled days) with at
    least one flagged day inside the event, widened by `tol` days each side.
    """
    near_hits, flagged, events, caught = 0, 0, 0, 0
    tol_days = pd.Timedelta(days=tol)
    for _, group in meta.assign(pred=pred).groupby("catchment"):
        flood_dates = group.loc[group[LABEL_COLUMN] == 1, "date"]
        flag_dates = group.loc[group["pred"] == 1, "date"]
        flagged += len(flag_dates)
        for d in flag_dates:
            near_hits += bool(((flood_dates - d).abs() <= tol_days).any())
        if flood_dates.empty:
            continue
        run_id = (flood_dates.diff() != pd.Timedelta(days=1)).cumsum()
        for _, run in flood_dates.groupby(run_id):
            events += 1
            caught += bool(flag_dates.between(run.min() - tol_days, run.max() + tol_days).any())
    precision = near_hits / flagged if flagged else 0.0
    event_recall = caught / events if events else 0.0
    return {"precision": precision, "event_recall": event_recall, "events": events,
            "events_caught": caught}


def evaluate(name, params, oof, test_probs, meta, cv_ap, fold_aps):
    """Pick the cut-off on out-of-fold predictions, then score CV and test."""
    is_test, in_cv = split_masks(meta)
    y = meta[LABEL_COLUMN].to_numpy()
    meta_cv, meta_test = meta[in_cv].reset_index(drop=True), meta[is_test].reset_index(drop=True)
    y_cv, y_test = y[in_cv], y[is_test]

    threshold = best_f1_threshold(y_cv, oof)
    cv_pred = (oof >= threshold).astype(int)
    test_pred = (test_probs >= threshold).astype(int)

    # Secondary threshold, reported alongside the F1-optimal one, not
    # instead of it (see youden_threshold's docstring).
    threshold_youden = youden_threshold(y_cv, oof)
    test_pred_youden = (test_probs >= threshold_youden).astype(int)

    catchments = meta_test["catchment"].to_numpy()
    return {
        "model": name,
        "params": params,
        "threshold": threshold,
        "threshold_youden": threshold_youden,
        "cv_ap": cv_ap,
        "cv_fold_aps": fold_aps,
        "cv": day_metrics(y_cv, cv_pred),
        "cv_tolerant": tolerant_metrics(meta_cv, cv_pred),
        "test_ap": average_precision_score(y_test, test_probs),
        "test": day_metrics(y_test, test_pred),
        "test_youden": day_metrics(y_test, test_pred_youden),
        "test_tolerant": tolerant_metrics(meta_test, test_pred),
        "test_per_catchment": {c: day_metrics(y_test[catchments == c], test_pred[catchments == c])
                               for c in CATCHMENTS},
    }


# ---------------------------------------------------------------- main

def _score(name, params, X_cv, meta_cv, n_seeds):
    start = time.time()
    oof, mean_ap, fold_aps = cross_validate(name, params, X_cv, meta_cv, n_seeds)
    seeds = f" x{n_seeds} seeds" if n_seeds > 1 else ""
    print(f"  {name:<18} {params}{seeds}  CV AP {mean_ap:.3f}  "
          f"folds {np.round(fold_aps, 3).tolist()}  ({time.time() - start:.0f}s)", flush=True)
    return {"params": params, "n_seeds": n_seeds, "cv_ap": mean_ap, "fold_aps": fold_aps, "oof": oof}


def _stage_one_cache(name):
    return RESULTS_DIR / f"{slug(name)}_stage_one.json"


def tune(name, X_cv, meta_cv):
    grid = PARAM_GRIDS[name]
    configs = [dict(zip(grid, values)) for values in itertools.product(*grid.values())]
    if name in SEQUENCE_MODELS:
        # Stage one only ranks configs (stage two recomputes everything it
        # keeps), so its scores are cached: re-running a neural model skips
        # the slow single-seed grid if this exact grid has been scored before.
        cache = _stage_one_cache(name)
        cached = json.loads(cache.read_text()) if cache.exists() else []
        if [t["params"] for t in cached] == configs:
            print("  stage one: reusing cached single-seed scores", flush=True)
            trials = cached
        else:
            trials = [_score(name, params, X_cv, meta_cv, 1) for params in configs]
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([{k: t[k] for k in ("params", "n_seeds", "cv_ap", "fold_aps")}
                                         for t in trials], indent=2, default=float))

        print(f"  stage two: top {STAGE_TWO_CONFIGS} configs, averaged over {ENSEMBLE_SEEDS} seeds",
              flush=True)
        top = sorted(trials, key=lambda t: t["cv_ap"], reverse=True)[:STAGE_TWO_CONFIGS]
        stage_two = [_score(name, t["params"], X_cv, meta_cv, ENSEMBLE_SEEDS) for t in top]
        return max(stage_two, key=lambda t: t["cv_ap"]), trials + stage_two
    trials = [_score(name, params, X_cv, meta_cv, 1) for params in configs]
    return max(trials, key=lambda t: t["cv_ap"]), trials


def run_model(name, X, meta):
    is_test, in_cv = split_masks(meta)
    y = meta[LABEL_COLUMN].to_numpy()
    print(f"\nTuning {name}", flush=True)
    best, trials = tune(name, X[~is_test], meta[~is_test].reset_index(drop=True))
    oof = best["oof"][in_cv[~is_test]]

    test_probs, model, (mean, std) = fit_predict(
        name, best["params"], X[~is_test], y[~is_test], X[is_test], best["n_seeds"], return_model=True)

    result = evaluate(name, best["params"], oof, test_probs, meta, best["cv_ap"], best["fold_aps"])
    result["n_seeds"] = best["n_seeds"]
    result["all_trials"] = [{k: t[k] for k in ("params", "n_seeds", "cv_ap")} for t in trials]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / f"{slug(name)}.json", "w") as f:
        json.dump(result, f, indent=2, default=float)
    np.savez(RESULTS_DIR / f"{slug(name)}_predictions.npz", oof=oof, test=test_probs)

    CLASSIFIERS_DIR.mkdir(parents=True, exist_ok=True)
    if name in SEQUENCE_MODELS:
        model_files = []
        for i, net in enumerate(model):
            # Weights only, not the full architecture+config: Keras's full-model
            # format breaks across Keras versions (a newer release can add a
            # field to a layer's saved config, such as quantization_config, that
            # an older Keras does not recognise and refuses to load), while a
            # plain weights file is just named numeric arrays. model_service/
            # app.py's _load_classifier rebuilds this same architecture in code
            # from this model's own saved params before loading these weights.
            path = CLASSIFIERS_DIR / f"{slug(name)}_seed{i}.weights.h5"
            net.save_weights(path)
            model_files.append(path.name)
    else:
        path = CLASSIFIERS_DIR / f"{slug(name)}.joblib"
        joblib.dump(model, path, compress=3)
        model_files = [path.name]
    with open(CLASSIFIERS_DIR / f"{slug(name)}.json", "w") as f:
        json.dump({
            "model": name, "params": best["params"], "threshold": result["threshold"],
            "feature_columns": ENGINEERED_FEATURE_COLUMNS,
            "window": best["params"].get("window", 1),
            "scaler_mean": mean.tolist(), "scaler_std": std.tolist(),
            "model_files": model_files,
            "note": "P(flood) is the mean of every model file's output; flag if >= threshold.",
        }, f, indent=2, default=str)


def combine(meta):
    """LSTM and random forest probabilities averaged, if both have run."""
    parts = [RESULTS_DIR / f"{slug(n)}_predictions.npz" for n in COMBINED_MODEL]
    if not all(p.exists() for p in parts):
        return None
    preds = [np.load(p) for p in parts]
    oof = np.mean([p["oof"] for p in preds], axis=0)
    test = np.mean([p["test"] for p in preds], axis=0)

    is_test, in_cv = split_masks(meta)
    y_cv, years_cv = meta[LABEL_COLUMN].to_numpy()[in_cv], meta["year"].to_numpy()[in_cv]
    fold_aps = [average_precision_score(y_cv[(years_cv >= a) & (years_cv <= b)],
                                        oof[(years_cv >= a) & (years_cv <= b)]) for a, b in CV_FOLDS]
    name = " + ".join(COMBINED_MODEL)
    result = evaluate(name, {"average_of": list(COMBINED_MODEL)}, oof, test, meta,
                      float(np.mean(fold_aps)), fold_aps)
    with open(RESULTS_DIR / f"{slug(name)}.json", "w") as f:
        json.dump(result, f, indent=2, default=float)
    return result


def summarise(meta):
    """Compare every model with saved results and record the best one."""
    results = []
    for name in PARAM_GRIDS:
        path = RESULTS_DIR / f"{slug(name)}.json"
        if path.exists():
            results.append(json.loads(path.read_text()))
    combined = combine(meta)
    if combined:
        results.append(combined)

    best_model = max(results, key=lambda r: (r["cv"]["f1"], r["cv_ap"]))
    with open(RESULTS_DIR / "summary.json", "w") as f:
        json.dump({"best_model": best_model["model"], "selected_by": "cross-validated F1",
                   "tolerance_days": TOLERANCE_DAYS, "cv_folds": CV_FOLDS,
                   "models": {r["model"]: {k: r[k] for k in ("params", "threshold", "cv_ap", "cv",
                                                              "cv_tolerant", "test_ap", "test",
                                                              "test_tolerant")}
                              for r in results}}, f, indent=2, default=float)

    print(f"\n{'':22}{'--- cross-validation 2015-2023 ---':^36}{'--- test 2024-2025 ---':^36}")
    print(f"{'model':<22}{'AP':>6}{'prec':>7}{'rec':>7}{'F1':>7}{'evRec':>7}"
          f"{'AP':>8}{'prec':>7}{'rec':>7}{'F1':>7}{'tolP':>7}{'evRec':>7}")
    for r in results:
        cv, te, tt = r["cv"], r["test"], r["test_tolerant"]
        print(f"{r['model']:<22}{r['cv_ap']:>6.3f}{cv['precision']:>7.3f}{cv['recall']:>7.3f}"
              f"{cv['f1']:>7.3f}{r['cv_tolerant']['event_recall']:>7.2f}"
              f"{r['test_ap']:>8.3f}{te['precision']:>7.3f}{te['recall']:>7.3f}{te['f1']:>7.3f}"
              f"{tt['precision']:>7.3f}{tt['event_recall']:>7.2f}")
    print(f"\n{'':22}{'--- Youden-threshold test (secondary) ---':^34}")
    print(f"{'model':<22}{'threshold':>11}{'prec':>7}{'rec':>7}{'F1':>7}")
    for r in results:
        ty = r["test_youden"]
        print(f"{r['model']:<22}{r['threshold_youden']:>11.4f}{ty['precision']:>7.3f}"
              f"{ty['recall']:>7.3f}{ty['f1']:>7.3f}")

    print(f"\nBest model (by cross-validated F1): {best_model['model']}")
    for r in results:
        print(f"\n{r['model']} test, per catchment (threshold {r['threshold']:.4f}):")
        for c, m in r["test_per_catchment"].items():
            print(f"  {c:<15} precision {m['precision']:.3f}  recall {m['recall']:.3f}  "
                  f"F1 {m['f1']:.3f}  ({m['flagged_days']} flagged, {m['flood_days']} flood days)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default=",".join(PARAM_GRIDS),
                        help="comma-separated subset of: " + ", ".join(PARAM_GRIDS))
    args = parser.parse_args()

    # Small networks train faster on the CPU. (Op determinism is left off:
    # it slows Conv1D on CPU by orders of magnitude; fixed seeds keep runs
    # close to reproducible.)
    tf.config.set_visible_devices([], "GPU")

    X, meta = build_dataset()
    for name in (m.strip() for m in args.models.split(",")):
        run_model(name, X, meta)
    summarise(meta)


if __name__ == "__main__":
    main()
