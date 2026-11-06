"""
Read-only API endpoints for the Flood Risk Dashboard Module (proposal
3.6.6), serving the data its React frontend needs: the catchment map,
the data stream monitor's time series, and the alert management screen's
filterable list. All require a logged-in session (login_required), per
the proposal's "authenticated users" framing; none of this writes data.
"""

import datetime

from flask import Blueprint, jsonify, request, session

import config
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


@dashboard_bp.route("/alerts", methods=["GET"])
@login_required
def list_alerts():
    """Alert Management screen: filterable by severity, catchment and
    status. Active-only is just status=active on this same endpoint,
    which also covers the main dashboard's active-alerts summary."""
    severity = request.args.get("severity")
    catchment = request.args.get("catchment")
    status = request.args.get("status")
    limit = min(request.args.get("limit", default=100, type=int) or 100, 500)

    sql = (
        "SELECT a.id, a.severity, a.status, a.created_at, a.updated_at, "
        "ca.name AS catchment, a.anomaly_detection_result_id "
        "FROM alerts a "
        "JOIN catchment_areas ca ON ca.id = a.catchment_id "
        "WHERE ca.is_active "
    )
    params = []
    if severity:
        sql += "AND a.severity = %s "
        params.append(severity)
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    if status:
        sql += "AND a.status = %s "
        params.append(status)
    sql += "ORDER BY a.created_at DESC LIMIT %s"
    params.append(limit)

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


@dashboard_bp.route("/alerts/summary", methods=["GET"])
@login_required
def alerts_summary():
    """Alert Management screen's summary cards: total/active/resolved and
    the severity breakdown across the WHOLE matching set, not just the
    page /alerts returns. /alerts caps at 500 rows, which the real
    seeded data blows past (the Kafka test run alone raised 1,828
    alerts), so counting the rows /alerts hands back would silently
    undercount these cards; this does the counting in SQL instead.
    Optionally scoped to one catchment, same as /alerts, but
    deliberately ignores severity/status, since breaking those down is
    the whole point of the cards."""
    catchment = request.args.get("catchment")

    sql = (
        "SELECT a.status, a.severity, COUNT(*) AS count "
        "FROM alerts a "
        "JOIN catchment_areas ca ON ca.id = a.catchment_id "
        "WHERE ca.is_active "
    )
    params = []
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "GROUP BY a.status, a.severity"

    rows = db.query_all(sql, tuple(params))

    summary = {"total": 0, "active": 0, "resolved": 0, "low": 0, "medium": 0, "high": 0}
    # Per-severity status split for the breakdown table (3.4.6's alert
    # management screen): how many of each severity are still active
    # versus already resolved. Built from the same grouped rows as the
    # flat totals above rather than a second query.
    by_severity = {
        "low": {"active": 0, "resolved": 0},
        "medium": {"active": 0, "resolved": 0},
        "high": {"active": 0, "resolved": 0},
    }
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
    """Alert management screen's over-time panel: alert counts bucketed
    by day, counted in SQL for the same reason /alerts/summary is - the
    500-row page /alerts returns would undercount a day's real total
    against the real ~1,828-row table. Scoped to catchment only, same
    as the summary cards above it."""
    catchment = request.args.get("catchment")

    sql = (
        "SELECT date_trunc('day', a.created_at) AS day, COUNT(*) AS count "
        "FROM alerts a "
        "JOIN catchment_areas ca ON ca.id = a.catchment_id "
        "WHERE ca.is_active "
    )
    params = []
    if catchment:
        sql += "AND ca.name = %s "
        params.append(catchment)
    sql += "GROUP BY day ORDER BY day"

    rows = db.query_all(sql, tuple(params))
    return jsonify(_serialize(rows))


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


@dashboard_bp.route("/users", methods=["GET"])
@role_required("system_administrator")
def list_users():
    """System Administration screen's user management panel. Restricted
    to system_administrator (config.ROLES), unlike the other endpoints
    above which only require being logged in. Password hashes are never
    returned."""
    rows = db.query_all(
        "SELECT id, username, role, is_active, created_at, email "
        "FROM users ORDER BY username"
    )
    return jsonify(_serialize(rows))


@dashboard_bp.route("/users", methods=["POST"])
@role_required("system_administrator")
def create_user_route():
    """Create a user from the System Administration screen itself,
    rather than only from the create_user.py CLI script (which still
    works, nothing here replaces it)."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role")
    email = (data.get("email") or "").strip() or None

    if not username or not password or not role:
        return jsonify({"error": "username, password and role are required"}), 400
    if role not in config.ROLES:
        return jsonify({"error": f"role must be one of {', '.join(config.ROLES)}"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if models.get_user_by_username(username) is not None:
        return jsonify({"error": f"a user named '{username}' already exists"}), 409
    if email is not None and models.get_user_by_email(email) is not None:
        return jsonify({"error": f"'{email}' is already linked to another account"}), 409

    user_id = models.create_user(username, password, role, email=email)
    models.log_event(session.get("username"), "user_created", f"{username} ({role})")

    return jsonify(
        {"id": user_id, "username": username, "role": role, "is_active": True, "email": email}
    ), 201


@dashboard_bp.route("/users/<int:user_id>", methods=["PATCH"])
@role_required("system_administrator")
def update_user_route(user_id):
    """Edit a user from the System Administration screen: role, active
    status and/or password, whichever fields are present in the body.
    create_user.py/change_password.py remain the CLI equivalents; this
    is the same operations through the web UI instead."""
    data = request.get_json(silent=True) or {}
    target = models.get_user_by_id(user_id)
    if target is None:
        return jsonify({"error": "no such user"}), 404

    if "is_active" in data and not data["is_active"] and user_id == session.get("user_id"):
        return jsonify({"error": "you cannot deactivate your own account"}), 400

    if "role" in data:
        role = data["role"]
        if role not in config.ROLES:
            return jsonify({"error": f"role must be one of {', '.join(config.ROLES)}"}), 400
        models.update_user_role(user_id, role)
        models.log_event(
            session.get("username"), "user_role_changed", f"{target['username']} -> {role}"
        )

    if "is_active" in data:
        is_active = bool(data["is_active"])
        models.set_user_active(user_id, is_active)
        action = "user_reactivated" if is_active else "user_deactivated"
        models.log_event(session.get("username"), action, target["username"])

    if "password" in data:
        new_password = data["password"]
        if len(new_password) < 8:
            return jsonify({"error": "password must be at least 8 characters"}), 400
        models.update_password(target["username"], new_password)
        models.log_event(session.get("username"), "user_password_reset", target["username"])

    if "email" in data:
        email = (data["email"] or "").strip() or None
        if email is not None:
            existing = models.get_user_by_email(email)
            if existing is not None and existing["id"] != user_id:
                return jsonify({"error": f"'{email}' is already linked to another account"}), 409
        models.set_user_email(user_id, email)
        action = "user_google_email_set" if email else "user_google_email_cleared"
        models.log_event(session.get("username"), action, target["username"])

    updated = models.get_user_by_id(user_id)
    return jsonify(
        {
            "id": updated["id"],
            "username": updated["username"],
            "role": updated["role"],
            "is_active": updated["is_active"],
            "email": updated["email"],
        }
    )


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

