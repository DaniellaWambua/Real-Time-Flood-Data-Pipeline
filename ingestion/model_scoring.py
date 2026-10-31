"""
Live model scoring: builds a catchment's latest feature window from
hydro_data_records and calls the model-hosting service (model_service/app.py)
for proposal 3.6.4's heavier, model-driven anomaly detection, on top of the
rule-based preliminary alerts consumer.py already raises on its own.

This needs the whole catchment set's trailing history, not just the one
catchment being scored: src/features.py's regional features average
same-day values across every catchment, and its rank features compare
today against the past RANK_HISTORY_DAYS (365) days. That is a real,
non-trivial query and recompute on every message; acceptable at this
project's replay scale, not something a higher-throughput production
system would leave unthrottled.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

import config
import db
from src.config import WINDOW_LENGTH
from src.features import ENGINEERED_FEATURE_COLUMNS, RANK_HISTORY_DAYS, add_engineered_features

# A small safety margin on top of the rank window itself, so a catchment
# right at the edge of having "enough" history doesn't flicker in and out.
HISTORY_DAYS_NEEDED = RANK_HISTORY_DAYS + WINDOW_LENGTH + 5


def fetch_recent_history(as_of_date):
    """Every catchment's readings over the trailing HISTORY_DAYS_NEEDED days.

    Always the full catchment set, never just one: regional features need
    every catchment's same-day values, not only the one being scored.
    """
    rows = db.query_all(
        "SELECT r.recorded_at AS date, c.name AS catchment, "
        "       r.rainfall_mm, r.river_discharge_m3s, r.soil_moisture_m3m3, "
        "       r.evaporation_mm, r.oni, r.rainfall_3day, r.rainfall_7day, r.discharge_change "
        "FROM hydro_data_records r "
        "JOIN catchment_areas c ON c.id = r.catchment_id "
        "WHERE r.recorded_at >= %s::timestamptz - (%s || ' days')::interval "
        "  AND r.recorded_at <= %s::timestamptz "
        "ORDER BY c.name, r.recorded_at",
        (as_of_date, HISTORY_DAYS_NEEDED, as_of_date),
    )
    return pd.DataFrame(rows)


def build_live_window(catchment, as_of_date):
    """Return (window, None), or (None, reason) if there isn't enough
    history for this catchment yet. window is window_length rows by
    len(ENGINEERED_FEATURE_COLUMNS), ready to send to the model service.
    """
    history = fetch_recent_history(as_of_date)
    if history.empty:
        return None, "no history at all yet"

    history["date"] = pd.to_datetime(history["date"])
    engineered = add_engineered_features(history)

    catchment_rows = engineered[engineered["catchment"] == catchment].sort_values("date")
    if len(catchment_rows) < WINDOW_LENGTH:
        return None, f"only {len(catchment_rows)} of {WINDOW_LENGTH} days of history so far"

    window_df = catchment_rows.tail(WINDOW_LENGTH)
    return window_df[ENGINEERED_FEATURE_COLUMNS].to_numpy().tolist(), None


def score_catchment(catchment, as_of_date):
    """The model service's score dict, or None if scoring could not be
    done right now (not enough history yet, or the service is unreachable).
    Never raises: a scoring miss should never take the consumer down, the
    rule-based alerts keep working regardless.
    """
    window, reason = build_live_window(catchment, as_of_date)
    if window is None:
        return None

    try:
        response = requests.post(
            f"{config.MODEL_SERVICE_URL}/score",
            json={"catchment": catchment, "window": window},
            timeout=config.MODEL_SERVICE_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        print(f"model service unreachable, skipping model-driven scoring for {catchment}: {exc}")
        return None

    if response.status_code != 200:
        print(f"model service returned {response.status_code} for {catchment}: {response.text}")
        return None

    return response.json()


def record_anomaly_result(catchment_id, hydro_data_record_id, score):
    """Persist the score to anomaly_detection_results, return its new id."""
    return db.execute_returning(
        "INSERT INTO anomaly_detection_results "
        "(detected_at, catchment_id, hydro_data_record_id, anomaly_score, threshold_used, is_anomalous) "
        "VALUES (now(), %s, %s, %s, %s, %s) RETURNING id",
        (
            catchment_id,
            hydro_data_record_id,
            score["anomaly_score"],
            score["threshold_used"],
            score["is_anomalous"],
        ),
    )


def raise_model_driven_alert(catchment_id, anomaly_result_id):
    """A model-driven alert, linked back to the anomaly result that
    triggered it, independent of and alongside any rule-based alert
    already raised for the same message.
    """
    db.execute(
        "INSERT INTO alerts (catchment_id, severity, status, anomaly_detection_result_id) "
        "VALUES (%s, %s, %s, %s)",
        (catchment_id, "high", "active", anomaly_result_id),
    )
