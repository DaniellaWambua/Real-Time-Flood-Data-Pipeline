"""Shared configuration for the ingestion and stream processing layer."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:9092")
TOPIC_RAW_READINGS = "hydro-raw-readings"
CONSUMER_GROUP = "stream-processor"

# Matches db/docker-compose.yml's defaults; override with real values in
# production via environment variables, never commit real credentials here.
# (Deliberately duplicated from backend/config.py rather than imported
# from it: both this file and that one are named config.py, and having
# ingestion/ reach into backend/'s sys.path caused the two to shadow each
# other. Keeping ingestion/ self-contained avoids that entirely.)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "flood_pipeline")
DB_USER = os.environ.get("DB_USER", "flood_pipeline")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "flood_pipeline_dev")

# Historical daily readings replayed through Kafka until the live Earth Engine feed is wired in
SIMULATION_DATA_FILE = PROJECT_ROOT / "data_collection" / "data" / "08_model_ready" / "features_daily_audited.csv"
REPLAY_SOURCE = "historical-replay"
# catchment code in the features file -> catchment name in the database
CATCHMENT_NAMES = {"nairobi": "Nairobi River", "mathare": "Mathare", "ngong": "Ngong"}

FEATURE_FIELDS = [
    "rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "era5_rain_mm",
    "soil_1", "soil_2", "temp_c", "dewpoint_depression", "pressure_hpa",
]

# The backend's flood detection endpoint, called after each reading is saved
DETECTION_URL = os.environ.get("DETECTION_URL", "http://localhost:5001/internal/detect")
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "dev-internal-token-change-before-deploying")