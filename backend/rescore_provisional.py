"""
Scores the stored provisional readings (no CHIRPS yet) with the model now in models/flood_lstm_fast/, after a new
provisional version is saved. Only days the full model has not scored and the current provisional version has not
scored are touched, through flood_detection.detect(provisional=True), so they get the same alerts a live provisional
reading would. Run from the backend/ directory: python rescore_provisional.py
"""
import db
import flood_detection

model = flood_detection.current_model_name("fast")
full = flood_detection.current_model_name("full")
todo = db.query_all(
    "SELECT h.catchment_id, h.recorded_at::date AS day, MAX(h.id) AS record_id FROM hydro_data_records h "
    "JOIN catchment_areas ca ON ca.id = h.catchment_id AND ca.is_active "
    "WHERE h.rainfall_mm IS NULL AND h.era5_rain_mm IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM anomaly_detection_results ar WHERE ar.catchment_id = h.catchment_id "
    "AND ar.detected_at::date = h.recorded_at::date AND ar.model_name IN (%s, %s)) "
    "GROUP BY h.catchment_id, h.recorded_at::date ORDER BY day, h.catchment_id",
    (model, full),
)
print(f"{model}: {len(todo)} provisional catchment-days to score")
scored = flagged = 0
for r in todo:
    result = flood_detection.detect(r["catchment_id"], r["day"], r["record_id"], provisional=True)
    scored += result["scored"]
    flagged += result.get("flagged", 0)
print(f"scored {scored}, flagged {flagged}")
