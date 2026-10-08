"""Shared configuration for the flood pipeline model training code."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

RAW_FEATURES_LABELS_FILE = RAW_DATA_DIR / "Dataset_labels_v6.csv"  # EM-DAT-corrected flood register

# Catchments
CATCHMENTS = [
    "Nairobi River", "Mathare", "Ngong", "Motoine",
    "Nzoia River", "Nyando River", "Tana River",
]

# Feature columns used by the model
FEATURE_COLUMNS = [
    "rainfall_mm",
    "river_discharge_m3s",
    "rainfall_3day",
    "rainfall_7day",
    "discharge_change",
    # rainfall_anomaly dropped: correlates 1.000 with rainfall_mm, a pure duplicate
]
LABEL_COLUMN = "flood_event"

# Windowing and chronological split (by year, not shuffled)
WINDOW_LENGTH = 14
VAL_START_YEAR = 2023   # 2010-2022 train, 2023 val, 2024-2025 test (narrowed to reduce train-test distance)
TEST_START_YEAR = 2024

RANDOM_SEED = 42

# Diagram and figure palette
COLOUR_YALE_BLUE = "#0D3B66"
COLOUR_LEMON_CHIFFON = "#FAF0CA"

# Model architecture
ENCODER_UNITS = [64, 32]
DECODER_UNITS = [32, 64]
LEARNING_RATE = 1e-3

# Training
EPOCHS = 50
BATCH_SIZE = 64
VALIDATION_SPLIT = 0.1
THRESHOLD_SEARCH_MIN = 80
THRESHOLD_SEARCH_MAX = 99.9
THRESHOLD_SEARCH_STEP = 0.5
