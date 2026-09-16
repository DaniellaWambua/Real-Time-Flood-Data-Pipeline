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

# Windowing and chronological split
# The dataset runs 2010 to 2025. Splits are by year, not shuffled, so the
# model is never trained on anything that happens after what it is tested on.
WINDOW_LENGTH = 14  # days of history used to judge each day
VAL_START_YEAR = 2022   # 2010-2021 train, 2022-2023 validation, 2024-2025 test
TEST_START_YEAR = 2024

RANDOM_SEED = 42

# Diagram and figure palette
COLOUR_YALE_BLUE = "#0D3B66"
COLOUR_LEMON_CHIFFON = "#FAF0CA"
