"""
Flood detection module: scores one catchment-day with the saved LSTM models in
models/flood_lstm/ and records the result in anomaly_detection_results.
"""
import json
from datetime import timedelta
from pathlib import Path

import numpy as np

import db

MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "flood_lstm"
DB_COLUMN = {"rain_mm": "rainfall_mm"}  # model feature name -> hydro_data_records column

_cfg, _models = None, None


def load_models():
    """Read config.json and the weight files once, on first use."""
    global _cfg, _models
    if _models is None:
        import tensorflow as tf
        cfg = json.loads((MODEL_DIR / "config.json").read_text())
        models = []
        for seed in cfg["seeds"]:
            m = tf.keras.Sequential([
                tf.keras.layers.Input((cfg["window"], len(cfg["features"]))),
                tf.keras.layers.LSTM(32),
                tf.keras.layers.Dropout(0.3),
                tf.keras.layers.Dense(1, activation="sigmoid"),
            ])
            m.load_weights(str(MODEL_DIR / f"lstm_raw_seed{seed}.weights.h5"))
            models.append(m)
        _cfg, _models = cfg, models
    return _cfg, _models

def current_model_name():
    """The name scores are saved under, e.g. 'lstm_raw v1', read from config.json without loading the models."""
    cfg = json.loads((MODEL_DIR / "config.json").read_text())
    return f"lstm_raw {cfg['version']}"


def severity_for(score, threshold):
    """low, medium or high by how far the score lies above the threshold, in thirds of the way to 1."""
    margin = (score - threshold) / (1 - threshold)
    return "low" if margin < 1 / 3 else "medium" if margin < 2 / 3 else "high"


def build_window(catchment_id, day):
    """The 14-day input ending on day, in the model's feature order, or (None, reason)."""
    cfg, _ = load_models()
    measured = [f for f in cfg["features"] if not f.startswith(("is_", "month_"))]
    cols = [DB_COLUMN.get(f, f) for f in measured]
    rows = db.query_all(
        f"SELECT recorded_at::date AS day, {', '.join(cols)} FROM hydro_data_records "
        "WHERE catchment_id = %s AND recorded_at::date <= %s AND era5_rain_mm IS NOT NULL "
        "ORDER BY recorded_at DESC LIMIT %s",
        (catchment_id, day, cfg["window"]),
    )[::-1]
    expected = [day - timedelta(days=i) for i in range(cfg["window"] - 1, -1, -1)]
    if [r["day"] for r in rows] != expected:
        return None, f"need {cfg['window']} consecutive days ending {day}, found {len(rows)} usable rows"
    if any(r[c] is None for r in rows for c in cols):
        return None, "a reading in the window has a missing value"
    code = db.query_one("SELECT code FROM catchment_areas WHERE id = %s", (catchment_id,))["code"]
    window = []
    for r in rows:
        v = {f: r[DB_COLUMN.get(f, f)] for f in measured}
        v["month_sin"] = np.sin(2 * np.pi * r["day"].month / 12)
        v["month_cos"] = np.cos(2 * np.pi * r["day"].month / 12)
        for f in cfg["features"]:
            if f.startswith("is_"):
                v[f] = 1.0 if f == f"is_{code}" else 0.0
        window.append([v[f] for f in cfg["features"]])
    return np.array(window, dtype="float32"), None


def score_window(window):
    """Scale with the training-year values and average the eight models' scores."""
    cfg, models = load_models()
    x = ((window - np.array(cfg["mean"])) / np.array(cfg["std"]))[np.newaxis].astype("float32")
    return float(np.mean([float(m(x, training=False)[0, 0]) for m in models]))


def detect(catchment_id, day, hydro_data_record_id=None):
    """Score one catchment-day, save the result and return it."""
    window, reason = build_window(catchment_id, day)
    if window is None:
        return {"scored": False, "reason": reason}
    cfg, _ = load_models()
    score = score_window(window)
    flagged = score >= cfg["threshold"]
    model_name = f"lstm_raw {cfg['version']}"
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO anomaly_detection_results (detected_at, catchment_id, hydro_data_record_id, "
                "model_name, anomaly_score, threshold_used, is_anomalous) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (day, catchment_id, hydro_data_record_id, model_name, score, cfg["threshold"], flagged),
            )
            result_id = cur.fetchone()[0]
            alert_id, severity = None, None
            if flagged:  # a flagged day raises an alert in the same transaction
                severity = severity_for(score, cfg["threshold"])
                cur.execute(
                    "INSERT INTO alerts (anomaly_detection_result_id, catchment_id, severity) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (result_id, catchment_id, severity),
                )
                alert_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"scored": True, "id": result_id, "score": score, "threshold": cfg["threshold"],
            "flagged": flagged, "model": model_name, "alert_id": alert_id, "severity": severity}