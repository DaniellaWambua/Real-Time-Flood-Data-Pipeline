"""
Tests for provisional scoring (the fast model without CHIRPS) and its confirmation by the full model:
backend/flood_detection.py detect() and the consumer's handling of provisional readings.
The models and the database are stand-ins.
"""
import datetime
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import flood_detection  # noqa: E402

DAY = datetime.date(2026, 10, 5)
FULL = {"name": "lstm_raw", "version": "v2", "threshold": 0.528}
FAST = {"name": "lstm_fast", "version": "v1", "threshold": 0.663}


def _detect(score, provisional, earlier_alert=None):
    """detect() with stand-ins; earlier_alert is the provisional alert id the full model finds, or None."""
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    answers = [[11]]  # new result id
    if not provisional:
        answers.append([earlier_alert] if earlier_alert else None)
    answers.append([5] if earlier_alert else [22])  # the settled alert's incident, or the new alert id
    cur.fetchone.side_effect = answers
    with patch("flood_detection.build_window", return_value=("window", None)) as window, \
         patch("flood_detection.score_window", return_value=score), \
         patch("flood_detection.load_models", side_effect=lambda kind="full": (FAST if kind == "fast" else FULL, [])), \
         patch("flood_detection.has_model", return_value=True), \
         patch("flood_detection.read_config", side_effect=lambda kind="full": FAST if kind == "fast" else FULL), \
         patch("flood_detection.db.get_connection", return_value=conn), \
         patch("incidents.attach", return_value=(5, True)):
        result = flood_detection.detect(2, DAY, 99, provisional=provisional)
    sql = [(c.args[0], c.args[1]) for c in cur.execute.call_args_list]
    return result, sql, window


def test_a_provisional_reading_is_scored_by_the_fast_model_and_raises_a_provisional_alert():
    result, sql, window = _detect(0.9, provisional=True)
    assert window.call_args.args[2] == "fast"
    assert result["model"] == "lstm_fast v1" and result["threshold"] == 0.663 and result["alert_id"] == 22
    insert = [p for q, p in sql if q.startswith("INSERT INTO alerts")][0]
    assert insert[-1] is True  # provisional


def test_the_full_model_confirms_a_provisional_alert_instead_of_raising_another():
    result, sql, _ = _detect(0.8, provisional=False, earlier_alert=40)
    assert result["settled"] == "confirmed" and result["alert_id"] == 40
    assert not any(q.startswith("INSERT INTO alerts") for q, _ in sql)
    update = [(q, p) for q, p in sql if q.startswith("UPDATE alerts")][0]
    assert "confirmation = 'confirmed'" in update[0] and update[1] == (11, "medium", 40)


def test_a_provisional_alert_the_full_model_does_not_flag_is_marked_not_confirmed():
    result, sql, _ = _detect(0.1, provisional=False, earlier_alert=40)
    assert result["settled"] == "not_confirmed" and not result["flagged"]
    assert any("confirmation = 'not_confirmed'" in q for q, _ in sql)


def test_the_full_model_raises_its_own_alert_when_there_was_no_provisional_one():
    result, sql, _ = _detect(0.9, provisional=False)
    assert result["settled"] is None and result["alert_id"] == 22
    insert = [p for q, p in sql if q.startswith("INSERT INTO alerts")][0]
    assert insert[-1] is False


def test_a_settled_alert_reports_the_settlement_not_a_new_incident():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [[11], [40], [5]]
    with patch("flood_detection.build_window", return_value=("w", None)), \
         patch("flood_detection.score_window", return_value=0.8), \
         patch("flood_detection.load_models", return_value=(FULL, [])), \
         patch("flood_detection.has_model", return_value=True), \
         patch("flood_detection.read_config", return_value=FAST), \
         patch("flood_detection.db.get_connection", return_value=conn), \
         patch("incidents.get", return_value={"id": 5}), \
         patch("notify.incident_to_verify") as new, patch("notify.incident_settled", return_value=1) as settled:
        flood_detection.detect(2, DAY, 99, notify=True)
    new.assert_not_called()
    settled.assert_called_once_with({"id": 5}, "confirmed")


# consumer: provisional readings
INGESTION = str(ROOT / "ingestion")
NAMES = ("config", "db", "validation", "consumer")


def _consumer():
    saved = {n: sys.modules.pop(n) for n in NAMES if n in sys.modules}
    sys.path.insert(0, INGESTION)
    try:
        return importlib.import_module("consumer")
    finally:
        sys.path.remove(INGESTION)
        for n in NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


consumer = _consumer()
READINGS = {"imerg_max_rate": 4.1, "imerg_total_mm": 20.3, "imerg_hours_ge5": 1.2, "era5_rain_mm": 9.8,
            "soil_1": 0.41, "soil_2": 0.39, "temp_c": 19.2, "dewpoint_depression": 3.1, "pressure_hpa": 818.4}


def _handle(message):
    counts = {"saved": 0, "rejected": 0, "skipped": 0, "scored": 0, "flagged": 0}
    with patch.object(consumer, "is_duplicate", return_value=False), \
         patch.object(consumer, "reject") as reject, \
         patch.object(consumer, "save_reading", return_value=99) as save, \
         patch.object(consumer, "request_detection", return_value={"scored": True, "flagged": False}) as detect:
        consumer.handle(message, {"Ngong": 1}, {"earth-engine-provisional": 5, "earth-engine": 4}, counts)
    return counts, reject, save, detect


def test_a_provisional_reading_without_chirps_is_saved_and_sent_to_the_fast_model():
    msg = {"date": "2026-10-05", "catchment": "Ngong", "source": "earth-engine-provisional", "readings": READINGS}
    counts, reject, save, detect = _handle(msg)
    reject.assert_not_called()
    assert counts["saved"] == 1
    assert detect.call_args.kwargs == {"notify": True, "provisional": True}


def test_a_complete_reading_without_chirps_is_still_rejected():
    msg = {"date": "2026-10-05", "catchment": "Ngong", "source": "earth-engine", "readings": READINGS}
    counts, reject, save, _ = _handle(msg)
    save.assert_not_called()
    assert "rain_mm" in reject.call_args.args[1]
