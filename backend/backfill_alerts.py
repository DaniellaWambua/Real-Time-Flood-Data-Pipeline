"""
One-off: raise alerts for flagged scores saved before alert generation existed, each filed under its
incident as a live alert would be. Only the current model's flagged scores with no alert yet are touched,
in date order so neighbouring days join one incident, so it is safe to run again.
Run from the backend/ directory: python backfill_alerts.py
"""
import db
import flood_detection
import incidents

rows = db.query_all(
    "SELECT ar.id, ar.catchment_id, ar.detected_at::date AS day, ar.anomaly_score, ar.threshold_used "
    "FROM anomaly_detection_results ar "
    "WHERE ar.model_name = %s AND ar.is_anomalous "
    "AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.anomaly_detection_result_id = ar.id) "
    "ORDER BY ar.detected_at",
    (flood_detection.current_model_name(),),
)
conn = db.get_connection()
try:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO alerts (anomaly_detection_result_id, catchment_id, severity) VALUES (%s, %s, %s) RETURNING id",
                (r["id"], r["catchment_id"], flood_detection.severity_for(r["anomaly_score"], r["threshold_used"])),
            )
            incidents.attach(cur, cur.fetchone()[0], r["catchment_id"], r["day"])
    conn.commit()
finally:
    conn.close()
print(f"raised {len(rows)} alerts")
