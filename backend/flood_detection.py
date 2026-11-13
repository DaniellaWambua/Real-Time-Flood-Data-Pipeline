"""
Flood detection module: scores one catchment-day with a saved LSTM model and records the result
in anomaly_detection_results, raising an alert when the score reaches the model's threshold.

Two models are used (decisions.md, real-time design):
  full  models/flood_lstm/, all 15 inputs including CHIRPS. CHIRPS is published about 42 days late,
        so this model confirms days.
  fast  models/flood_lstm_fast/, the same network without CHIRPS. IMERG and ERA5-Land are about
        8 days late, so this model gives a provisional score long before CHIRPS arrives.
A provisional alert is kept when the full model later scores the same day: it is re-pointed at the
full model's result and marked confirmed if the full model also flags the day, or marked not
confirmed if it does not, so acknowledgements and responses recorded against it are never lost.
"""
import json
from datetime import timedelta
from pathlib import Path

import numpy as np

import db

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MODEL_DIRS = {"full": MODELS_DIR / "flood_lstm", "fast": MODELS_DIR / "flood_lstm_fast"}
MODEL_DIR = MODEL_DIRS["full"]
DB_COLUMN = {"rain_mm": "rainfall_mm"}  # model feature name -> hydro_data_records column

_loaded = {}


def read_config(kind="full"):
    return json.loads((MODEL_DIRS[kind] / "config.json").read_text())


def has_model(kind):
    return (MODEL_DIRS[kind] / "config.json").exists()


def load_models(kind="full"):
    """Read a model's config.json and weight files once, on first use."""
    if kind not in _loaded:
        import tensorflow as tf
        cfg = read_config(kind)
        models = []
        for seed in cfg["seeds"]:
            m = tf.keras.Sequential([
                tf.keras.layers.Input((cfg["window"], len(cfg["features"]))),
                tf.keras.layers.LSTM(cfg.get("units", 32)),
                tf.keras.layers.Dropout(cfg.get("dropout", 0.3)),
                tf.keras.layers.Dense(1, activation="sigmoid"),
            ])
            m.load_weights(str(MODEL_DIRS[kind] / f"lstm_raw_seed{seed}.weights.h5"))
            models.append(m)
        _loaded[kind] = (cfg, models)
    return _loaded[kind]


def model_name(cfg):
    return f"{cfg.get('name', 'lstm_raw')} {cfg['version']}"


def current_model_name(kind="full"):
    """The name scores are saved under, e.g. 'lstm_raw v2', read from config.json without loading the models."""
    return model_name(read_config(kind))


def shown_model_names():
    """The models whose alerts the dashboard shows: the full model, and the fast one when it is installed."""
    return [current_model_name("full")] + ([current_model_name("fast")] if has_model("fast") else [])


# The scores the dashboard shows: the full model's, and the fast model's for catchment-days the full model
# has not scored yet. Use with visible_results_params(), on anomaly_detection_results aliased ar.
VISIBLE_RESULTS = (
    "(ar.model_name = %s OR (ar.model_name = %s AND NOT EXISTS (SELECT 1 FROM anomaly_detection_results f "
    "WHERE f.catchment_id = ar.catchment_id AND f.detected_at = ar.detected_at AND f.model_name = %s))) "
)


def visible_results_params():
    full = current_model_name("full")
    fast = current_model_name("fast") if has_model("fast") else full
    return [full, fast, full]


def severity_for(score, threshold):
    """low, medium or high by how far the score lies above the threshold, in thirds of the way to 1."""
    margin = (score - threshold) / (1 - threshold)
    return "low" if margin < 1 / 3 else "medium" if margin < 2 / 3 else "high"


def build_window(catchment_id, day, kind="full"):
    """The 14-day input ending on day, in the model's feature order, or (None, reason).
    One row per day: the full model only uses readings that include CHIRPS; the fast model uses any
    reading, preferring a complete one when a day has both."""
    cfg, _ = load_models(kind)
    measured = [f for f in cfg["features"] if not f.startswith(("is_", "month_"))]
    cols = [DB_COLUMN.get(f, f) for f in measured]
    need_chirps = "AND rainfall_mm IS NOT NULL " if "rain_mm" in cfg["features"] else ""
    rows = db.query_all(
        f"SELECT day, {', '.join(cols)} FROM (SELECT DISTINCT ON (recorded_at::date) recorded_at::date AS day, "
        f"{', '.join(cols)} FROM hydro_data_records "
        f"WHERE catchment_id = %s AND recorded_at::date <= %s AND era5_rain_mm IS NOT NULL {need_chirps}"
        "ORDER BY recorded_at::date DESC, (rainfall_mm IS NULL)) d ORDER BY day DESC LIMIT %s",
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


def score_window(window, kind="full"):
    """Scale with the training-year values and average the eight models' scores."""
    cfg, models = load_models(kind)
    x = ((window - np.array(cfg["mean"])) / np.array(cfg["std"]))[np.newaxis].astype("float32")
    return float(np.mean([float(m(x, training=False)[0, 0]) for m in models]))


def detect(catchment_id, day, hydro_data_record_id=None, notify=False, provisional=False):
    """Score one catchment-day, save the result and return it.
    provisional scores with the fast model (a reading without CHIRPS); otherwise the full model scores it
    and settles any provisional alert for the same day. Each new alert joins its incident. With notify, a
    new incident is sent to Disaster Management to verify, and a settled one is reported (live readings
    only; replays and rescoring pass False)."""
    import incidents  # noqa: PLC0415 - incidents imports this module
    kind = "fast" if provisional else "full"
    window, reason = build_window(catchment_id, day, kind)
    if window is None:
        return {"scored": False, "reason": reason}
    cfg, _ = load_models(kind)
    score = score_window(window, kind)
    flagged = score >= cfg["threshold"]
    name = model_name(cfg)
    severity = severity_for(score, cfg["threshold"]) if flagged else None
    alert_id, settled, incident_id, opened = None, None, None, False
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO anomaly_detection_results (detected_at, catchment_id, hydro_data_record_id, "
                "model_name, anomaly_score, threshold_used, is_anomalous) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (day, catchment_id, hydro_data_record_id, name, score, cfg["threshold"], flagged),
            )
            result_id = cur.fetchone()[0]
            earlier = None
            if not provisional and has_model("fast"):
                cur.execute(
                    "SELECT a.id FROM alerts a JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
                    "WHERE a.provisional AND ar.model_name = %s AND ar.catchment_id = %s AND ar.detected_at::date = %s",
                    (current_model_name("fast"), catchment_id, day),
                )
                earlier = cur.fetchone()
            if earlier is not None:  # the full model settles the provisional alert instead of adding another
                alert_id = earlier[0]
                if flagged:
                    settled = "confirmed"
                    cur.execute(
                        "UPDATE alerts SET anomaly_detection_result_id = %s, severity = %s, provisional = false, "
                        "confirmation = 'confirmed', updated_at = now() WHERE id = %s",
                        (result_id, severity, alert_id),
                    )
                else:
                    settled = "not_confirmed"
                    cur.execute(
                        "UPDATE alerts SET provisional = false, confirmation = 'not_confirmed', updated_at = now() "
                        "WHERE id = %s",
                        (alert_id,),
                    )
            elif flagged:  # a flagged day raises an alert, filed under its incident, in the same transaction
                cur.execute(
                    "INSERT INTO alerts (anomaly_detection_result_id, catchment_id, severity, provisional) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (result_id, catchment_id, severity, provisional),
                )
                alert_id = cur.fetchone()[0]
                incident_id, opened = incidents.attach(cur, alert_id, catchment_id, day)
            if settled:
                cur.execute("SELECT incident_id FROM alerts WHERE id = %s", (alert_id,))
                incident_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    notified = None
    if notify and incident_id is not None and (opened or settled):
        import notify as notifier  # noqa: PLC0415
        incident = incidents.get(incident_id)
        if incident is not None:
            notified = notifier.incident_settled(incident, settled) if settled else notifier.incident_to_verify(incident)
    return {"scored": True, "id": result_id, "score": score, "threshold": cfg["threshold"],
            "flagged": flagged, "model": name, "provisional": provisional, "alert_id": alert_id,
            "severity": severity, "settled": settled, "incident_id": incident_id, "new_incident": opened,
            "notified": notified}
