"""
The LSTM anomaly screen's own endpoints: what the deployed model is and how it has
done (/anomalies/model), where each catchment stands now (/anomalies/latest), the
scores list with a date range (/anomalies/scores), one month of scores for the
calendar (/anomalies/calendar) and one day in full (/anomalies/day).

Kept apart from routes_dashboard.py, which still serves the main dashboard's own
/anomalies/recent panel, the same way the activity log lives in routes_logs.py.
"""
import datetime
import json
from calendar import monthrange

from flask import Blueprint, jsonify, request

import db
import flood_detection
from decorators import login_required

anomalies_bp = Blueprint("anomalies", __name__, url_prefix="/api/anomalies")

# The 14-day window's measured inputs, in the order the day panel shows them, with
# the label and unit the dashboard uses. Keys are hydro_data_records columns.
DAY_INPUTS = [
    ("rainfall_mm", "Rain (CHIRPS)", "mm"),
    ("era5_rain_mm", "Rain (ERA5-Land)", "mm"),
    ("imerg_total_mm", "IMERG total", "mm"),
    ("imerg_max_rate", "IMERG peak rate", "mm/h"),
    ("imerg_hours_ge5", "Hours over 5 mm", ""),
    ("soil_1", "Soil 0 to 7 cm", ""),
    ("soil_2", "Soil 7 to 28 cm", ""),
    ("temp_c", "Temperature", "°C"),
    ("dewpoint_depression", "Dewpoint depression", "°C"),
    ("pressure_hpa", "Pressure", "hPa"),
]


def _iso(rows):
    """Dates and timestamps as ISO 8601 strings, as routes_dashboard.py does."""
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                row[key] = value.isoformat()
    return rows


def _date_arg(name):
    """A YYYY-MM-DD query argument, or None if absent or unparseable."""
    raw = request.args.get(name)
    try:
        return datetime.date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _filters():
    """The catchment, date range and flagged filters shared by the list endpoints."""
    sql, params = "", []
    catchment = request.args.get("catchment")
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    start, end = _date_arg("from"), _date_arg("to")
    if start:
        sql += "AND ar.detected_at::date >= %s "
        params.append(start)
    if end:
        sql += "AND ar.detected_at::date <= %s "
        params.append(end)
    if request.args.get("flagged") == "true":
        sql += "AND ar.is_anomalous "
    return sql, params


@anomalies_bp.route("/model", methods=["GET"])
@login_required
def model_status():
    """The deployed model card: what is running, how much it has scored, and the
    held-out evaluation saved beside the weights in models/flood_lstm/.

    The evaluation is read from evaluation.json rather than computed here: scoring
    precision needs the audited labels, which are a training artefact and are not
    in the operational database. Retraining writes a new evaluation.json with the
    weights, so the page always shows the deployed version's own figures."""
    cfg = json.loads((flood_detection.MODEL_DIR / "config.json").read_text())
    evaluation_file = flood_detection.MODEL_DIR / "evaluation.json"
    evaluation = json.loads(evaluation_file.read_text()) if evaluation_file.exists() else None

    live = db.query_one(
        "SELECT COUNT(*) AS days_scored, COUNT(*) FILTER (WHERE ar.is_anomalous) AS flagged, "
        "MIN(ar.detected_at)::date AS first_day, MAX(ar.detected_at)::date AS last_day "
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND ar.model_name = %s",
        (flood_detection.current_model_name(),),
    )

    return jsonify(
        {
            "name": flood_detection.current_model_name(),
            "version": cfg["version"],
            "threshold": cfg["threshold"],
            "window": cfg["window"],
            "features": cfg["features"],
            "seeds": len(cfg["seeds"]),
            "train_years": cfg["train_years"],
            "target": cfg["target"],
            "live": _iso([live])[0],
            "evaluation": evaluation,
        }
    )


@anomalies_bp.route("/scores", methods=["GET"])
@login_required
def list_scores():
    """The scores list: newest first, filtered by catchment, date range and flagged,
    with the matching total so "load more" knows when to stop."""
    where, params = _filters()
    model = [flood_detection.current_model_name()]
    joins = (
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "LEFT JOIN alerts a ON a.anomaly_detection_result_id = ar.id "
        "WHERE ca.is_active AND ar.model_name = %s "
    )
    total = db.query_one(f"SELECT COUNT(*) AS count {joins}{where}", tuple(model + params))["count"]

    limit = min(request.args.get("limit", default=50, type=int) or 50, 500)
    offset = max(request.args.get("offset", default=0, type=int) or 0, 0)
    rows = db.query_all(
        "SELECT ar.id, ar.detected_at::date AS day, ca.name AS catchment, ar.anomaly_score, "
        "ar.threshold_used, ar.is_anomalous, a.severity AS alert_severity, a.status AS alert_status "
        + joins
        + where
        + "ORDER BY ar.detected_at DESC, ca.name LIMIT %s OFFSET %s",
        tuple(model + params + [limit, offset]),
    )
    return jsonify({"total": total, "limit": limit, "offset": offset, "rows": _iso(rows)})


@anomalies_bp.route("/calendar", methods=["GET"])
@login_required
def month_calendar():
    """One catchment, one month: a score per day so the day-lookup calendar can shade
    each square. month is YYYY-MM and defaults to the last month the model scored."""
    model = flood_detection.current_model_name()
    raw = request.args.get("month") or ""
    try:
        year, month = int(raw[:4]), int(raw[5:7])
        datetime.date(year, month, 1)
    except ValueError:
        last = db.query_one(
            "SELECT MAX(detected_at)::date AS day FROM anomaly_detection_results WHERE model_name = %s",
            (model,),
        )
        today = (last or {}).get("day") or datetime.date.today()
        year, month = today.year, today.month

    first = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, monthrange(year, month)[1])
    sql = (
        "SELECT ar.detected_at::date AS day, ar.anomaly_score, ar.is_anomalous, ar.threshold_used "
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND ar.model_name = %s AND ar.detected_at::date BETWEEN %s AND %s "
    )
    params = [model, first, last_day]
    catchment = request.args.get("catchment")
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "ORDER BY ar.detected_at"

    rows = db.query_all(sql, tuple(params))
    bounds = db.query_one(
        "SELECT MIN(detected_at)::date AS first_day, MAX(detected_at)::date AS last_day "
        "FROM anomaly_detection_results WHERE model_name = %s",
        (model,),
    )
    return jsonify(
        {
            "month": f"{year:04d}-{month:02d}",
            "days": _iso(rows),
            "scored_range": _iso([bounds])[0] if bounds else None,
        }
    )


@anomalies_bp.route("/day", methods=["GET"])
@login_required
def one_day():
    """One catchment on one day: the score against the threshold, the alert it raised
    if any, and the measured inputs for that day, so a date can be looked up and
    explained in full. 404 when the model has not scored that day."""
    day = _date_arg("date")
    catchment = request.args.get("catchment")
    if not day or not catchment:
        return jsonify({"error": "catchment and date (YYYY-MM-DD) are required"}), 400

    row = db.query_one(
        "SELECT ar.id, ar.detected_at::date AS day, ca.name AS catchment, ca.id AS catchment_id, "
        "ar.anomaly_score, ar.threshold_used, ar.is_anomalous, ar.hydro_data_record_id, "
        "a.id AS alert_id, a.severity AS alert_severity, a.status AS alert_status "
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "LEFT JOIN alerts a ON a.anomaly_detection_result_id = ar.id "
        "WHERE ca.is_active AND ar.model_name = %s AND ca.name = %s AND ar.detected_at::date = %s",
        (flood_detection.current_model_name(), catchment, day),
    )
    if row is None:
        return jsonify({"error": "no score for that catchment and day"}), 404

    columns = ", ".join(column for column, _, _ in DAY_INPUTS)
    reading = db.query_one(
        f"SELECT {columns} FROM hydro_data_records "
        "WHERE catchment_id = %s AND recorded_at::date = %s "
        # a day can hold an older seeded row as well as the replayed one; prefer
        # whichever carries the model's own features, as build_window() does
        "ORDER BY (era5_rain_mm IS NOT NULL) DESC, recorded_at DESC LIMIT 1",
        (row["catchment_id"], day),
    )
    row["inputs"] = [
        {"label": label, "unit": unit, "value": (reading or {}).get(column)}
        for column, label, unit in DAY_INPUTS
    ]
    return jsonify(_iso([row])[0])
