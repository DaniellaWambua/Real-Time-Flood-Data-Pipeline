"""
Turns what Emergency Responders found on the ground into label candidates for the next retraining.

Every resolved incident whose outcome is 'flooding_observed' or 'no_flooding' gives one row per day of the
incident, in the columns data_collection/src/apply_corrections.py reads, so a reviewer can check them and
append the accepted rows to the label corrections file. old_status is filled from the original labelled
table when the day is in it; days after the table ends (new seasons) are listed with old_status blank,
ready for when the table is extended. 'not_checked' outcomes are left out: nobody looked.

Run from the backend/ directory: python export_field_reports.py
Writes data_collection/data/09_label_audit/field_report_candidates.csv
"""
import csv
from datetime import date, timedelta
from pathlib import Path

import db

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data_collection/data/01_flood_labels/processed/daily_labelled_2015_2025.csv"
OUT = ROOT / "data_collection/data/09_label_audit/field_report_candidates.csv"
COLUMNS = ["date", "catchment", "old_status", "new_status", "source_type", "source_name", "source_url",
           "evidence_note", "checker", "date_checked"]

original = {}
if ORIGINAL.exists():
    with open(ORIGINAL, newline="") as f:
        for r in csv.DictReader(f):
            original[(r["catchment"], r["date"][:10])] = r["label_status"]

rows = db.query_all(
    "SELECT i.id, ca.code, i.start_day, i.end_day, i.outcome, i.outcome_places, i.outcome_note, i.resolved_by, "
    "i.resolved_at::date AS resolved_on FROM incidents i JOIN catchment_areas ca ON ca.id = i.catchment_id "
    "WHERE i.status = 'resolved' AND i.outcome IN ('flooding_observed', 'no_flooding') ORDER BY i.start_day, ca.code"
)
out = []
for r in rows:
    new_status = "flood" if r["outcome"] == "flooding_observed" else "no_flood"
    note = f"Field report on incident {r['id']}" + (f"; places: {r['outcome_places']}" if r["outcome_places"] else "") \
        + (f"; {r['outcome_note']}" if r["outcome_note"] else "")
    day = r["start_day"]
    while day <= r["end_day"]:
        key = (r["code"], day.isoformat())
        old = original.get(key, "")
        if old != new_status:  # a day the labels already agree with needs no correction
            out.append({"date": day.isoformat(), "catchment": r["code"], "old_status": old, "new_status": new_status,
                        "source_type": "field_report", "source_name": f"Emergency Responder {r['resolved_by']}",
                        "source_url": f"incident:{r['id']}", "evidence_note": note, "checker": "",
                        "date_checked": (r["resolved_on"] or date.today()).isoformat()})
        day += timedelta(days=1)

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(out)
print(f"{len(rows)} field reports gave {len(out)} candidate label changes, written to {OUT}")
