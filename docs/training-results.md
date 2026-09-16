# LSTM Autoencoder training runs

Branch: feature/train (repo: Real-Time-Flood-Data-Pipeline)

## Setup

Each catchment is trained on its own first (Nairobi River, Mathare, Ngong, Motoine),
the same order used in the earlier Colab work, then a combined model is trained on
all four pooled together. The random seed is fixed for reproducibility. Each model
picks its own anomaly threshold by searching percentiles of normal validation
reconstruction error and keeping the one with the best F1 on validation.

Reconstruction error is scored on the final day of each window only, not averaged
across the full 14 days. Averaging diluted a flood day's signal against the
thirteen ordinary days beside it, which produced a hard cliff in the
precision/recall trade-off (recall 1.0 collapsing straight to 0 with almost no
middle ground). Scoring the final day only produced a genuine gradient instead,
and improved F1 for every model.

## Results (test set, 2024-2025)

| Model | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| Nairobi River | 0.439 | 0.098 | 1.000 | 0.178 |
| Mathare | 0.482 | 0.102 | 1.000 | 0.185 |
| Ngong | 0.280 | 0.075 | 1.000 | 0.139 |
| Motoine | 0.191 | 0.067 | 1.000 | 0.125 |
| Combined | 0.321 | 0.097 | 1.000 | 0.177 |

Every flood window in the test period is still caught (recall 1.000 across all
five models), while precision roughly doubled compared with the whole-window
scoring approach. Validation set size is small (5 to 20 flood windows per
catchment versus 48 in test), so the exact recall figure on test should be read
with that caveat in mind rather than as a guarantee.

## Files produced

`models/lstm_autoencoder_<catchment>.keras` and `models/lstm_autoencoder_combined.keras`,
with matching figures under `reports/figures/training_curve_<name>.png`.
