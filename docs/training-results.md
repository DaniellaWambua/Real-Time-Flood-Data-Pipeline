# LSTM Autoencoder training runs

Branch: feature/train (repo: Real-Time-Flood-Data-Pipeline)

## Setup

Each catchment is trained on its own first (Nairobi River, Mathare, Ngong, Motoine),
the same order used in the earlier Colab work, then a combined model is trained on
all four pooled together. Each model picks its own anomaly threshold by searching
percentiles of normal validation reconstruction error and keeping the one with the
best F1 on validation, rather than a fixed percentile, so precision and recall are
balanced rather than recall being favoured by default.

## Results

Pending the next run of `python3 -m src.train`. Results (threshold, precision,
recall, F1 per model) will be recorded here once available.

## Files produced

`models/lstm_autoencoder_<catchment>.keras` and `models/lstm_autoencoder_combined.keras`,
with matching figures under `reports/figures/training_curve_<name>.png`.
