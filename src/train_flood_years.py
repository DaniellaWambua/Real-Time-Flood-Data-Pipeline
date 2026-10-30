"""Autoencoder variant: train only on normal days drawn from each
catchment's own flood-active years, instead of the full 2010-2022 span.

Dr Owuor's feedback was to balance flood vs normal day counts. That
specific operation has no meaning for the autoencoder, since it never
trains on flood days at all by design, it only ever learns what
"normal" looks like, then flags departures from it. This script is the
autoencoder-side translation of that feedback: restrict what "normal"
is learned from to years already known to be flood-active for that
catchment, rather than diluting it with quiet years that may not
represent the wetter conditions 2024-2025 actually looks like. See
src/balanced_lstm_classifier.py for the other half, a supervised
classifier trained on a genuinely 1:1 balanced set.

Test stays fixed at 2024-2025, untouched and at its real, imbalanced
composition, exactly as every other evaluation in this project.
Validation is 2023 for every catchment, a flood-active year for all
six. Training years are each catchment's own other flood-active years
below, read directly off a per-catchment, per-year count of
Dataset_labels_v9.csv's confirmed events.

Run with: python -m src.train_flood_years
"""

from __future__ import annotations

from sklearn.preprocessing import StandardScaler

from src.alternative_splits import _windows_allowing_gaps
from src.data_loading import load_raw_data
from src.walk_forward_validation import set_seeds, train_one

TEST_START_YEAR = 2024
TEST_END_YEAR = 2025
VAL_YEAR = 2023

# Each catchment's own flood-active years, excluding the shared
# validation year (2023) and the fixed test years (2024-2025).
FLOOD_YEARS = {
    "Nairobi River": [2012, 2013, 2015, 2018, 2020],
    "Mathare": [2012, 2013, 2015, 2018, 2020],
    "Ngong": [2013, 2015, 2018, 2020],
    "Motoine": [2013, 2015, 2016, 2018, 2020],
    "Nyando River": [2010, 2015, 2016],
    "Tana River": [2015, 2016, 2021],
}


def split_for(catchment_df, train_years):
    X_train_raw, y_train_raw = _windows_allowing_gaps(catchment_df, train_years)
    X_val, y_val = _windows_allowing_gaps(catchment_df, [VAL_YEAR])
    X_test, y_test = _windows_allowing_gaps(catchment_df, list(range(TEST_START_YEAR, TEST_END_YEAR + 1)))

    X_train_raw = X_train_raw[y_train_raw == 0]

    n_features = X_train_raw.shape[-1]
    scaler = StandardScaler().fit(X_train_raw.reshape(-1, n_features))

    def scale(X):
        n, w, f = X.shape
        return scaler.transform(X.reshape(-1, f)).reshape(n, w, f)

    return scale(X_train_raw), scale(X_val), y_val, scale(X_test), y_test


def main():
    set_seeds()
    df = load_raw_data()
    results = []
    for catchment, train_years in FLOOD_YEARS.items():
        catchment_df = df[df["catchment"] == catchment].sort_values("date")
        X_train, X_val, y_val, X_test, y_test = split_for(catchment_df, train_years)
        if len(X_train) == 0 or len(X_val) == 0 or y_val.sum() == 0:
            print(f"{catchment}: skipped, empty split or no validation positives")
            continue
        drift_ratio, precision, recall, f1, n_val_pos, n_test_pos = train_one(
            catchment, X_train, X_val, y_val, X_test, y_test
        )
        print(
            f"{catchment:<15} train_days={len(X_train):<6} val_pos={n_val_pos:<3} "
            f"test_pos={n_test_pos:<4} drift={drift_ratio:.2f} "
            f"precision={precision:.3f} recall={recall:.3f} f1={f1:.3f}"
        )
        results.append(
            {"catchment": catchment, "precision": precision, "recall": recall, "f1": f1, "test_pos": n_test_pos}
        )

    if results:
        pooled_tp = sum(r["recall"] * r["test_pos"] for r in results)
        pooled_pos = sum(r["test_pos"] for r in results)
        pooled_recall = pooled_tp / pooled_pos if pooled_pos else 0.0
        mean_f1 = sum(r["f1"] for r in results) / len(results)
        print(f"\nAcross {len(results)} catchments: mean F1={mean_f1:.3f}, pooled recall={pooled_recall:.3f}")


if __name__ == "__main__":
    main()
