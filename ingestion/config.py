"""Shared configuration for the ingestion and stream processing layer."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# One secrets file for the whole system, shared with the backend
load_dotenv(PROJECT_ROOT / "backend" / ".env")


def _required(name):
    """A secret with no default: refuse to start when it is missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; add it to backend/.env (see backend/.env.example)")
    return value


KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:9092")
TOPIC_RAW_READINGS = "hydro-raw-readings"
TOPIC_FORECASTS = "hydro-forecasts"
CONSUMER_GROUP = "stream-processor"

# Read from backend/.env or the environment; never commit real credentials here.
# (Deliberately duplicated from backend/config.py rather than imported
# from it: both this file and that one are named config.py, and having
# ingestion/ reach into backend/'s sys.path caused the two to shadow each
# other. Keeping ingestion/ self-contained avoids that entirely.)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "flood_pipeline")
DB_USER = os.environ.get("DB_USER", "flood_pipeline")
DB_PASSWORD = _required("DB_PASSWORD")

# Historical daily readings replayed through Kafka until the live Earth Engine feed is wired in
SIMULATION_DATA_FILE = PROJECT_ROOT / "data_collection" / "data" / "08_model_ready" / "features_daily_audited.csv"
REPLAY_SOURCE = "historical-replay"
# catchment code in the features file -> catchment name in the database
CATCHMENT_NAMES = {"nairobi": "Nairobi River", "mathare": "Mathare", "ngong": "Ngong"}

FEATURE_FIELDS = [
    "rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "era5_rain_mm",
    "soil_1", "soil_2", "temp_c", "dewpoint_depression", "pressure_hpa",
]

# Live feed from Google Earth Engine (producer.py --live)
EE_PROJECT = os.environ.get("EE_PROJECT", "flood-pipeline-nairobi")
CATCHMENTS_FILE = PROJECT_ROOT / "data_collection" / "data" / "05_spatial" / "processed" / "catchments.geojson"
LIVE_SOURCE = "earth-engine"
LIVE_DATASETS = "CHIRPS, IMERG, ERA5-Land"
WINDOW_DAYS = 14  # the model's input length, backfilled on the first live run
# Days IMERG and ERA5-Land have published but CHIRPS has not: sent without rain_mm, scored by the fast model
PROVISIONAL_SOURCE = "earth-engine-provisional"
PROVISIONAL_DATASETS = "IMERG, ERA5-Land (CHIRPS pending)"
PROVISIONAL_FIELDS = [f for f in FEATURE_FIELDS if f != "rain_mm"]

# Rainfall warning from Open-Meteo forecasts (producer.py --forecast)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_SOURCE = "open-meteo"
FORECAST_DATASETS = "Open-Meteo daily rainfall forecast"
FORECAST_DAYS = 3
# KMD's flat 24-hour heavy-rainfall warning level (Kiptum et al., 2023)
RAIN_WARNING_MM = 50.0

# The backend's flood detection endpoint, called after each reading is saved
DETECTION_URL = os.environ.get("DETECTION_URL", "http://localhost:5001/internal/detect")
# where the consumer asks the backend to email a new rainfall warning
WARNING_NOTIFY_URL = os.environ.get("WARNING_NOTIFY_URL", DETECTION_URL.rsplit("/", 1)[0] + "/notify-warning")
INTERNAL_API_TOKEN = _required("INTERNAL_API_TOKEN")