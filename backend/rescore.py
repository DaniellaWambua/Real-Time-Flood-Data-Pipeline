"""
Scores the stored readings with the model now in models/flood_lstm/ (run after a new version is saved).
Every catchment-day already in hydro_data_records that the current version has not scored is scored once,
through flood_detection.detect, so it gets the same alerts a live reading would. Scores from older versions
stay in anomaly_detection_results; the dashboard only shows the current version's.
Safe to run again: days the current version already scored are skipped.
Run from the backend/ directory: python rescore.py [first_day last_day], e.g. python rescore.py 2024-01-01 2025-12-31
"""
import datetime
import sys

import db
import flood_detection

model = flood_detection.current_model_name()
first, last = (datetime.date.fromisoformat(d) for d in sys.argv[1:3]) if len(sys.argv) > 2 else (None, None)
sql = (
    "SELECT h.catchment_id, h.recorded_at::date AS day, MAX(h.id) AS record_id FROM hydro_data_records h "
    "JOIN catchment_areas ca ON ca.id = h.catchment_id AND ca.is_active "
    "WHERE h.rainfall_mm IS NOT NULL "  # provisional readings wait for CHIRPS before the full model scores them
    "AND NOT EXISTS (SELECT 1 FROM anomaly_detection_results ar WHERE ar.catchment_id = h.catchment_id "
    "AND ar.detected_at::date = h.recorded_at::date AND ar.model_name = %s) "
)
params = [model]
if first:
    sql += "AND h.recorded_at::date BETWEEN %s AND %s "
    params += [first, last]
sql += "GROUP BY h.catchment_id, h.recorded_at::date ORDER BY day, h.catchment_id"
todo = db.query_all(sql, tuple(params))
print(f"{model}: {len(todo)} catchment-days to score")
scored = flagged = skipped = 0
for i, r in enumerate(todo, 1):
    result = flood_detection.detect(r["catchment_id"], r["day"], r["record_id"])
    if result["scored"]:
        scored += 1
        flagged += result["flagged"]
    else:
        skipped += 1
    if i % 250 == 0:
        print(f"  {i}/{len(todo)}", flush=True)
print(f"scored {scored}, flagged {flagged}, not scorable {skipped} (fewer than 14 consecutive days of readings)")
