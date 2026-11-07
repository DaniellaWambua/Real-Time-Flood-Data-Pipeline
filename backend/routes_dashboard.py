"""
Read-only API endpoints for the Flood Risk Dashboard Module (proposal
3.6.6), serving the data its React frontend needs: the catchment map,
the data stream monitor's time series, and the alert management screen's
filterable list. All require a logged-in session (login_required), per
the proposal's "authenticated users" framing; none of this writes data.
"""

import datetime

from flask import Blueprint, jsonify, request, session

import db
import flood_detection
import models
from decorators import login_required, role_required


def _serialize(rows):
    """Convert any datetime/date values to ISO 8601 strings so the React
    frontend gets a predictable, standard format rather than relying on
    Flask's default (RFC 1123-style) datetime encoding."""
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                row[key] = value.isoformat()
    return rows

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api")


@dashboard_bp.route("/catchments", methods=["GET"])
@login_required
def list_catchments():
    rows = db.query_all(
        "SELECT id, name, county, "
        "ST_X(geom) AS longitude, ST_Y(geom) AS latitude "
        "FROM catchment_areas WHERE is_active ORDER BY name"
    )
    return jsonify(_serialize(rows))


@dashboard_bp.route("/readings/recent", methods=["GET"])
@login_required
def recent_readings():
    catchment = request.args.get("catchment")
    limit = min(request.args.get("limit", default=50, type=int) or 50, 500)

    sql = (
        "SELECT hdr.id, hdr.recorded_at, ca.name AS catchment, ds.name AS source, "
        "hdr.rainfall_mm, hdr.river_discharge_m3s, hdr.soil_moisture_m3m3, "
        "hdr.evaporation_mm, hdr.oni "
        "FROM hydro_data_records hdr "
        "JOIN catchment_areas ca ON ca.id = hdr.catchment_id "
        "JOIN data_sources ds ON ds.id = hdr.data_source_id "
        "WHERE ca.is_active "
    )
    params = []
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "ORDER BY hdr.recorded_at DESC LIMIT %s"
    params.append(limit)

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


# Alerts raised from the current model's flags only. Older rule-based alerts stay
# stored but are not shown, since they came from the replaced design.
ALERT_FROM = (
    "FROM alerts a "
    "JOIN catchment_areas ca ON ca.id = a.catchment_id "
    "JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
    "WHERE ca.is_active AND ar.model_name = %s "
)
ALERT_STATUSES = ["active", "acknowledged", "resolved"]
# action -> (new status, statuses it may be applied to)
ALERT_ACTIONS = {"acknowledge": ("acknowledged", ("active",)),
                 "resolve": ("resolved", ("active", "acknowledged"))}


@dashboard_bp.route("/alerts", methods=["GET"])
@login_required
def list_alerts():
    """Alert Management screen: filterable by severity, catchment and status, newest flood day
    first, with the score and threshold behind each alert."""
    severity = request.args.get("severity")
    catchment = request.args.get("catchment")
    status = request.args.get("status")
    limit = min(request.args.get("limit", default=100, type=int) or 100, 500)

    sql = (
        "SELECT a.id, a.severity, a.status, a.created_at, a.updated_at, "
        "a.acknowledged_at, a.acknowledged_by, a.resolved_at, a.resolved_by, "
        "ca.name AS catchment, a.anomaly_detection_result_id, "
        "ar.detected_at AS flood_day, ar.anomaly_score, ar.threshold_used "
        + ALERT_FROM
    )
    params = [flood_detection.current_model_name()]
    if severity:
        sql += "AND a.severity = %s "
        params.append(severity)
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    if status:
        sql += "AND a.status = %s "
        params.append(status)
    sql += "ORDER BY ar.detected_at DESC, a.id DESC LIMIT %s"
    params.append(limit)

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


@dashboard_bp.route("/alerts/summary", methods=["GET"])
@login_required
def alerts_summary():
    """Status and severity counts across the whole matching set, counted in SQL rather than
    from the capped /alerts page. Optionally scoped to one catchment."""
    catchment = request.args.get("catchment")

    sql = "SELECT a.status, a.severity, COUNT(*) AS count " + ALERT_FROM
    params = [flood_detection.current_model_name()]
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "GROUP BY a.status, a.severity"

    rows = db.query_all(sql, tuple(params))

    summary = {"total": 0, **{st: 0 for st in ALERT_STATUSES}, "low": 0, "medium": 0, "high": 0}
    by_severity = {sev: {st: 0 for st in ALERT_STATUSES} for sev in ("low", "medium", "high")}
    for row in rows:
        count = row["count"]
        summary["total"] += count
        if row["status"] in summary:
            summary[row["status"]] += count
        if row["severity"] in summary:
            summary[row["severity"]] += count
        if row["severity"] in by_severity and row["status"] in by_severity[row["severity"]]:
            by_severity[row["severity"]][row["status"]] += count

    summary["by_severity"] = by_severity
    return jsonify(summary)


@dashboard_bp.route("/alerts/trend", methods=["GET"])
@login_required
def alerts_trend():
    """Alert counts per flood day, counted in SQL. Scoped to catchment only."""
    catchment = request.args.get("catchment")

    sql = "SELECT date_trunc('day', ar.detected_at) AS day, COUNT(*) AS count " + ALERT_FROM
    params = [flood_detection.current_model_name()]
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "GROUP BY day ORDER BY day"

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


@dashboard_bp.route("/alerts/<int:alert_id>", methods=["PATCH"])
@role_required("emergency_responder")
def update_alert(alert_id):
    """Emergency Responders acknowledge an alert once seen and resolve it once dealt with.
    Each change records who and when, and is written to the system log."""
    action = (request.get_json(silent=True) or {}).get("action")
    if action not in ALERT_ACTIONS:
        return jsonify({"error": "action must be acknowledge or resolve"}), 400
    new_status, allowed_from = ALERT_ACTIONS[action]

    alert = db.query_one(
        "SELECT a.id, a.status, ca.name AS catchment FROM alerts a "
        "JOIN catchment_areas ca ON ca.id = a.catchment_id WHERE a.id = %s",
        (alert_id,),
    )
    if alert is None:
        return jsonify({"error": "no such alert"}), 404
    if alert["status"] not in allowed_from:
        return jsonify({"error": f"an alert that is {alert['status']} cannot be {new_status}"}), 409

    username = session.get("username")
    db.execute(
        f"UPDATE alerts SET status = %s, {new_status}_at = now(), {new_status}_by = %s, "
        "updated_at = now() WHERE id = %s",
        (new_status, username, alert_id),
    )
    models.log_event(username, f"alert_{new_status}", f"alert {alert_id} ({alert['catchment']})")
    return jsonify({"id": alert_id, "status": new_status})


@dashboard_bp.route("/sources", methods=["GET"])
@login_required
def list_sources():
    """System Administration screen: pipeline component (data source)
    statuses, plus each source's own last-ingested-record timestamp and
    total record count, not just the static connection_status column -
    "ensures the continuity of the data pipeline" (proposal 3.4.1)
    needs something to check that against. This reads from a historical
    Kafka replay rather than a live feed, so it's informational (when
    ingestion last actually happened), not a real-time freshness check
    against wall-clock time."""
    rows = db.query_all(
        "SELECT ds.id, ds.name, ds.source_type, ds.connection_status, ds.created_at, "
        "MAX(hdr.recorded_at) AS last_ingested_at, COUNT(hdr.id) AS record_count "
        "FROM data_sources ds "
        "LEFT JOIN hydro_data_records hdr ON hdr.data_source_id = ds.id "
        "GROUP BY ds.id "
        "ORDER BY ds.name"
    )
    return jsonify(_serialize(rows))


@dashboard_bp.route("/anomalies/recent", methods=["GET"])
@login_required
def recent_anomalies():
    """Main dashboard's "recent anomaly outputs" panel: LSTM inference
    results (proposal 3.6.4), separate from the stream processor's
    rule-based preliminary alerts in /alerts above."""
    catchment = request.args.get("catchment")
    limit = min(request.args.get("limit", default=50, type=int) or 50, 500)

    sql = (
        "SELECT ar.id, ar.detected_at, ca.name AS catchment, "
        "ar.anomaly_score, ar.threshold_used, ar.is_anomalous, "
        "ar.hydro_data_record_id "
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND ar.model_name = %s "
    )
    params = [flood_detection.current_model_name()]
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    if request.args.get("flagged") == "true":
        sql += "AND ar.is_anomalous "
    sql += "ORDER BY ar.detected_at DESC LIMIT %s"
    params.append(limit)

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


@dashboard_bp.route("/admin/stats", methods=["GET"])
@role_required("system_administrator")
def admin_stats():
    """System Administration screen's database overview panel: row
    counts across the main tables, a quick operational sanity check.
    Table names are hardcoded, one query each, rather than building SQL
    from a list, so nothing here is ever assembled from request input."""
    return jsonify(
        {
            "users": db.query_one("SELECT COUNT(*) AS count FROM users")["count"],
            "catchments": db.query_one("SELECT COUNT(*) AS count FROM catchment_areas WHERE is_active")["count"],
            "data_sources": db.query_one("SELECT COUNT(*) AS count FROM data_sources")["count"],
            "readings": db.query_one("SELECT COUNT(*) AS count FROM hydro_data_records")["count"],
            "anomalies": db.query_one(
                "SELECT COUNT(*) AS count FROM anomaly_detection_results"
            )["count"],
            "alerts": db.query_one("SELECT COUNT(*) AS count FROM alerts")["count"],
        }
    )


@dashboard_bp.route("/logs", methods=["GET"])
@role_required("system_administrator")
def list_logs():
    """System Administration screen's log panel (proposal 3.4.6 names
    this directly; nothing backed it before). Capped rather than paged,
    same reasoning as the alert management screen's own detail table:
    a fixed recent window is what an admin actually scans, not the
    whole history."""
    limit = min(request.args.get("limit", default=20, type=int) or 20, 200)
    rows = db.query_all(
        "SELECT id, occurred_at, actor, action, detail "
        "FROM system_logs ORDER BY occurred_at DESC LIMIT %s",
        (limit,),
    )
    return jsonify(_serialize(rows))

