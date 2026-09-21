"""Checks whether requiring multiple catchments to agree on the same date
improves precision without losing real flood events.

Every flood-labelled date in the dataset hits all four catchments at once
(confirmed by inspection: 220 flood rows fall on exactly 55 dates, each
with all four catchments flagged). A single catchment's model raising an
alarm on its own could just be that catchment having an unusual but
harmless day. Requiring two or more catchments to agree on the same date
should filter out that isolated noise, since a real flood is corroborated
everywhere by definition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score
from tensorflow.keras.models import load_model

from src.config import CATCHMENTS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits
from src.scoring import choose_threshold, reconstruction_error, slugify


def per_catchment_flags(splits):
    """For each catchment: its own threshold, and test-day flags by date."""
    flags_by_catchment = {}
    dates = None
    y_true = None

    for name, split in splits.items():
        model = load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")

        val_errors = reconstruction_error(model, split.X_val)
        threshold = choose_threshold(val_errors, split.y_val)

        test_errors = reconstruction_error(model, split.X_test)
        flagged = test_errors > threshold

        flags_by_catchment[name] = pd.Series(flagged, index=split.dates_test)

        # dates and true labels are identical across catchments (checked
        # separately); take them from whichever catchment comes first
        if dates is None:
            dates = split.dates_test
            y_true = pd.Series(split.y_test, index=split.dates_test)

    flags_df = pd.DataFrame(flags_by_catchment)
    return flags_df, y_true


def evaluate_agreement_levels(flags_df, y_true):
    agreement_count = flags_df.sum(axis=1)

    print(f"{'agree >=':<10}{'flagged days':>14}{'precision':>12}{'recall':>10}{'f1':>8}")
    for k in range(1, len(CATCHMENTS) + 1):
        y_pred = (agreement_count >= k).astype(int)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        print(f"{k:<10}{int(y_pred.sum()):>14}{precision:>12.3f}{recall:>10.3f}{f1:>8.3f}")


def main():
    df = load_raw_data()
    splits = build_all_splits(df)
    flags_df, y_true = per_catchment_flags(splits)
    evaluate_agreement_levels(flags_df, y_true)


if __name__ == "__main__":
    main()
