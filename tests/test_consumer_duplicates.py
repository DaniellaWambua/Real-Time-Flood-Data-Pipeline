"""Tests for the consumer's duplicate check (ingestion/consumer.py handle and is_duplicate)."""
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

INGESTION = str(Path(__file__).resolve().parent.parent / "ingestion")


def _load_consumer():
    """Import consumer.py with ingestion's own config and db, not backend's modules of the same name."""
    saved = {name: sys.modules.pop(name) for name in ("config", "db", "validation", "consumer") if name in sys.modules}
    sys.path.insert(0, INGESTION)
    try:
        return importlib.import_module("consumer")
    finally:
        sys.path.remove(INGESTION)
        for name in ("config", "db", "validation", "consumer"):
            sys.modules.pop(name, None)
        sys.modules.update(saved)


consumer = _load_consumer()

MESSAGE = {"date": "2024-04-29", "catchment": "Mathare", "source": "historical-replay",
           "readings": {"rain_mm": 12.5, "imerg_max_rate": 4.1, "imerg_total_mm": 20.3, "imerg_hours_ge5": 1.2,
                        "era5_rain_mm": 9.8, "soil_1": 0.41, "soil_2": 0.39, "temp_c": 19.2,
                        "dewpoint_depression": 3.1, "pressure_hpa": 818.4}}
CATCHMENTS = {"Mathare": 2}


def _counts():
    return {"saved": 0, "rejected": 0, "skipped": 0, "scored": 0, "flagged": 0}


def _handle(duplicate):
    counts = _counts()
    with patch.object(consumer, "is_duplicate", return_value=duplicate) as is_dup, \
         patch.object(consumer, "reject") as reject, \
         patch.object(consumer, "save_reading", return_value=99) as save, \
         patch.object(consumer, "request_detection", return_value={"scored": False, "reason": ""}):
        consumer.handle(MESSAGE, CATCHMENTS, {"historical-replay": 1}, counts)
    return counts, is_dup, reject, save


def test_a_duplicate_reading_is_rejected_logged_and_not_saved():
    counts, _, reject, save = _handle(duplicate=True)
    save.assert_not_called()
    reject.assert_called_once()
    assert "already stored" in reject.call_args.args[1]
    assert counts["rejected"] == 1 and counts["saved"] == 0


def test_a_new_reading_is_saved():
    counts, _, reject, save = _handle(duplicate=False)
    reject.assert_not_called()
    save.assert_called_once()
    assert counts["saved"] == 1 and counts["rejected"] == 0


def test_the_duplicate_check_uses_source_catchment_and_date():
    _, is_dup, _, _ = _handle(duplicate=False)
    is_dup.assert_called_once_with(1, 2, "2024-04-29")


def test_is_duplicate_queries_by_source_catchment_and_date():
    with patch.object(consumer.db, "query_one", return_value={"?column?": 1}) as query:
        assert consumer.is_duplicate(1, 2, "2024-04-29") is True
    sql, params = query.call_args.args
    assert "data_source_id" in sql and "catchment_id" in sql and "recorded_at" in sql
    assert params == (1, 2, "2024-04-29")
    with patch.object(consumer.db, "query_one", return_value=None):
        assert consumer.is_duplicate(1, 2, "2024-04-29") is False
