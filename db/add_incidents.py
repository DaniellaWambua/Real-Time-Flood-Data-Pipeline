"""
Migration to incidents, verification, field outcomes and notifications for an older database.
Groups existing alerts into incidents, carries over their acknowledge and resolve state and responses,
then drops the per-alert workflow columns. Backfilled incidents start as pending. Safe to re-run.
Run from db/: python add_incidents.py
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402
import flood_detection  # noqa: E402

TABLES = [
    # used by every score since the LSTM went live, but missing from older copies of 02_schema.sql
    "ALTER TABLE anomaly_detection_results ADD COLUMN IF NOT EXISTS model_name TEXT",
    """CREATE TABLE IF NOT EXISTS incidents (
        id SERIAL PRIMARY KEY, catchment_id INTEGER NOT NULL REFERENCES catchment_areas(id),
        start_day DATE NOT NULL, end_day DATE NOT NULL,
        verification TEXT NOT NULL DEFAULT 'pending', verified_by TEXT, verified_at TIMESTAMPTZ, verification_note TEXT,
        status TEXT NOT NULL DEFAULT 'active', acknowledged_by TEXT, acknowledged_at TIMESTAMPTZ,
        resolved_by TEXT, resolved_at TIMESTAMPTZ, outcome TEXT, outcome_places TEXT, outcome_note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_incidents_catchment_days ON incidents (catchment_id, end_day DESC)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS incident_id INTEGER REFERENCES incidents(id)",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS provisional BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS confirmation TEXT",
    "CREATE INDEX IF NOT EXISTS idx_alerts_incident ON alerts (incident_id)",
    """CREATE TABLE IF NOT EXISTS incident_responses (
        id SERIAL PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id), kind TEXT NOT NULL,
        note TEXT NOT NULL, author TEXT NOT NULL, author_role TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_incident_responses_incident ON incident_responses (incident_id, created_at)",
    """CREATE TABLE IF NOT EXISTS notifications (
        id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL, link TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        read_at TIMESTAMPTZ)""",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS push_subscriptions (
        id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), endpoint TEXT NOT NULL UNIQUE,
        p256dh TEXT NOT NULL, auth TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
]
OLD_COLUMNS = ["status", "acknowledged_at", "acknowledged_by", "resolved_at", "resolved_by"]


def columns(table):
    return {r["column_name"] for r in db.query_all(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))}


def table_exists(name):
    return db.query_one("SELECT to_regclass(%s) AS t", (name,))["t"] is not None


for sql in TABLES:
    db.execute(sql)

old_workflow = "status" in columns("alerts")
extra = ", a.status, a.acknowledged_at, a.acknowledged_by, a.resolved_at, a.resolved_by" if old_workflow else ""
alerts = db.query_all(
    "SELECT a.id, a.catchment_id, ar.detected_at::date AS day" + extra + " FROM alerts a "
    "JOIN anomaly_detection_results ar ON ar.id = a.anomaly_detection_result_id "
    "WHERE a.incident_id IS NULL AND ar.model_name = ANY(%s) ORDER BY a.catchment_id, day, a.id",
    (flood_detection.shown_model_names(),),
)

groups, current = [], []
for a in alerts:
    if current and (a["catchment_id"] != current[-1]["catchment_id"] or a["day"] > current[-1]["day"] + timedelta(days=1)):
        groups.append(current)
        current = []
    current.append(a)
if current:
    groups.append(current)

conn = db.get_connection()
try:
    with conn.cursor() as cur:
        for g in groups:
            status, ack_by, ack_at, res_by, res_at = "active", None, None, None, None
            if old_workflow:
                states = {a["status"] for a in g}
                if states == {"resolved"}:
                    status = "resolved"
                    last = max(g, key=lambda a: a["resolved_at"] or a["day"])
                    res_by, res_at = last["resolved_by"], last["resolved_at"]
                elif states & {"acknowledged", "resolved"}:
                    status = "acknowledged"
                if status != "active":
                    acked = [a for a in g if a["acknowledged_at"]]
                    if acked:
                        first = min(acked, key=lambda a: a["acknowledged_at"])
                        ack_by, ack_at = first["acknowledged_by"], first["acknowledged_at"]
            cur.execute(
                "INSERT INTO incidents (catchment_id, start_day, end_day, status, acknowledged_by, acknowledged_at, "
                "resolved_by, resolved_at, outcome) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (g[0]["catchment_id"], g[0]["day"], g[-1]["day"], status, ack_by, ack_at, res_by, res_at,
                 "not_checked" if status == "resolved" else None),
            )
            incident_id = cur.fetchone()[0]
            cur.execute("UPDATE alerts SET incident_id = %s WHERE id = ANY(%s)", (incident_id, [a["id"] for a in g]))
        if table_exists("alert_responses"):
            cur.execute(
                "INSERT INTO incident_responses (incident_id, kind, note, author, author_role, created_at) "
                "SELECT a.incident_id, r.kind, r.note, r.author, r.author_role, r.created_at FROM alert_responses r "
                "JOIN alerts a ON a.id = r.alert_id WHERE a.incident_id IS NOT NULL"
            )
            moved = cur.rowcount
            cur.execute("DROP TABLE alert_responses")
            print(f"moved {moved} responses from alerts to incidents")
        for col in OLD_COLUMNS:
            cur.execute(f"ALTER TABLE alerts DROP COLUMN IF EXISTS {col}")
    conn.commit()
finally:
    conn.close()
print(f"grouped {len(alerts)} alerts into {len(groups)} incidents; incidents, notifications and push tables present")
