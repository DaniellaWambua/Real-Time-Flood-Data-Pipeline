"""Tests for ingestion/validation.py, the consumer's reading checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
from validation import check_reading  # noqa: E402

FIELDS = ["rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "era5_rain_mm",
          "soil_1", "soil_2", "temp_c", "dewpoint_depression", "pressure_hpa"]
GOOD = {"date": "2024-04-29", "catchment": "Mathare", "source": "historical-replay",
        "readings": {"rain_mm": 12.5, "imerg_max_rate": 4.1, "imerg_total_mm": 20.3, "imerg_hours_ge5": 1.2,
                     "era5_rain_mm": 9.8, "soil_1": 0.41, "soil_2": 0.39, "temp_c": 19.2,
                     "dewpoint_depression": 3.1, "pressure_hpa": 818.4}}


def with_reading(field, value):
    return {**GOOD, "readings": {**GOOD["readings"], field: value}}


def test_a_valid_reading_passes():
    assert check_reading(GOOD, FIELDS) is None


def test_negative_rainfall_is_rejected():
    assert "negative rainfall" in check_reading(with_reading("rain_mm", -1.0), FIELDS)


def test_soil_moisture_outside_0_to_1_is_rejected():
    assert "outside 0 to 1" in check_reading(with_reading("soil_1", 1.2), FIELDS)
    assert "outside 0 to 1" in check_reading(with_reading("soil_2", -0.1), FIELDS)


def test_missing_or_non_numeric_values_are_rejected():
    assert "missing" in check_reading(with_reading("temp_c", None), FIELDS)
    assert "missing" in check_reading(with_reading("temp_c", float("nan")), FIELDS)
    assert "missing" in check_reading(with_reading("temp_c", "warm"), FIELDS)
    readings = {k: v for k, v in GOOD["readings"].items() if k != "soil_2"}
    assert "missing" in check_reading({**GOOD, "readings": readings}, FIELDS)


def test_a_bad_date_is_rejected():
    assert "date" in check_reading({**GOOD, "date": "29/04/2024"}, FIELDS)