"""
Read-only endpoints for the dashboard: catchments, the data stream, the rainfall outlook,
data source status and the administration cards. All need a signed-in session.
Incidents are in routes_incidents.py.
"""

import datetime

from flask import Blueprint, jsonify, request

import db
import flood_detection
import incidents
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
        "SELECT id, name, county, wards, "
        "ST_X(geom) AS longitude, ST_Y(geom) AS latitude "
        "FROM catchment_areas WHERE is_active ORDER BY name"
    )
    return jsonify(_serialize(rows))


@dashboard_bp.route("/readings/recent", methods=["GET"])
@login_required
def recent_readings():
    """The Data stream screen: the ten readings the model uses, newest first, for one catchment.
        Only rows with those readings are returned (era5_rain_mm marks them), so rows left from the
        retired rule-based design are not mixed in."""
    catchment = request.args.get("catchment")
    limit = min(request.args.get("limit", default=50, type=int) or 50, 500)

    sql = (
        "SELECT hdr.id, hdr.recorded_at, ca.name AS catchment, ds.name AS source, "
        "hdr.rainfall_mm, hdr.era5_rain_mm, hdr.imerg_total_mm, hdr.imerg_max_rate, "
        "hdr.imerg_hours_ge5, hdr.soil_1, hdr.soil_2, hdr.temp_c, "
        "hdr.dewpoint_depression, hdr.pressure_hpa "
        "FROM hydro_data_records hdr "
        "JOIN catchment_areas ca ON ca.id = hdr.catchment_id "
        "JOIN data_sources ds ON ds.id = hdr.data_source_id "
        "WHERE ca.is_active AND hdr.era5_rain_mm IS NOT NULL "
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
@dashboard_bp.route("/forecast", methods=["GET"])
@login_required
def rainfall_forecast():
    """The rainfall outlook: each active catchment's latest Open-Meteo forecast from today
    onwards, with days at or above the warning level marked. A rule-based warning,
    separate from the LSTM's alerts."""
    rows = db.query_all(
        "SELECT ca.name AS catchment, ca.wards, rf.forecast_date, rf.precipitation_mm, "
        "rf.threshold_mm, rf.is_warning, rf.issued_at "
        "FROM rainfall_forecasts rf JOIN catchment_areas ca ON ca.id = rf.catchment_id "
        "WHERE ca.is_active AND rf.forecast_date >= (now() AT TIME ZONE 'Africa/Nairobi')::date "
        "ORDER BY ca.name, rf.forecast_date"
    )
    return jsonify(_serialize(rows))


@dashboard_bp.route("/sources", methods=["GET"])
@login_required
def list_sources():
    """System Administration: each data source's status, latest reading and record count.
    The forecast feed's rows are in rainfall_forecasts, not hydro_data_records, so they are counted there."""
    rows = db.query_all(
        "SELECT ds.id, ds.name, ds.source_type, ds.connection_status, ds.datasets, ds.created_at, "
        "COALESCE(MAX(hdr.recorded_at), "
        "(SELECT MAX(rf.issued_at) FROM rainfall_forecasts rf WHERE rf.source = ds.name)) AS last_ingested_at, "
        "COUNT(hdr.id) + (SELECT COUNT(*) FROM rainfall_forecasts rf WHERE rf.source = ds.name) AS record_count "
        "FROM data_sources ds "
        "LEFT JOIN hydro_data_records hdr ON hdr.data_source_id = ds.id "
        "WHERE ds.is_active "
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
        "ar.hydro_data_record_id, (ar.model_name <> %s) AS provisional "
        "FROM anomaly_detection_results ar "
        "JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND " + flood_detection.VISIBLE_RESULTS
    )
    full = flood_detection.current_model_name()
    params = [full, *flood_detection.visible_results_params()]
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
    """System Administration stat cards: row counts with the breakdown each card shows, in one query.
        Scoped like the other screens (active catchments and feed, current model) so the numbers agree."""
    counts = db.query_one(
        "SELECT (SELECT COUNT(*) FROM users) AS users, "
        "(SELECT COUNT(*) FROM users WHERE is_active AND password_hash IS NULL) AS users_pending, "
        "(SELECT COUNT(*) FROM users WHERE NOT is_active) AS users_inactive, "
        "(SELECT COUNT(*) FROM catchment_areas WHERE is_active) AS catchments, "
        "(SELECT COUNT(*) FROM catchment_areas WHERE NOT is_active) AS catchments_inactive, "
        "(SELECT COUNT(*) FROM data_sources WHERE is_active) AS data_sources, "
        "(SELECT COUNT(*) FROM data_sources WHERE is_active AND connection_status = 'connected') "
        "AS sources_connected, "
        "(SELECT COUNT(*) FROM hydro_data_records h JOIN catchment_areas ca ON ca.id = h.catchment_id "
        "JOIN data_sources ds ON ds.id = h.data_source_id WHERE ca.is_active AND ds.is_active) AS readings, "
        "(SELECT MAX(h.recorded_at)::date FROM hydro_data_records h "
        "JOIN catchment_areas ca ON ca.id = h.catchment_id "
        "JOIN data_sources ds ON ds.id = h.data_source_id "
        "WHERE ca.is_active AND ds.is_active) AS readings_last_day, "
        "(SELECT COUNT(*) FROM anomaly_detection_results ar JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND ar.model_name = %(model)s) AS anomalies, "
        "(SELECT COUNT(*) FROM anomaly_detection_results ar JOIN catchment_areas ca ON ca.id = ar.catchment_id "
        "WHERE ca.is_active AND ar.model_name = %(model)s AND ar.is_anomalous) AS anomalies_flagged, "
        "(SELECT COUNT(*) FROM (" + incidents.INCIDENT_SELECT + ") i) AS incidents, "
        "(SELECT COUNT(*) FROM (" + incidents.INCIDENT_SELECT + ") i WHERE i.verification = 'pending') "
        "AS incidents_pending, "
        "(SELECT COUNT(*) FROM (" + incidents.INCIDENT_SELECT + ") i WHERE i.verification = 'verified' "
        "AND i.status <> 'resolved') AS incidents_open",
        {"model": flood_detection.current_model_name(), "models": flood_detection.shown_model_names()},
    )
    return jsonify(_serialize([counts])[0])
