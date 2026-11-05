# Retraining on audited labels, 3 November 2026

This compares every model trained on the original labels with the same model trained on the audited labels of D11, each judged against both label sets. The protocol is decisions.md D13. All numbers are in `retrain_results.csv`. Per-seed AP for the 8-seed LSTM runs is in `retrain_lstm_seeds.csv`, and the chart is `retrain_comparison.png`. Unless stated otherwise, AP is pooled average precision over the three development folds (the D8 primary measure), judged on the audited labels, for the today target.

## What was run
- (a) All seven models with the frozen D8 settings, seeds 0 to 2. The rule has no seed.
- (b) The same models with the tuned D10 settings. The tuned rule keeps rain_sum_3d, so it is the same run as the frozen rule.
- (c) The three LSTM variants with seeds 0 to 7, under both settings, and an 8-seed ensemble that averages the score per day.

Each run was made once with the original labels and once with the audited labels, for both targets. On the development folds the audited labels add 2 flood days (53 to 55) and 3 events (17 to 20). On 2024-2025 they add 9 flood days (87 to 96) and 12 events (26 to 38).

## Reproduction
Before anything else, the frozen settings were trained and judged on the original labels and compared with `comparison_results.csv`. All 154 development numbers match to three decimals: AP pooled and mean of folds, maximum F1, top 5 percent recall, and event recall and false alarm days at 3, 5 and 10 percent, for seven models and two targets. The same holds for the 154 numbers of D9 on 2024-2025. The check is in `retrain_reproduction_dev.csv` and `retrain_reproduction_final.csv`.

## Development ranking
Today target, the leading approaches by pooled AP judged on the audited labels. AP on the original labels and mean-of-folds AP are given for comparison. The full ranking of 37 approaches for both targets is in `retrain_results.csv`.

| Rank | Approach | Trained on | AP audited | AP original | AP fold mean | Precision at 5% | Recall at 5% | POD at 5% |
|---|---|---|---|---|---|---|---|---|
| 1 | lstm_log tuned, 8-seed ensemble | audited | 0.153 | 0.149 | 0.290 | 0.097 | 0.382 | 0.450 |
| 2 | boosting frozen | original | 0.148 | 0.127 | 0.238 | 0.116 | 0.454 | 0.600 |
| 3 | boosting frozen | audited | 0.142 | 0.122 | 0.230 | 0.111 | 0.436 | 0.550 |
| 4 | lstm_log tuned, 8-seed ensemble | original | 0.141 | 0.135 | 0.278 | 0.097 | 0.382 | 0.450 |
| 5 | lstm_log tuned, mean of 8 seeds | audited | 0.135 | 0.132 | 0.268 | 0.101 | 0.396 | 0.488 |
| 7 | extra_trees tuned | audited | 0.131 | 0.121 | 0.246 | 0.128 | 0.503 | 0.650 |
| 12 | rule_rain_3d | none | 0.112 | 0.101 | 0.147 | 0.137 | 0.546 | 0.600 |

For the tomorrow target the order changes. Frozen boosting trained on audited labels leads (AP 0.135), followed by frozen boosting on original labels (0.126) and tuned boosting (0.121), with the rule at 0.096. The tuned lstm_log ensemble falls to 11th on pooled AP (0.091), but it is first on mean-of-folds AP for both targets (0.290 today, 0.230 tomorrow).

Other development measures do not favour the same approach:
- **Precision at a 5 percent alarm share:** the rule is the most precise (0.137 today). The best model is tuned ExtraTrees (0.128 to 0.130).
- **Event POD at 5 percent:** forest is highest (0.683).
- **Maximum F1:** frozen boosting trained on audited labels is highest (0.259), against 0.234 for the rule.

## Which approach is best on development, and by how much
No approach is clearly best on development.
- **Today target:** the leader, the tuned lstm_log ensemble trained on audited labels, is 0.005 AP ahead of frozen boosting. The 8 single seeds of that LSTM have a standard deviation of 0.014, so the margin is about a third of the seed-to-seed spread.
- **Tomorrow target:** the leader is frozen boosting trained on audited labels, 0.009 ahead of the same model trained on original labels.
- **Against the rule:** no approach is significantly better than the rule. The 95 percent block bootstrap interval for the difference in AP includes zero for every approach except the frozen lstm_log runs for the tomorrow target, which are significantly worse. For example, the interval runs from -0.055 to 0.181 for the today leader and from -0.026 to 0.120 for the tomorrow leader.
- **AP definition:** the leader depends on whether pooled or mean-of-folds AP is used, which is a further sign that the differences are small.

Three effects can be read with more confidence.
- **Training labels.** Training on audited labels changes development AP by between -0.010 and 0.015 for the trees, and the sign varies by model and target. For the 8-seed LSTM runs the mean change is between -0.009 and 0.014. Between 1 and 8 of the 8 seeds improve, with no consistent direction except tuned lstm_log and lstm_raw for the tomorrow target (8 and 7 of 8 seeds better, gains of 0.012 and 0.005). Judging the same model against the audited labels raises AP for most models, by up to 0.021 (frozen boosting, today), as in D12. Most of the label effect is therefore in measurement rather than training.
- **Tuned settings for lstm_log.** On development, the tuned setting beats the frozen one in 8 of 8 seeds for both targets and both label sets. The mean gain is 0.030 to 0.067, which is larger than the seed spread. For lstm_raw and lstm_batches the tuned setting is within seed noise (4 to 6 of 8 seeds better).
- **Seed ensembles.** The 8-seed ensemble beats the mean single seed in 40 of 48 development comparisons, by 0.009 AP on average (range -0.003 to 0.035).

## 2024-2025, secondary check
This period was already seen in D9, D10 and D12. The numbers below are a secondary check and not an unseen test, and no choice should rest on them.

| Approach | Trained on | AP audited | Precision at 5% | Recall at 5% | F1 at 5% | POD at 5% | FAR at 5% | False alarm days per catchment-year |
|---|---|---|---|---|---|---|---|---|
| lstm_raw frozen, 8-seed ensemble | audited | 0.544 | 0.500 | 0.531 | 0.515 | 0.553 | 0.441 | 8.5 |
| lstm_log frozen, 8-seed ensemble | audited | 0.526 | 0.461 | 0.490 | 0.475 | 0.526 | 0.571 | 9.2 |
| lstm_raw frozen, 8-seed ensemble | original | 0.508 | 0.480 | 0.510 | 0.495 | 0.500 | 0.500 | 8.8 |
| lstm_log tuned, 8-seed ensemble (development leader, today) | audited | 0.451 | 0.431 | 0.458 | 0.444 | 0.579 | 0.487 | 9.7 |
| rule_rain_3d | none | 0.341 | 0.422 | 0.448 | 0.434 | 0.632 | 0.521 | 9.8 |
| boosting frozen (development second, today) | original | 0.206 | 0.216 | 0.229 | 0.222 | 0.421 | 0.769 | 13.3 |

- **Ranking.** The 2024-2025 ranking does not follow the development ranking. Boosting, second on development, is last on 2024-2025 for the today target. The frozen LSTM ensembles, which were in the lower half on development, lead.
- **Tuned settings.** The tuned lstm_log and lstm_raw settings are worse than the frozen ones in most seeds on this period (0 to 4 of 8 seeds better). This is the reverse of development and repeats the D10 finding.
- **Training labels.** Training on audited labels raises AP for lstm_raw and lstm_log by 0.027 to 0.043 for the today target, in 6 to 8 of 8 seeds. For the trees the change is between -0.015 and 0.035.
- **Ensembles.** The ensemble beats the mean single seed in all 48 comparisons, by 0.043 AP on average.

## What the results show
- **No single approach is clearly best on development.** The lead changes with the target and the AP definition, and no approach is significantly better than the rule.
- **The label audit helps measurement more than training.** Judging against audited labels raises AP for most models. Training on them gives small gains with mixed signs on development, because the training years changed little.
- **Two changes are consistent across seeds.** The tuned lstm_log setting is better than the frozen one on development in every seed, and the 8-seed ensemble is better than a single seed in almost every comparison.
- **Development and 2024-2025 disagree.** This is as in D9 and D10, and it means a development choice will carry wide uncertainty whatever it is.

## What the results do not show
- **They are not an unseen test.** No period remains that has not been seen.
- **They do not cover labels outside the audit scope.** Training labels before 2022 are unchanged apart from group A (D11), so these runs cannot show the effect of a fuller audit.
- **They do not identify a strong model.** With 17 to 20 development events, differences of 0.01 to 0.02 AP cannot be separated from sampling noise.

## How to reproduce
Run from the repo root with the Python in `~/venvs/flood-model`.

```
export PYTHONPATH=data_collection/src
PY=~/venvs/flood-model/bin/python
$PY data_collection/src/retrain_scores.py frozen trees dev original
$PY data_collection/src/retrain_scores.py frozen lstm dev original 0-2
$PY data_collection/src/retrain_check.py dev
for s in frozen tuned; do for sp in dev final; do for tl in original audited; do
  $PY data_collection/src/retrain_scores.py $s trees $sp $tl
  $PY data_collection/src/retrain_scores.py $s lstm $sp $tl 0-2
  $PY data_collection/src/retrain_scores.py $s lstm $sp $tl 3-7
done; done; done
$PY data_collection/src/retrain_check.py final
$PY data_collection/src/retrain_evaluate.py
$PY data_collection/src/retrain_plot.py
```

The loop repeats the two runs already made for the check, which gives the same scores. On an 8-core machine each tree run took under a minute and each LSTM run 3 to 8 minutes. With four runs in parallel the whole set took about 30 minutes, and the evaluation about 3 minutes. The score files (`retrain_*_scores_*.csv`) are working files and are not committed, as with the other score files.
