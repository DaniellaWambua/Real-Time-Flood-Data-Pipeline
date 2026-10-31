"""Standalone model-hosting service for live flood anomaly scoring.

A small Flask app, deliberately separate from ingestion/ and backend/:
it is the one place TensorFlow/Keras gets loaded for *serving* (as
opposed to training), so the Kafka consumer stays a light, fast process
that just calls this over HTTP. This is the "hosting the model" piece
of proposal 3.6.4's model-driven anomaly detection, sitting between the
stream processor and the anomaly_detection_results table it writes to.

Two different kinds of model are served side by side, for comparison
in front of the supervisor rather than a single committed choice:

- The unsupervised LSTM Autoencoder (src/train.py), one model per
  catchment, scored by reconstruction error against a threshold.
- The pooled supervised classifiers from src/model_selection.py (LSTM,
  1D CNN, Gradient Boosting, Random Forest, XGBoost, and the LSTM +
  Random Forest probability average), one shared model across every
  catchment (catchment identity is already a feature column), scored
  by predicted probability against a threshold.

An optional "model" field on /score picks which one runs, defaulting
to "autoencoder" so the existing consumer keeps working unchanged
until it is updated to ask for the others too.

Run from the repository root: python -m model_service.app
(FLOOD_DATASET defaults to src.config's current default, same as
training; MODEL_SERVICE_PORT defaults to 5002, since 5000 is taken by
macOS AirPlay and 5001 is the dashboard API, see backend/README notes.)
"""

from __future__ import annotations

import json
import os

import joblib
import numpy as np
from flask import Flask, jsonify, request
from tensorflow import keras

from src.config import CATCHMENTS, DATASET, MODELS_DIR
from src.scoring import slugify

app = Flask(__name__)

CLASSIFIERS_DIR = MODELS_DIR / "flood_classifiers" / DATASET
MODEL_SELECTION_RESULTS_DIR = MODELS_DIR.parent / "reports" / "model_selection" / DATASET

# Request-facing model name -> the on-disk slug src/model_selection.py
# saved it under (slug(name) there lowercases and underscores the
# model's display name, e.g. "Random Forest" -> "random_forest").
CLASSIFIER_SLUGS = {
    "lstm_classifier": "lstm",
    "1d_cnn": "1d_cnn",
    "gradient_boosting": "gradient_boosting",
    "random_forest": "random_forest",
    "xgboost": "xgboost",
}

# Of the above, which ones read a window of days rather than just the
# final day's (already rolling/rank-summarised) feature row.
SEQUENCE_CLASSIFIERS = {"lstm_classifier", "1d_cnn"}

# LSTM + Random Forest, averaged. Never fit or saved as its own model
# (see src/model_selection.py's combine()): only its chosen threshold
# is saved, in reports/model_selection/<DATASET>/, so it is scored here
# by re-using the two classifiers above rather than loading anything
# of its own.
COMBINED_MODEL = "lstm_and_random_forest"

# Lazily loaded and cached, so a request for a model/catchment nobody
# has asked for yet pays the (one-off) load cost, not every request,
# and missing artefacts fail clearly rather than crashing the service
# at startup. Kept as two separate caches because the two kinds of
# model are keyed differently (per catchment vs per classifier name).
_AUTOENCODER_CACHE: dict[str, dict] = {}
_CLASSIFIER_CACHE: dict[str, dict] = {}
_combined_threshold_cache: dict[str, float] = {}


# --------------------------------------------------------- autoencoder

def _load_autoencoder(catchment: str) -> dict:
    if catchment in _AUTOENCODER_CACHE:
        return _AUTOENCODER_CACHE[catchment]

    if catchment not in CATCHMENTS:
        raise ValueError(f"{catchment!r} is not one of the configured catchments: {CATCHMENTS}")

    slug = slugify(catchment)
    model_path = MODELS_DIR / f"lstm_autoencoder_{slug}.keras"
    scaler_path = MODELS_DIR / f"scaler_{slug}.joblib"
    metadata_path = MODELS_DIR / f"metadata_{slug}.json"

    for path in (model_path, scaler_path, metadata_path):
        if not path.exists():
            raise FileNotFoundError(
                f"{path} does not exist. src/train.py now saves the scaler and "
                f"metadata alongside the model (joblib/json), but only for runs "
                f"made after that change; re-run `python -m src.train` and pull "
                f"the resulting models/ files if this catchment predates it."
            )

    with open(metadata_path) as f:
        metadata = json.load(f)

    entry = {
        "model": keras.models.load_model(model_path),
        "scaler": joblib.load(scaler_path),
        "metadata": metadata,
    }
    _AUTOENCODER_CACHE[catchment] = entry
    return entry


def _score_autoencoder(catchment: str, window) -> dict:
    entry = _load_autoencoder(catchment)
    metadata = entry["metadata"]
    expected_len = metadata["window_length"]
    expected_features = metadata["feature_columns"]

    X = np.asarray(window, dtype=float)
    if X.shape != (expected_len, len(expected_features)):
        raise ValueError(
            f"window must be shaped ({expected_len}, {len(expected_features)}) "
            f"to match feature_columns {expected_features}, got {X.shape}"
        )

    scaled = entry["scaler"].transform(X).reshape(1, expected_len, len(expected_features))
    reconstructed = entry["model"].predict(scaled, verbose=0)

    # Same scoring rule as src/scoring.py's reconstruction_error: only the
    # final day's reconstruction error is the anomaly signal, because the
    # flood label belongs to that one day, not the window average.
    anomaly_score = float(np.mean(np.square(scaled[0, -1, :] - reconstructed[0, -1, :])))
    threshold = float(metadata["threshold"])

    return {
        "model": "autoencoder",
        "catchment": catchment,
        "anomaly_score": anomaly_score,
        "threshold_used": threshold,
        "is_anomalous": anomaly_score > threshold,
    }


# -------------------------------------------------- supervised classifiers

def _load_classifier(name: str) -> dict:
    if name in _CLASSIFIER_CACHE:
        return _CLASSIFIER_CACHE[name]

    if name not in CLASSIFIER_SLUGS:
        raise ValueError(f"{name!r} is not a known classifier: {sorted(CLASSIFIER_SLUGS)}")

    slug = CLASSIFIER_SLUGS[name]
    metadata_path = CLASSIFIERS_DIR / f"{slug}.json"
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"{metadata_path} does not exist. Run `python -m src.model_selection` "
            f"(or pull its models/flood_classifiers/{DATASET}/ output) first."
        )

    with open(metadata_path) as f:
        metadata = json.load(f)

    if name in SEQUENCE_CLASSIFIERS:
        models = [keras.models.load_model(CLASSIFIERS_DIR / fname) for fname in metadata["model_files"]]
        entry = {"metadata": metadata, "models": models}
    else:
        model = joblib.load(CLASSIFIERS_DIR / metadata["model_files"][0])
        entry = {"metadata": metadata, "model": model}

    _CLASSIFIER_CACHE[name] = entry
    return entry


def _classifier_probability(name: str, window) -> float:
    """P(flood) for one classifier, given a window of engineered feature rows.

    Scaling (plain z-score, not a pickled sklearn scaler) is applied to
    every row the same way src/model_selection.py's own training-time
    scaler was fit: per-feature mean/std, broadcast across all rows, so
    it is correct however many rows are passed in before the model-
    specific slice (a window, or just the final row) is taken.
    """
    entry = _load_classifier(name)
    metadata = entry["metadata"]
    expected_features = metadata["feature_columns"]

    X = np.asarray(window, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(expected_features):
        raise ValueError(
            f"window must be rows of {len(expected_features)} values matching "
            f"feature_columns {expected_features}, got shape {X.shape}"
        )

    mean = np.asarray(metadata["scaler_mean"], dtype=float)
    std = np.asarray(metadata["scaler_std"], dtype=float)
    scaled = (X - mean) / std

    if name in SEQUENCE_CLASSIFIERS:
        window_length = metadata["window"]
        if scaled.shape[0] < window_length:
            raise ValueError(
                f"{name} needs at least {window_length} days of history, got {scaled.shape[0]}"
            )
        seq = scaled[-window_length:].reshape(1, window_length, len(expected_features))
        # The saved model is an ensemble of seed-trained networks (see
        # src/model_selection.py's ENSEMBLE_SEEDS); P(flood) is their mean.
        probs = [float(net.predict(seq, verbose=0).ravel()[0]) for net in entry["models"]]
        return float(np.mean(probs))

    row = scaled[-1].reshape(1, -1)
    return float(entry["model"].predict_proba(row)[0, 1])


def _score_classifier(name: str, catchment: str, window) -> dict:
    entry = _load_classifier(name)
    probability = _classifier_probability(name, window)
    threshold = float(entry["metadata"]["threshold"])
    return {
        "model": name,
        "catchment": catchment,
        "probability": probability,
        "threshold_used": threshold,
        "is_anomalous": probability >= threshold,
    }


def _combined_threshold() -> float:
    if "value" in _combined_threshold_cache:
        return _combined_threshold_cache["value"]

    path = MODEL_SELECTION_RESULTS_DIR / f"{COMBINED_MODEL}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. The combined model has no file of its own "
            f"(see src/model_selection.py's combine()); run `python -m "
            f"src.model_selection` with both LSTM and Random Forest already "
            f"trained so it can average their saved predictions and write this."
        )
    with open(path) as f:
        data = json.load(f)
    threshold = float(data["threshold"])
    _combined_threshold_cache["value"] = threshold
    return threshold


def _score_combined(catchment: str, window) -> dict:
    p_lstm = _classifier_probability("lstm_classifier", window)
    p_rf = _classifier_probability("random_forest", window)
    probability = (p_lstm + p_rf) / 2
    threshold = _combined_threshold()
    return {
        "model": COMBINED_MODEL,
        "catchment": catchment,
        "probability": probability,
        "threshold_used": threshold,
        "is_anomalous": probability >= threshold,
    }


# -------------------------------------------------------------- routes

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "autoencoder_catchments_loaded": list(_AUTOENCODER_CACHE.keys()),
        "classifiers_loaded": list(_CLASSIFIER_CACHE.keys()),
        "available_models": ["autoencoder", *CLASSIFIER_SLUGS.keys(), COMBINED_MODEL],
    })


@app.route("/score", methods=["POST"])
def score():
    """Score one catchment's latest window with the requested model.

    Request body: {"catchment": "Mukuru", "window": [[...], [...], ...],
    "model": "autoencoder"}. "model" is optional and defaults to
    "autoencoder"; the other choices are the keys of CLASSIFIER_SLUGS
    plus "lstm_and_random_forest". "window" is rows of engineered
    feature values, in metadata["feature_columns"] order, NOT yet
    scaled (scaling happens here, with that model's own saved scaler),
    and NOT yet sliced to any particular length: send as many trailing
    days as are available and each model takes however many it needs.
    """
    data = request.get_json(silent=True) or {}
    catchment = data.get("catchment")
    window = data.get("window")
    model_name = data.get("model", "autoencoder")

    if not catchment or window is None:
        return jsonify({"error": "catchment and window are required"}), 400

    try:
        if model_name == "autoencoder":
            result = _score_autoencoder(catchment, window)
        elif model_name == COMBINED_MODEL:
            result = _score_combined(catchment, window)
        elif model_name in CLASSIFIER_SLUGS:
            result = _score_classifier(model_name, catchment, window)
        else:
            return jsonify({
                "error": f"unrecognised model {model_name!r}; choose one of "
                         f"{['autoencoder', *CLASSIFIER_SLUGS.keys(), COMBINED_MODEL]}"
            }), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("MODEL_SERVICE_PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=False)
