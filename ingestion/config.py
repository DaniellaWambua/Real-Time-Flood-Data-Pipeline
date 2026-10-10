"""Shared configuration for the ingestion and stream processing layer."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

KAFKA_BROKER = os.environ.get("KAFKA_BROKER", "localhost:9092")
TOPIC_RAW_READINGS = "hydro-raw-readings"
CONSUMER_GROUP = "stream-processor"

# The dataset used to simulate a live feed until the real CHIRPS/GloFAS/KMD
# sources are wired in (see producer.py's read_rows()).
SIMULATION_DATA_FILE = PROJECT_ROOT / "data" / "raw" / "Dataset_labels_v7.csv"

FEATURE_FIELDS = [
    "rainfall_mm",
    "river_discharge_m3s",
    "soil_moisture_m3m3",
    "evaporation_mm",
    "oni",
    "rainfall_3day",
    "rainfall_7day",
    "discharge_change",
]

# Preliminary, rule-based risk thresholds evaluated by the stream processor
# (proposal 3.5.6: "evaluate threshold conditions, and trigger preliminary
# alerts"). Deliberately simple and independent of the LSTM model, which
# runs its own, separate anomaly scoring (proposal 3.6.4) on top of the
# records this layer persists.
RAINFALL_ALERT_MM = 50.0
DISCHARGE_CHANGE_ALERT = 1.0
