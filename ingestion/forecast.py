"""
Daily rainfall forecasts from the Open-Meteo Forecast API, one point per catchment.

The forecast is a separate, rule-based warning: it is not given to the LSTM, which
was trained on CHIRPS, IMERG and ERA5-Land and would not read forecast values correctly.
"""
import json
import urllib.parse
import urllib.request

import config


def build_url(points):
    """The request for every catchment's point at once; points are (longitude, latitude)."""
    query = {
        "latitude": ",".join(f"{lat:.4f}" for _, lat in points),
        "longitude": ",".join(f"{lon:.4f}" for lon, _ in points),
        "daily": "precipitation_sum",
        "timezone": "Africa/Nairobi",
        "forecast_days": config.FORECAST_DAYS,
    }
    return f"{config.OPEN_METEO_URL}?{urllib.parse.urlencode(query)}"


def to_messages(response, catchments, issued_at):
    """One message per catchment from Open-Meteo's reply, in the order catchments were asked for.
    catchments is a list of (name, longitude, latitude)."""
    locations = response if isinstance(response, list) else [response]
    if len(locations) != len(catchments):
        raise ValueError(f"asked for {len(catchments)} locations, Open-Meteo returned {len(locations)}")
    messages = []
    for (name, _, _), loc in zip(catchments, locations):
        daily = loc["daily"]
        messages.append({
            "catchment": name,
            "source": config.FORECAST_SOURCE,
            "issued_at": issued_at,
            "days": [{"date": d, "precipitation_mm": mm}
                     for d, mm in zip(daily["time"], daily["precipitation_sum"])],
        })
    return messages


def fetch(catchments, issued_at):
    """Forecast messages for (name, longitude, latitude) catchments."""
    url = build_url([(lon, lat) for _, lon, lat in catchments])
    with urllib.request.urlopen(url, timeout=30) as resp:
        return to_messages(json.loads(resp.read()), catchments, issued_at)
