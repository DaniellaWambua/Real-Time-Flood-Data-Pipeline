"""Shared configuration for the flood pipeline model training code."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
FIGURES_DIR = PROJECT_ROOT / "reports" / "figures"

RAW_FEATURES_LABELS_FILE = RAW_DATA_DIR / "Dataset_labels_v9.csv"  # v8 + newly-sourced register events (master catalogue + DesInventar), same features as v8

# Catchments
# Nzoia River is deliberately excluded: it has 0 validation-period flood
# events under this split in every configuration tried, so no catchment-
# specific threshold could ever be tuned for it, and its only non-zero
# result anywhere in the investigation (precision 0.039, recall 0.400,
# under the all-three ERA5 feature set) rode entirely on a pooled
# threshold borrowed from Nyando River rather than genuine model
# confidence (see training-results.md, Phase 9/10). Scoped out as a
# limitation (insufficient verified flood events in the validation
# window), not dropped from the raw dataset, so it can be reinstated if
# more flood events are sourced for it later.
CATCHMENTS = [
    "Nairobi River", "Mathare", "Ngong", "Motoine",
    "Nyando River", "Tana River",
]

# Feature columns used by the model: 5 rainfall/discharge features plus
# 3 ERA5-Land/climate features (soil moisture, evaporation, ONI). This is
# the final set, decided after testing each new feature alone and all
# together (see training-results.md, Phase 9/10 for the full reasoning).
# rainfall_anomaly was tried and dropped: it correlates 1.000 with
# rainfall_mm, so it added nothing.
FEATURE_COLUMNS = [
    "rainfall_mm",
    "river_discharge_m3s",
    "rainfall_3day",
    "rainfall_7day",
    "discharge_change",
    "soil_moisture_m3m3",
    "evaporation_mm",
    "oni",
]
LABEL_COLUMN = "flood_event"

# Dataset switch. v9 (above) is the default: same six catchments and
# feature set as v8, with 22 additional flood-register events sourced
# from the master catalogue and DesInventar (see flood-folder-assessment.md
# and training-results.md). Setting FLOOD_DATASET=v8 trains on the prior
# register instead, for direct before/after comparison. Setting
# FLOOD_DATASET=v6 trains on the earlier v6 file: no ERA5-Land/ONI
# features, but with Nzoia River back in. Nzoia was dropped because the
# single 2023 validation year has no Nzoia floods; src/model_selection.py
# validates on 2015-2023 in four blocks, which do include Nzoia's
# 2013/2015 floods.
DATASET = os.environ.get("FLOOD_DATASET", "v9")
if DATASET == "v6":
    RAW_FEATURES_LABELS_FILE = RAW_DATA_DIR / "Dataset_labels_v6.csv"
    CATCHMENTS = CATCHMENTS + ["Nzoia River"]
    FEATURE_COLUMNS = [c for c in FEATURE_COLUMNS
                       if c not in ("soil_moisture_m3m3", "evaporation_mm", "oni")]
elif DATASET == "v8":
    RAW_FEATURES_LABELS_FILE = RAW_DATA_DIR / "Dataset_labels_v8.csv"
elif DATASET != "v9":
    raise ValueError(f"FLOOD_DATASET must be v6, v8, or v9, not {DATASET!r}")

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

# Added 2026-10-27 (Phase 12 finalisation): dropout for the autoencoder's
# LSTM layers, the first change tested that targets the documented
# validation-to-test drift problem directly rather than recalibrating
# the threshold after training.
AUTOENCODER_DROPOUT = 0.1

# Added 2026-10-27 (Phase 12 finalisation): dropout for the autoencoder's
# LSTM layers, the first change tested that targets the documented
# validation-to-test drift problem directly rather than recalibrating
# the threshold after training.
AUTOENCODER_DROPOUT = 0.1
