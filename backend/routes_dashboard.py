"""
Read-only API endpoints for the Flood Risk Dashboard Module (proposal
3.6.6), serving the data its React frontend needs: the catchment map,
the data stream monitor's time series, and the alert management screen's
filterable list. All require a logged-in session (login_required), per
the proposal's "authenticated users" framing; none of this writes data.
"""

import datetime

from flask import Blueprint, jsonify, request

import db
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
        "FROM catchment_areas ORDER BY name"
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
    )
    params = []
    if catchment:
        sql += "WHERE ca.name = %s "
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
        "WHERE 1 = 1 "
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


@dashboard_bp.route("/sources", methods=["GET"])
@login_required
def list_sources():
    """System Administration screen: pipeline component (data source)
    statuses. A minimal first version; proper logs are a later addition."""
    rows = db.query_all(
        "SELECT id, name, source_type, connection_status, created_at "
        "FROM data_sources ORDER BY name"
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
    )
    params = []
    if catchment:
        sql += "WHERE ca.name = %s "
        params.append(catchment)
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
        "SELECT id, username, role, created_at FROM users ORDER BY username"
    )
    return jsonify(_serialize(rows))

