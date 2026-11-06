"""Checks a reading must pass before the consumer saves it."""
import math
from datetime import date

RAIN_FIELDS = ["rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "era5_rain_mm"]
SOIL_FIELDS = ["soil_1", "soil_2"]


def check_reading(message, fields):
    """Return None if the reading is valid, otherwise the reason it is rejected."""
    try:
        date.fromisoformat(message.get("date", ""))
    except (TypeError, ValueError):
        return f"date is not YYYY-MM-DD ({message.get('date')})"
    readings = message.get("readings") or {}
    for f in fields:
        v = readings.get(f)
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
            return f"missing or non-numeric value for {f}"
    for f in RAIN_FIELDS:
        if readings[f] < 0:
            return f"negative rainfall in {f} ({readings[f]})"
    for f in SOIL_FIELDS:
        if not 0 <= readings[f] <= 1:
            return f"soil moisture {f} outside 0 to 1 ({readings[f]})"
    return None