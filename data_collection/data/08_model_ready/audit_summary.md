# Label audit comparison, 3 November 2026

This compares the frozen D8 models trained and judged on the original labels with the same models trained and judged on the audited labels (D11). The protocol is decisions.md D12. Full numbers are in `audit_dev_results.csv` and `audit_final_results.csv`, with bootstrap intervals in `audit_dev_bootstrap.csv` and `audit_final_bootstrap.csv`. The LSTM seed check is in `audit_lstm_seed_summary.csv` and the seed ensemble in `audit_lstm_ensemble.csv`. The chart is `audit_comparison.png`.

## What changed in the labels
The audit changed 25 days. 18 days became flood and 7 days of three dry Ngong units became unknown, and the 2-day buffer then set 58 further days to unknown. Most corrections fall in 2023 to 2025, so the training years of the development folds barely changed. The 2019 fold is identical under both label sets, because no correction falls in 2015 to 2018.

| Period | Flood days, original | Flood days, audited | Events, original | Events, audited |
|---|---|---|---|---|
| Development folds (2019, 2021-22, 2023) | 53 | 55 | 17 | 20 |
| 2024-2025 | 87 | 96 | 26 | 38 |

13 of the 38 events in 2024 to 2025 are single audited days. Event detection (POD) therefore falls under the audited labels for most models, because more short events are counted, not because the models got worse.

## Reproduction
With the original labels every model reproduces the saved D8 and D9 results. The rule, boosting and lstm_raw match to the third decimal, and lstm_raw matches seed by seed on every fold. Forest and ExtraTrees differ by at most 0.02 in single scores because of floating point differences between machines, which moves pooled AP by at most 0.001.

## Development folds, today target, mean of 3 seeds

| Model | AP original | AP, same model judged on audited labels | AP, trained and judged on audited labels | Precision at 5%, original then audited |
|---|---|---|---|---|
| rule_rain_3d | 0.101 | 0.112 | 0.112 | 0.128 then 0.137 |
| boosting | 0.127 | 0.148 | 0.142 | 0.101 then 0.111 |
| lstm_raw | 0.080 | 0.087 | 0.103 | 0.060 then 0.093 |
| forest | 0.090 | 0.108 | 0.112 | 0.100 then 0.111 |
| extra_trees | 0.112 | 0.122 | 0.124 | 0.114 then 0.125 |

Judging against the audited labels raises AP for every model, by 0.007 (lstm_raw) to 0.021 (boosting). Training on them adds little for the trees. For lstm_raw the 3-seed gain looked large, but with 8 seeds it is 0.008 on average (5 of 8 seeds better, standard deviation 0.017), which is within seed noise.

## 2024-2025, today target, mean of 3 seeds
This period was already seen in D9 and D10, so these numbers are a label sensitivity check, not an unseen test.

| Model | AP original | AP audited (trained and judged) | Precision at 5% | Recall at 5% | F1 at 5% |
|---|---|---|---|---|---|
| rule_rain_3d | 0.253 | 0.341 | 0.327 then 0.422 | 0.391 then 0.448 | 0.356 then 0.434 |
| boosting | 0.189 | 0.241 | 0.202 then 0.255 | 0.241 then 0.271 | 0.220 then 0.263 |
| lstm_raw | 0.446 | 0.530 | 0.410 then 0.507 | 0.490 then 0.538 | 0.447 then 0.522 |
| forest | 0.268 | 0.324 | 0.292 then 0.320 | 0.349 then 0.340 | 0.318 then 0.330 |
| extra_trees | 0.378 | 0.397 | 0.353 then 0.369 | 0.421 then 0.392 | 0.384 then 0.380 |

With 8 seeds the lstm_raw training gain on this period is 0.033 AP on average (6 of 8 seeds better, standard deviation 0.062), judged against the original labels. Averaging the 8 seeds into one score lifts lstm_raw to AP 0.544, precision 0.490 and recall 0.521 at a 5% alarm share on the audited labels, against 0.446, 0.410 and 0.490 for the D9 model. On the development folds the ensemble gain is small (0.098 to 0.106 for audited training).

## What the results show
- **Most of the gain is in measurement.** Judging the same models against corrected labels raises AP and precision for every model in both periods. Part of this is circular, because the audit searched for floods on wet days, so the new flood days favour rain-driven scores. The rule gains most on 2024-2025 (AP 0.253 to 0.341), which fits that explanation.
- **Training on audited labels gives at most a small gain.** The training years changed little, and the LSTM gain is within seed noise in development. The 2024-2025 gain is positive for 6 of 8 seeds but is not settled.
- **Averaging seeds helps the LSTM.** It removes most of the seed-to-seed swing and gives the best numbers in both periods, at no cost in data.
- **The precision target is still far off.** With hindsight thresholds, the best lstm_raw precision at a recall of 0.75 is about 0.25 on 2024-2025, and precision of 0.70 is reached only up to a recall of about 0.39 (`audit_final_operating_points.csv`).

## What the results do not show
- **They are not an unseen test.** 2024-2025 has been seen three times now (D9, D10 and here), and no further model choice should be based on it.
- **They do not cover 2015-2021 groups B and C.** Those years were outside the audit scope (D11), so training labels there are unchanged.

## How to retrain and reproduce
Run from the repo root with `data_collection/.venv` active.

```
python data_collection/src/build_features.py data_collection/data/01_flood_labels/processed/daily_labelled_2015_2025_audited.csv _audited
PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py trees dev
PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py lstm dev
PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py trees final
PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py lstm final
AUDIT_SEEDS=3,4,5,6,7 PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py lstm dev
AUDIT_SEEDS=3,4,5,6,7 PYTHONPATH=data_collection/src python data_collection/src/audit_scores.py lstm final
python data_collection/src/audit_evaluate.py dev
python data_collection/src/audit_evaluate.py final
python data_collection/src/audit_operating_points.py
python data_collection/src/audit_seed_check.py
python data_collection/src/audit_ensemble.py
python data_collection/src/audit_plot.py
```

On a 2-core machine the tree runs took under 2 minutes each and the LSTM runs up to about 25 minutes each. The score files (`audit_*_scores_*.csv`) are working files and are not committed, as with the other score files.
