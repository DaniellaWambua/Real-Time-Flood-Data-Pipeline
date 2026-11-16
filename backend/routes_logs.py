"""
The Activity log for the System Administration screen, one area at a time: sign-ins and
security, user accounts, alerts and the data pipeline (models.log_category). Restricted to
the system_administrator role.
"""
import re

from flask import Blueprint, jsonify, request

import db
import models
from decorators import role_required

logs_bp = Blueprint("logs", __name__, url_prefix="/api")

PERIODS = {"1d": "1 day", "7d": "7 days", "30d": "30 days"}  # anything else means all time
OUTCOMES = {
    "success": ("login_success", "totp_enabled", "password_changed"),
    "failed": ("login_failure", "password_change_failure"),
}
ALERT_IN_DETAIL = re.compile(r"alert (\d+)")


def _period_filter(sql, params):
    period = PERIODS.get(request.args.get("period", "7d"))
    if period:
        sql += "AND occurred_at >= now() - %s::interval "
        params.append(period)
    return sql


def _with_alert_details(rows):
    """Add each alert entry's severity, catchment, flood day and score, for the alerts feed."""
    ids = sorted({int(m.group(1)) for r in rows if (m := ALERT_IN_DETAIL.search(r.get("detail") or ""))})
    if not ids:
        return rows
    found = db.query_all(
        "SELECT a.id, a.severity, ca.name AS catchment, ar.detected_at AS flood_day, "
        "ar.anomaly_score, ar.threshold_used FROM alerts a "
        "JOIN catchment_areas ca ON ca.id = a.catchment_id "
        "LEFT JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
        "WHERE a.id = ANY(%s)",
        (ids,),
    )
    by_id = {f["id"]: f for f in found}
    for r in rows:
        m = ALERT_IN_DETAIL.search(r.get("detail") or "")
        alert = by_id.get(int(m.group(1))) if m else None
        if alert:
            r["alert"] = {**alert, "flood_day": alert["flood_day"].isoformat() if alert["flood_day"] else None}
    return rows


@logs_bp.route("/logs", methods=["GET"])
@role_required("system_administrator")
def list_logs():
    """Newest first, for one area, with search, period and (for sign-ins) outcome filters.
    "Load more" passes the last id it has as before=."""
    category = request.args.get("category")
    q = (request.args.get("q") or "").strip()
    outcome = request.args.get("outcome")
    before = request.args.get("before", type=int)
    limit = min(request.args.get("limit", default=50, type=int) or 50, 500)

    sql = "SELECT id, occurred_at, actor, action, detail, category FROM system_logs WHERE true "
    params = []
    if category in models.LOG_CATEGORIES:
        sql += "AND category = %s "
        params.append(category)
    sql = _period_filter(sql, params)
    if q:
        sql += "AND (actor ILIKE %s OR detail ILIKE %s OR action ILIKE %s) "
        params += [f"%{q}%"] * 3
    if outcome in OUTCOMES:
        sql += "AND action = ANY(%s) "
        params.append(list(OUTCOMES[outcome]))
    if before:
        sql += "AND id < %s "
        params.append(before)
    sql += "ORDER BY id DESC LIMIT %s"
    params.append(limit)

    rows = db.query_all(sql, tuple(params))
    for r in rows:
        r["occurred_at"] = r["occurred_at"].isoformat()
    if category == "alerts":
        rows = _with_alert_details(rows)
    return jsonify(rows)
