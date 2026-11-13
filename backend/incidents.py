"""
Flood incidents: consecutive flagged days in one catchment, worked as one case.

Each flagged day is an alert (flood_detection.detect). attach() puts a new alert into the open incident
it continues, a pending or verified incident in the same catchment whose days it touches or adjoins,
or opens a new incident. Severity, provisional state and model confirmation are worked out from the
incident's alerts when it is read (INCIDENT_SELECT), so they can never drift out of step.
"""
import db
import flood_detection

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
VERIFICATIONS = ("pending", "verified", "dismissed")
STATUSES = ("active", "acknowledged", "resolved")
OUTCOMES = ("flooding_observed", "no_flooding", "not_checked")


def attach(cur, alert_id, catchment_id, day):
    """Link alert_id (flagged on day) to its incident inside the caller's transaction.
    Returns (incident_id, created) where created is True when a new incident was opened."""
    cur.execute(
        "SELECT id FROM incidents WHERE catchment_id = %s AND status <> 'resolved' AND verification <> 'dismissed' "
        "AND %s BETWEEN start_day - 1 AND end_day + 1 ORDER BY end_day DESC LIMIT 1",
        (catchment_id, day),
    )
    row = cur.fetchone()
    if row:
        incident_id, created = row[0], False
        cur.execute(
            "UPDATE incidents SET start_day = LEAST(start_day, %s), end_day = GREATEST(end_day, %s), "
            "updated_at = now() WHERE id = %s",
            (day, day, incident_id),
        )
    else:
        cur.execute(
            "INSERT INTO incidents (catchment_id, start_day, end_day) VALUES (%s, %s, %s) RETURNING id",
            (catchment_id, day, day),
        )
        incident_id, created = cur.fetchone()[0], True
    cur.execute("UPDATE alerts SET incident_id = %s WHERE id = %s", (incident_id, alert_id))
    return incident_id, created


# One row per incident, with what its alerts add up to. Only alerts from the models the dashboard shows
# count, so incidents left over from a replaced model version drop out of view.
INCIDENT_SELECT = (
    "SELECT i.id, i.catchment_id, ca.name AS catchment, ca.code AS catchment_code, ca.wards, "
    "i.start_day, i.end_day, (i.end_day - i.start_day + 1) AS days, i.verification, i.verified_by, i.verified_at, "
    "i.verification_note, i.status, i.acknowledged_by, i.acknowledged_at, i.resolved_by, i.resolved_at, "
    "i.outcome, i.outcome_places, i.outcome_note, i.created_at, i.updated_at, s.severity, s.flagged_days, "
    "s.max_score, s.provisional, s.confirmed_days, s.not_confirmed_days, "
    "(SELECT COUNT(*) FROM incident_responses r WHERE r.incident_id = i.id) AS responses "
    "FROM incidents i JOIN catchment_areas ca ON ca.id = i.catchment_id "
    "JOIN LATERAL (SELECT CASE MAX(CASE a.severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END) "
    "  WHEN 3 THEN 'high' WHEN 2 THEN 'medium' ELSE 'low' END AS severity, COUNT(*) AS flagged_days, "
    "  MAX(ar.anomaly_score) AS max_score, BOOL_AND(a.provisional) AS provisional, "
    "  COUNT(*) FILTER (WHERE a.confirmation = 'confirmed') AS confirmed_days, "
    "  COUNT(*) FILTER (WHERE a.confirmation = 'not_confirmed') AS not_confirmed_days "
    "  FROM alerts a JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
    "  WHERE a.incident_id = i.id AND ar.model_name = ANY(%(models)s)) s ON s.flagged_days > 0 "
    "WHERE ca.is_active "
)


def confirmation(row):
    """'provisional', 'confirmed', 'not_confirmed' or None (raised by the full model) for one incident row."""
    if row["provisional"]:
        return "provisional"
    if row["confirmed_days"]:
        return "confirmed"
    if row["not_confirmed_days"] and row["not_confirmed_days"] == row["flagged_days"]:
        return "not_confirmed"
    return None


def get(incident_id):
    """One incident as INCIDENT_SELECT gives it, or None."""
    row = db.query_one(INCIDENT_SELECT + "AND i.id = %(id)s",
                       {"models": flood_detection.shown_model_names(), "id": incident_id})
    if row:
        row["confirmation"] = confirmation(row)
    return row
