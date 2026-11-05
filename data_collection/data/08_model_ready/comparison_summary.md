# Model comparison, 3 November 2026

Full numbers are in `comparison_results.csv`. The test split by catchment and year is in `comparison_final_breakdown.csv`, and the fixed-threshold rule check is in `rule_fixed_threshold_results.csv`. Plots are `comparison_pr_dev.png`, `comparison_pr_final.png`, `comparison_events_dev.png` and `comparison_events_final.png`. The protocol is decisions.md D8, and D9 records the final test.

## Data limits that bound every result
- There are 194 flood days in 57 events, across three catchments over 2015 to 2025, with 2017 and 2020 unusable (D6).
- The development folds hold 13, 11 and 29 flood days, which is 4, 6 and 7 events, or 17 events pooled. One event more or fewer moves a fold's event recall by 14 to 25 points.
- The test years 2024 to 2025 hold 87 flood days in 26 events. The base rate is 0.042, against 0.012 in development, so average precision (AP) is only comparable across periods as lift over base rate.
- Labels come from news reports (Groundsource) and EM-DAT. A missed report counts as a no_flood day.
- Intervals are 95 percent block bootstraps over catchment-months. Most of them are wide.

## Development folds against final test (today target, mean of 3 seeds)

| Model | Role | Dev AP (lift) | Dev event recall at 5% | Test AP (lift) [95% CI] | Test event recall at 5% [95% CI] |
|---|---|---|---|---|---|
| rule_rain_3d | primary | 0.101 (8.2) | 0.59 | 0.253 (6.0) [0.15, 0.37] | 0.62 [0.40, 0.79] |
| boosting | primary | 0.127 (10.4) | 0.53 | 0.189 (4.5) [0.12, 0.28] | 0.58 [0.38, 0.78] |
| lstm_raw | primary | 0.080 (6.5) | 0.27 | 0.446 (10.6) [0.27, 0.61] | 0.55 [0.31, 0.74] |
| forest | secondary | 0.090 (7.3) | 0.63 | 0.268 (6.4) | 0.62 |
| extra_trees | secondary | 0.111 (9.1) | 0.53 | 0.378 (9.0) | 0.67 |
| lstm_log | secondary | 0.067 (5.4) | 0.27 | 0.457 (10.9) | 0.58 |
| lstm_batches | secondary | 0.050 (4.1) | 0.24 | 0.402 (9.5) | 0.51 |

Dev AP is pooled over the three folds. The tomorrow target gives the same pattern, and its test AP for lstm_raw is 0.491 (lift 11.6). At a 5% alarm share all models give 10 to 14 false alarm days per catchment-year on the test, against 16 to 17 in development. This number is mostly fixed by the alarm share itself.

**The ranking is not the same in development and test.** In development, boosting and ExtraTrees led on AP and all three LSTM variants came last. On the test, the three LSTM variants lead on AP and boosting comes last. On event recall the rule sits near the top in both periods.

## Primary comparisons
- **Boosting against the rule.** There is no evidence that boosting is better. The AP difference interval includes zero in development (today −0.04 to 0.09) and on the test (−0.17 to 0.05). Event recall at 5% is lower in both periods (0.53 against 0.59, then 0.58 against 0.62).
- **lstm_raw against the rule.** In development there is no AP difference (−0.08 to 0.08), and event recall is clearly lower (0.27 against 0.59). On the test, AP is higher, with intervals of 0.06 to 0.33 for today and 0.13 to 0.36 for tomorrow. The point estimate is higher in all three catchments and in both test years. Event recall at 5% is not higher (0.55 against 0.62, with intervals that overlap almost completely).

## What the results show
- **Every model ranks flood days above chance in every period.** AP lift is 3 to 12 over the base rate. The one exception is development lstm_batches on the tomorrow target, whose interval reaches down to chance.
- **The 3-day rainfall rule is a strong baseline.** No machine-learning model beats it on event recall in either period.
- **On the test, the LSTM ranks flood days better than the rule, but it does not detect more events.** Its AP gain comes from scoring more days inside each event highly. Detecting more separate events is a different thing.
- **LSTM results swing heavily with the seed and the fold.** For today/raw on the 2021–22 fold, the seeds give AP 0.12, 0.04 and 0.02. Development results did not predict test results.
- **All models do about equally well on today and tomorrow.** Rainfall up to today carries most of the signal for tomorrow too.
- **A fixed rule threshold does not hold its alarm rate.** The threshold is 43.7 mm in 3 days, the 95th percentile of 2015–2023. In the wetter 2024–2025 period it alarms on 8.8% of days and detects 20 of 26 events (0.77). The cost is 22 false alarm days per catchment-year, against 12 at a 5% alarm share.

## What the results do not show
- **They do not show that the LSTM is the better model in general.** Its test advantage rests on one two-year period with 26 events, and development pointed the other way. A plausible but untested explanation is that the final model had more flood days to learn from (107, against 54, 67 and 78 in the development folds), and that 2024 had long, multi-day events that favour a sequence model.
- **They do not show that any model meets the proposal's acceptance level (F1 at least 0.70, recall at least 0.75).** Day-level F1 is at most 0.50 even with the threshold chosen in hindsight. Event recall reaches 0.75 only at a 10% alarm share, with about 25 false alarm days per catchment-year.
- **They do not cover real-time operation, Kafka ingestion, river discharge inputs or an LSTM autoencoder.** None of these was part of this analysis.

## Reproducibility
- The local LSTM weights runs (raw and log) match the saved Colab files to three decimals.
- The batches mode does not match Colab. Local reruns of the original train_lstm.py and of lstm_common.py agree with each other (today 0.257, 0.055, 0.018) but not with the Colab file (0.234, 0.047, 0.027). The likely cause is that Colab runs `train_on_batch` differently from this machine.
- Boosting reproduces baselines_balanced.py, and the event scoring reproduces event_eval.py exactly.

## Tuning run (D10, a second look at 2024 to 2025)
Hyperparameters were searched on the development folds after the final test (`tuning/`). The 2024 to 2025 period had already been seen, so these test numbers are not an unseen test. The D9 results above stay the primary results. Full numbers are in `tuned_comparison_results.csv`, `tuned_fixed_threshold_results.csv` and `tuned_vs_frozen.csv`.

- **Selected settings.** Forest, ExtraTrees, lstm_raw and lstm_log have a setting at least as good as the frozen one on all six development numbers. Boosting and lstm_batches do not, so the best mean rank was taken. For boosting that means tomorrow event recall goes from 0.47 to 0.65 while today AP drops from 0.197 to 0.185. For lstm_batches, tomorrow AP drops from 0.093 to 0.089. No single feature beats rain_sum_3d on all six numbers, so rule_tuned is the same as the rule.
- **Development gains mostly did not carry over to the test.** Tuning raised development AP for most models, but test AP fell for ExtraTrees (0.378 to 0.308), lstm_raw (0.446 to 0.408) and lstm_log (0.457 to 0.382) on today. It rose for forest (0.268 to 0.353), boosting (0.189 to 0.221) and lstm_batches on tomorrow. With 17 development events, the search partly fitted noise in the folds.
- **The ranking still changes between development and test.** In tuned development, lstm_log leads on today AP and the rule is last. On the test, lstm_raw leads and boosting is last.
- **Fixed-threshold F1 on the test stays at or below 0.39.** The threshold is the one maximising F1 on out-of-fold development scores. Recall of 0.75 at thresholds fixed beforehand costs 76 to 140 false alarm days per catchment-year for the models, and 45 to 51 for the rule. The proposal's acceptance level is still not met.
