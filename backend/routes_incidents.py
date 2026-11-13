"""
Incident Management (the proposal's Alert Management screen, worked as incidents).

  Disaster Management officers  verify or dismiss each new incident before the field is told
  Emergency Responders          acknowledge a verified incident, record field updates, and resolve it,
                                saying whether flooding was found (which becomes a label for retraining)
  Government Officials          record the resources they allocated
  either of the last two        records recovery work once the incident is resolved
Emergency Responders and Government Officials only see verified incidents; Disaster Management
officers and administrators see every incident, including pending and dismissed ones.
"""
import datetime

from flask import Blueprint, jsonify, request, session

import config
import db
import flood_detection
import incidents
import models
import notify
from decorators import login_required, role_required

incidents_bp = Blueprint("incidents", __name__, url_prefix="/api")

FIELD_ROLES = ("emergency_responder", "government_official")
RESPONSE_KINDS = {"field": ("emergency_responder",), "resources": ("government_official",),
                  "recovery": ("emergency_responder", "government_official")}
MAX_NOTE = 1000


def _serialize(rows):
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                row[key] = value.isoformat()
        if "provisional" in row and "confirmed_days" in row:
            row["confirmation"] = incidents.confirmation(row)
    return rows


def _scope():
    """SQL and params limiting what the signed-in role may see."""
    if session.get("role") in FIELD_ROLES:
        return "AND i.verification = 'verified' ", {}
    return "", {}


def _filtered():
    """INCIDENT_SELECT with the request's filters and the role's scope, wrapped so filters can use its columns."""
    where, params = _scope()
    sql = "SELECT * FROM (" + incidents.INCIDENT_SELECT + where + ") i WHERE true "
    params["models"] = flood_detection.shown_model_names()
    for key in ("catchment", "severity", "verification"):
        value = request.args.get(key)
        if value:
            sql += f"AND i.{key} = %({key})s "
            params[key] = value
    status = request.args.get("status")
    if status == "open":  # not resolved and not dismissed
        sql += "AND i.status <> 'resolved' AND i.verification <> 'dismissed' "
    elif status:
        sql += "AND i.status = %(status)s "
        params["status"] = status
    return sql, params


@incidents_bp.route("/incidents", methods=["GET"])
@login_required
def list_incidents():
    """Newest first, pending verification on top for the officers who verify them."""
    sql, params = _filtered()
    params["limit"] = min(request.args.get("limit", default=100, type=int) or 100, 500)
    sql += "ORDER BY (i.verification = 'pending') DESC, i.end_day DESC, i.id DESC LIMIT %(limit)s"
    return jsonify(_serialize(db.query_all(sql, params)))


@incidents_bp.route("/incidents/summary", methods=["GET"])
@login_required
def incidents_summary():
    """Counts over the whole matching set (catchment filter only), counted in SQL."""
    where, params = _scope()
    params["models"] = flood_detection.shown_model_names()
    sql = ("SELECT i.verification, i.status, i.severity, COUNT(*) AS count FROM (" + incidents.INCIDENT_SELECT
           + where + ") i WHERE true ")
    if request.args.get("catchment"):
        sql += "AND i.catchment = %(catchment)s "
        params["catchment"] = request.args["catchment"]
    rows = db.query_all(sql + "GROUP BY i.verification, i.status, i.severity", params)
    summary = {"total": 0, "pending": 0, "verified": 0, "dismissed": 0,
               **{st: 0 for st in incidents.STATUSES}, "low": 0, "medium": 0, "high": 0}
    by_severity = {sev: {st: 0 for st in incidents.STATUSES} for sev in ("low", "medium", "high")}
    for r in rows:
        n = r["count"]
        summary["total"] += n
        summary[r["verification"]] += n
        if r["verification"] == "dismissed":
            continue  # a dismissed incident is not part of the work queue
        summary[r["status"]] += n
        summary[r["severity"]] += n
        by_severity[r["severity"]][r["status"]] += n
    summary["by_severity"] = by_severity
    return jsonify(summary)


def _visible(incident_id):
    """The incident if this role may see it, else None (so field roles get a 404 for unverified ones)."""
    incident = incidents.get(incident_id)
    if incident is None:
        return None
    if session.get("role") in FIELD_ROLES and incident["verification"] != "verified":
        return None
    return incident


@incidents_bp.route("/incidents/<int:incident_id>", methods=["GET"])
@login_required
def incident_detail(incident_id):
    """One incident with each flagged day behind it and everything recorded against it."""
    incident = _visible(incident_id)
    if incident is None:
        return jsonify({"error": "no such incident"}), 404
    days = db.query_all(
        "SELECT a.id, ar.detected_at::date AS day, a.severity, ar.anomaly_score, ar.threshold_used, ar.model_name, "
        "a.provisional, a.confirmation, a.created_at FROM alerts a "
        "JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
        "WHERE a.incident_id = %s AND ar.model_name = ANY(%s) ORDER BY day",
        (incident_id, flood_detection.shown_model_names()),
    )
    responses = db.query_all(
        "SELECT id, kind, note, author, author_role, created_at FROM incident_responses "
        "WHERE incident_id = %s ORDER BY created_at, id", (incident_id,))
    out = _serialize([dict(incident)])[0]
    out["days_flagged"] = _serialize(days)
    out["response_list"] = _serialize(responses)
    return jsonify(out)


def _recent(incident):
    """Whether the incident is recent enough for telling the field to be useful (not a replayed year)."""
    return (datetime.date.today() - incident["end_day"]).days <= config.NOTIFY_WITHIN_DAYS


@incidents_bp.route("/incidents/<int:incident_id>/verification", methods=["POST"])
@role_required("disaster_management_agency")
def verify_incident(incident_id):
    """Verify a pending incident, which tells responders and officials, or dismiss it as a false alarm."""
    data = request.get_json(silent=True) or {}
    decision, note = data.get("decision"), (data.get("note") or "").strip()[:MAX_NOTE] or None
    if decision not in ("verify", "dismiss"):
        return jsonify({"error": "decision must be verify or dismiss"}), 400
    incident = incidents.get(incident_id)
    if incident is None:
        return jsonify({"error": "no such incident"}), 404
    if incident["verification"] != "pending":
        return jsonify({"error": f"this incident is already {incident['verification']}"}), 409
    username = session.get("username")
    state = "verified" if decision == "verify" else "dismissed"
    db.execute(
        "UPDATE incidents SET verification = %s, verified_by = %s, verified_at = now(), verification_note = %s, "
        "updated_at = now() WHERE id = %s", (state, username, note, incident_id))
    models.log_event(username, f"incident_{state}", f"incident {incident_id} ({incident['catchment']})")
    told = 0
    if state == "verified" and _recent(incident):
        told = notify.incident_verified(incident, username)
    return jsonify({"id": incident_id, "verification": state, "notified": told})


@incidents_bp.route("/incidents/<int:incident_id>/acknowledge", methods=["POST"])
@role_required("emergency_responder")
def acknowledge_incident(incident_id):
    incident = _visible(incident_id)
    if incident is None:
        return jsonify({"error": "no such incident"}), 404
    if incident["status"] != "active":
        return jsonify({"error": f"an incident that is {incident['status']} cannot be acknowledged"}), 409
    username = session.get("username")
    db.execute("UPDATE incidents SET status = 'acknowledged', acknowledged_by = %s, acknowledged_at = now(), "
               "updated_at = now() WHERE id = %s", (username, incident_id))
    models.log_event(username, "incident_acknowledged", f"incident {incident_id} ({incident['catchment']})")
    return jsonify({"id": incident_id, "status": "acknowledged"})


@incidents_bp.route("/incidents/<int:incident_id>/resolve", methods=["POST"])
@role_required("emergency_responder")
def resolve_incident(incident_id):
    """Close an incident and record what was found on the ground. 'flooding_observed' and 'no_flooding'
    become label candidates for retraining (export_field_reports.py); 'not_checked' does not."""
    data = request.get_json(silent=True) or {}
    outcome = data.get("outcome")
    places = (data.get("places") or "").strip()[:MAX_NOTE] or None
    note = (data.get("note") or "").strip()[:MAX_NOTE] or None
    if outcome not in incidents.OUTCOMES:
        return jsonify({"error": "outcome must be flooding_observed, no_flooding or not_checked"}), 400
    incident = _visible(incident_id)
    if incident is None:
        return jsonify({"error": "no such incident"}), 404
    if incident["status"] == "resolved":
        return jsonify({"error": "this incident is already resolved"}), 409
    username = session.get("username")
    db.execute(
        "UPDATE incidents SET status = 'resolved', resolved_by = %s, resolved_at = now(), outcome = %s, "
        "outcome_places = %s, outcome_note = %s, updated_at = now() WHERE id = %s",
        (username, outcome, places, note, incident_id))
    models.log_event(username, "incident_resolved",
                     f"incident {incident_id} ({incident['catchment']}): {outcome.replace('_', ' ')}")
    return jsonify({"id": incident_id, "status": "resolved", "outcome": outcome})


@incidents_bp.route("/incidents/<int:incident_id>/responses", methods=["POST"])
@role_required(*FIELD_ROLES)
def add_response(incident_id):
    """Emergency Responders record field updates, Government Officials record resources they
    allocated, and either records recovery work once the incident is resolved."""
    data = request.get_json(silent=True) or {}
    kind, note = data.get("kind"), (data.get("note") or "").strip()
    role = session.get("role")
    if kind not in RESPONSE_KINDS:
        return jsonify({"error": "kind must be field, resources or recovery"}), 400
    if role not in RESPONSE_KINDS[kind]:
        return jsonify({"error": f"a {role.replace('_', ' ')} cannot record a {kind} response"}), 403
    if not note or len(note) > MAX_NOTE:
        return jsonify({"error": f"note must be 1 to {MAX_NOTE} characters"}), 400
    incident = _visible(incident_id)
    if incident is None:
        return jsonify({"error": "no such incident"}), 404
    if kind == "recovery" and incident["status"] != "resolved":
        return jsonify({"error": "recovery work is recorded once the incident is resolved"}), 409
    if kind != "recovery" and incident["status"] == "resolved":
        return jsonify({"error": "this incident is resolved; record recovery work instead"}), 409
    username = session.get("username")
    row = db.execute_returning(
        "INSERT INTO incident_responses (incident_id, kind, note, author, author_role) VALUES (%s, %s, %s, %s, %s) "
        "RETURNING id, kind, note, author, author_role, created_at",
        (incident_id, kind, note, username, role),
    )
    models.log_event(username, f"incident_response_{kind}", f"incident {incident_id} ({incident['catchment']})")
    return jsonify(_serialize([row])[0]), 201
