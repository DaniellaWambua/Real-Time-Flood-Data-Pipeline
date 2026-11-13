"""
Read-only API endpoints for the Flood Risk Dashboard Module (proposal
3.6.6), serving the data its React frontend needs: the catchment map,
the data stream monitor's time series, the rainfall outlook, data source
status and the administration cards. All require a logged-in session
(login_required), per the proposal's "authenticated users" framing; none of
this writes data. Incidents have their own module, routes_incidents.py.
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
    """The Data stream screen: the ten measured readings the model reads, newest
    first, for one catchment.

    Only rows carrying those readings are returned (era5_rain_mm is the marker,
    the same test flood_detection.build_window uses). A catchment's table also
    holds older rows from the retired rule-based design, which have river
    discharge and evaporation but none of the model's own inputs; showing the two
    together would mix two different feeds on one time axis."""
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
    """System Administration screen: pipeline component (data source)
    statuses, plus each source's own last-ingested-record timestamp and
    total record count, not just the static connection_status column -
    "ensures the continuity of the data pipeline" (proposal 3.4.1)
    needs something to check that against. This reads from a historical
    Kafka replay rather than a live feed, so it's informational (when
    ingestion last actually happened), not a real-time freshness check
    against wall-clock time."""
    rows = db.query_all(
        "SELECT ds.id, ds.name, ds.source_type, ds.connection_status, ds.datasets, ds.created_at, "
        "MAX(hdr.recorded_at) AS last_ingested_at, COUNT(hdr.id) AS record_count "
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
    """System Administration screen's stat cards: row counts across the main
    tables, each with the one breakdown its card shows (how many users are still
    invited, how many alerts are still open, and so on), so a card says what
    state the system is in rather than only how many rows there are. One query
    of hardcoded sub-selects, so nothing here is ever assembled from request
    input, and the page makes a single call.

    Scoped the same way every other screen is: active catchments and the active
    feed only, and the current model's scores and the incidents raised from them, so
    these cards agree with the Data stream, Incidents and LSTM screens rather than
    counting rows left behind by the replaced rule-based design."""
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
