"""Shared configuration for the flood pipeline model training code."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

RAW_FEATURES_LABELS_FILE = RAW_DATA_DIR / "Dataset_labels_v4.csv"

# Catchments
CATCHMENTS = ["Nairobi River", "Mathare", "Ngong", "Motoine"]

# Feature columns used by the model
FEATURE_COLUMNS = [
    "rainfall_mm",
    "river_discharge_m3s",
    "rainfall_3day",
    "rainfall_7day",
    "discharge_change",
    "rainfall_anomaly",
]
LABEL_COLUMN = "flood_event"

# Diagram and figure palette
COLOUR_YALE_BLUE = "#0D3B66"
COLOUR_LEMON_CHIFFON = "#FAF0CA"
