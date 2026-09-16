# First LSTM Autoencoder training run

Date: 2026-09-16
Branch: feature/train

## Setup

Model trained on 17328 normal (non-flood) windows pooled across all four
catchments, 14-day windows, early stopping on a validation split within
the training period. Anomaly threshold set at the 99th percentile of
reconstruction error on normal windows in the 2022-2023 validation set.

## Test set result (2024-2025, 2872 windows, 48 flood)

| Metric | Value |
|---|---|
| Threshold | 0.898 |
| Precision | 0.216 |
| Recall | 1.000 |
| F1 | 0.356 |

## Reading the numbers

Recall of 1.000 means every flood window in the test period was flagged,
which is the priority for an early warning system since a missed flood is
far more costly than a false alarm. Precision of 0.216 looks low but
follows from how rare flood windows are in the data (48 out of 2872, 1.7
percent), rather than a high false alarm rate as such: roughly 174 of the
2824 normal test windows were flagged, about 6 percent of them. Tightening
the threshold (raising the percentile) would trade some recall for higher
precision, worth trying once there is time to compare thresholds properly.

## Files produced

- `models/lstm_autoencoder.keras`
- `reports/figures/training_curve.png`
