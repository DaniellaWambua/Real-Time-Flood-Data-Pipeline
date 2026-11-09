"""Tests for the live Earth Engine feed (ingestion/earth_engine.py and producer.py --live)."""
import importlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

INGESTION = str(Path(__file__).resolve().parent.parent / "ingestion")
NAMES = ("config", "db", "validation", "earth_engine", "producer")


def _load(module):
    """Import an ingestion module with ingestion's own config and db, not backend's modules of the same name."""
    saved = {n: sys.modules.pop(n) for n in NAMES if n in sys.modules}
    sys.path.insert(0, INGESTION)
    try:
        return importlib.import_module(module)
    finally:
        sys.path.remove(INGESTION)
        for n in NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


producer = _load("producer")
earth_engine = producer.earth_engine

LATEST = {"chirps": date(2026, 9, 30), "imerg": date(2026, 11, 8), "era5": date(2026, 11, 2)}
ROWS = [{"date": "2026-09-30", "catchment": "mathare", "readings": {"rain_mm": 1.0}}]


def _ms(*args):
    return datetime(*args, tzinfo=timezone.utc).timestamp() * 1000


def test_readings_are_converted_as_in_training():
    r = earth_engine.to_reading(
        {"precipitation": -0.2},
        {"total_precipitation_sum": 0.012, "temperature_2m": 293.15, "dewpoint_temperature_2m": 288.15,
         "surface_pressure": 81840.0, "volumetric_soil_water_layer_1": 0.41, "volumetric_soil_water_layer_2": 0.39},
        {"imerg_max_rate": 4.1, "imerg_total_mm": 20.3, "imerg_hours_ge5": 1.5})
    assert r["rain_mm"] == 0.0                        # negative rainfall clipped to 0
    assert r["era5_rain_mm"] == pytest.approx(12.0)   # metres to mm
    assert r["temp_c"] == pytest.approx(20.0)         # kelvin to Celsius
    assert r["dewpoint_depression"] == pytest.approx(5.0)
    assert r["pressure_hpa"] == pytest.approx(818.4)  # pascals to hPa
    assert (r["soil_1"], r["soil_2"], r["imerg_total_mm"]) == (0.41, 0.39, 20.3)
    assert sorted(r) == sorted(producer.config.FEATURE_FIELDS)


def test_a_missing_raw_value_gives_none_for_the_consumer_to_reject():
    r = earth_engine.to_reading({}, {"temperature_2m": 293.15}, {})
    assert r["rain_mm"] is None and r["dewpoint_depression"] is None and r["temp_c"] == pytest.approx(20.0)


def test_an_imerg_day_counts_only_once_its_last_half_hour_exists():
    assert earth_engine.latest_complete_day("imerg", _ms(2026, 11, 8, 23, 30)) == date(2026, 11, 8)
    assert earth_engine.latest_complete_day("imerg", _ms(2026, 11, 9, 10, 0)) == date(2026, 11, 8)
    assert earth_engine.latest_complete_day("era5", _ms(2026, 11, 2)) == date(2026, 11, 2)


def test_the_slowest_dataset_sets_the_last_day():
    assert producer.plan_range(LATEST, date(2026, 9, 20)) == (date(2026, 9, 21), date(2026, 9, 30))


def test_the_first_run_backfills_one_model_window():
    assert producer.plan_range(LATEST, None) == (date(2026, 9, 17), date(2026, 9, 30))


def _run_live(latest=LATEST, last=date(2026, 9, 29), fetch=None):
    with patch.object(earth_engine, "latest_days", return_value=latest) if not callable(latest) else \
            patch.object(earth_engine, "latest_days", side_effect=latest), \
         patch.object(earth_engine, "fetch", side_effect=fetch or (lambda s, e: ROWS)) as fetch_mock, \
         patch.object(producer, "last_live_day", return_value=last), \
         patch.object(producer, "publish", return_value=len(ROWS)) as publish, \
         patch.object(producer, "record_status") as status, \
         patch.object(producer.time, "sleep"):
        code = producer.run_live(interval=0)
    return code, fetch_mock, publish, status


def test_a_live_run_publishes_new_days_and_records_success():
    code, fetch, publish, status = _run_live()
    assert code == 0
    fetch.assert_called_once_with(date(2026, 9, 30), date(2026, 9, 30))
    message = publish.call_args.args[0][0]
    assert message["source"] == "earth-engine" and message["catchment"] == "Mathare"
    ok, detail = status.call_args.args
    assert ok and "published 1 readings" in detail and "CHIRPS 2026-09-30" in detail


def test_nothing_is_fetched_when_already_up_to_date():
    code, fetch, publish, status = _run_live(last=date(2026, 9, 30))
    assert code == 0
    fetch.assert_not_called()
    publish.assert_not_called()
    assert status.call_args.args[0] is True and "up to date" in status.call_args.args[1]


def test_a_failing_source_is_retried_then_recorded_as_disconnected():
    calls = []

    def unreachable():
        calls.append(1)
        raise ConnectionError("Earth Engine unreachable")

    code, fetch, publish, status = _run_live(latest=unreachable)
    assert code == 1 and len(calls) == 3
    publish.assert_not_called()
    ok, detail = status.call_args.args
    assert ok is False and "Earth Engine unreachable" in detail


def test_a_missing_package_fails_at_once_without_retrying():
    calls = []

    def no_module():
        calls.append(1)
        raise ImportError("No module named 'ee'")

    code, _, publish, status = _run_live(latest=no_module)
    assert code == 1 and len(calls) == 1
    assert status.call_args.args[0] is False
