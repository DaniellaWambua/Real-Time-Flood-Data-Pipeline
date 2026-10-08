"""One-off diagnostic: does each catchment's model actually produce higher
reconstruction error on flood days than on ordinary days in validation?

Every threshold scheme tried so far (pooled raw, pooled normalised,
independent) has produced the same degenerate pattern for Nairobi River,
Mathare, Ngong and Motoine: recall near 1.0, precision near 0.03-0.06,
meaning almost every day gets flagged regardless of label. That pattern
shows up even running each catchment's own choose_threshold on its own
validation set with no pooling involved at all, which rules out pooling
as the cause. This checks the more basic question directly: in
validation, is the reconstruction error on flood days actually any
higher than on ordinary days for these catchments, or has the retrained
model lost the separation needed for anomaly scoring to work at all.
"""

from __future__ import annotations

import numpy as np
from tensorflow import keras

from src.config import CATCHMENTS, MODELS_DIR
from src.data_loading import load_raw_data
from src.preprocessing import build_all_splits
from src.scoring import reconstruction_error, slugify


def main():
    df = load_raw_data()
    splits = build_all_splits(df)
    models = {
        name: keras.models.load_model(MODELS_DIR / f"lstm_autoencoder_{slugify(name)}.keras")
        for name in CATCHMENTS
    }

    print(f"{'catchment':<18}{'normal median':>15}{'flood median':>14}{'normal p90':>12}{'flood p10':>11}{'flood>normal?':>15}")
    for name in CATCHMENTS:
        split = splits[name]
        model = models[name]
        errs_val = reconstruction_error(model, split.X_val)
        y_val = split.y_val
        normal = errs_val[y_val == 0]
        flood = errs_val[y_val == 1]
        if len(flood) == 0:
            print(f"{name:<18}{'no flood days in validation':>60}")
            continue
        normal_median = np.median(normal)
        flood_median = np.median(flood)
        normal_p90 = np.percentile(normal, 90)
        flood_p10 = np.percentile(flood, 10)
        separated = "yes" if flood_median > normal_median else "NO"
        print(
            f"{name:<18}{normal_median:>15.5f}{flood_median:>14.5f}"
            f"{normal_p90:>12.5f}{flood_p10:>11.5f}{separated:>15}"
        )


if __name__ == "__main__":
    main()
