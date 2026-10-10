
# LSTM Autoencoder training runs

Branch: feature/train (repo: Real-Time-Flood-Data-Pipeline)

## Setup

Each catchment is trained on its own first (Nairobi River, Mathare, Ngong, Motoine), the same order used in the earlier Colab work, then a combined model is trained on all four pooled together. The random seed is fixed for reproducibility. Each model picks its own anomaly threshold by searching percentiles of normal validation reconstruction error and keeping the one with the best F1 on validation.

Reconstruction error is scored on the final day of each window only, not averaged across the full 14 days. Averaging diluted a flood day's signal against the thirteen ordinary days beside it, which produced a hard cliff in the precision/recall trade-off (recall 1.0 collapsing straight to 0 with almost no middle ground). Scoring the final day only produced a genuine gradient instead, and improved F1 for every model.

## Results (test set, 2024-2025, four-catchment dataset)

Nairobi River: threshold 0.439, precision 0.098, recall 1.000, F1 0.178.
Mathare: threshold 0.482, precision 0.102, recall 1.000, F1 0.185.
Ngong: threshold 0.280, precision 0.075, recall 1.000, F1 0.139.
Motoine: threshold 0.191, precision 0.067, recall 1.000, F1 0.125.
Combined: threshold 0.321, precision 0.097, recall 1.000, F1 0.177.

Every flood window in the test period is still caught (recall 1.000 across all five models), while precision roughly doubled compared with the earlier whole-window scoring approach. Validation set size is small (5 to 20 flood windows per catchment versus 48 in test), so the exact recall figure on test should be read with that caveat in mind rather than as a guarantee. These numbers predate the seven-catchment dataset (see Phase 6) and will be superseded once retraining happens on it.

## Investigating the low precision: overfitting check and distribution shift

Recall of 1.000 alongside low precision prompted a check for overfitting: is the model just memorising training data rather than learning genuine "normal" behaviour? `src/diagnose_overfitting.py` compares reconstruction error (mean and median, on normal windows only) across train, validation and test for each catchment.

Val/train ratios are all below 1.0 (validation windows reconstruct as well as, or better than, training windows), which rules out classic overfitting. But test/train ratios are consistently 1.87x to 2.43x higher across all four catchments, for both mean and median error. The model reconstructs the 2024-2025 test period noticeably worse than either of the periods it was tuned on, in a way that overfitting does not explain.

To check whether this is a genuine shift in conditions rather than a data or modelling artefact, raw feature means were compared across the three periods (train 2010-2021, val 2022-2023, test 2024-2025), on normal (non-flood) rows only, per catchment:

- `rainfall_mm`, `rainfall_3day`, `rainfall_7day`: all consistently higher in test than train, by roughly 20-30 percent, in every one of the four catchments independently.
- `rainfall_anomaly`: negative in train and val (below the training-period average, as expected) but positive in test, again in all four catchments. What counted as "wetter than normal" during training is closer to the norm in the test period.
- `discharge_change`: consistently more positive in test than train in all four catchments (rivers rising more often or more sharply day to day).
- `river_discharge_m3s`: mixed. Nairobi River, Mathare and Ngong show modest increases; Motoine shows a slight decrease. Raw discharge is noisier and more locally determined than rainfall, so this is the one feature that does not move uniformly.

Four independent catchments moving together on four separate rainfall-derived features, plus the ruled-out overfitting explanation, points to a genuine shift in baseline conditions during 2024-2025 rather than a bug in the data or the pipeline. The test period was measurably wetter than the years the model learned "normal" from, so days that are unusually wet but not flood days in 2024-2025 still look anomalous to a model trained on a drier 2010-2021 baseline, which is a plausible direct driver of the low precision. (Phase 8 below revisits this same phenomenon more rigorously, as validation-to-test drift in reconstruction error itself, once the dataset grew to seven catchments.)

Note on `rainfall_anomaly`: reading the actual Colab labelling notebook later showed this feature is computed as `rainfall_mm` minus each catchment's mean over the *entire* 2010-2025 span, not a rolling or training-only baseline. That is a constant per catchment, so it is mathematically a pure shift of `rainfall_mm` and explains why the two correlate at exactly 1.000 (see Phase 7 below); it also explains the sign flip in a way consistent with, not contradicting, the wetter-test-period finding.

## Cross-catchment consensus

`src/evaluate_consensus.py` tests whether requiring K catchments to be flagged on the same calendar date, rather than trusting each catchment's flag alone, improves precision.

Results on the test set (four-catchment dataset), by agreement level:

Agree >=1: 206 flagged days, precision 0.058, recall 1.000, F1 0.110.
Agree >=2: 158 flagged days, precision 0.076, recall 1.000, F1 0.141.
Agree >=3: 128 flagged days, precision 0.094, recall 1.000, F1 0.171.
Agree >=4: 90 flagged days, precision 0.133, recall 1.000, F1 0.235.

Recall stays at 1.000 at every agreement level, so there is no trade-off to weigh: requiring all four catchments to agree (K=4) more than doubles F1 over trusting any single catchment alone (0.110 to 0.235). Worth re-running once seven-catchment models exist, since the agreement threshold and its interpretation may change with three more catchments in the vote.

**Correction, after reading the actual Colab labelling notebook (`Historical_Data.ipynb`):** the original justification for K=4 given here, "all 220 historical flood rows fall on 55 dates where all four catchments are flagged simultaneously, evidence that floods are basin-wide," overstated what the data actually shows. The flood register labelled events with `"catchment": "All"` and the labelling code applied that date range to every catchment present in the dataset, rather than recording each catchment's flood status independently. So every catchment being flagged on the same dates was a property of how the labels were built, not independently confirmed physical fact. The precision/recall result itself is still real, since it comes from four separately trained models' reconstruction error, genuine model behaviour, not a labelling artefact. The honest framing is "the dataset labelled every known flood identically across catchments, so requiring the independently-trained models to agree filters out each catchment's idiosyncratic false alarms," not "floods are confirmed basin-wide events." Worth remembering for the defence, since a reviewer could reasonably ask how catchment-specific flooding was verified for the original four, and until the fix below, it was not.

## Phase 6: dataset expansion

### Extraction pipeline, corrected understanding

The extraction lives across two notebooks, not one. `Historical_Data_extraction 1.ipynb` pulls CHIRPS (Earth Engine batch export to Drive, asynchronous) and GloFAS (Open-Meteo REST loop) into `chirps_raw.csv`/`glofas_raw.csv`, looping generically over two small catchment dictionaries (`CATCHMENTS` for Earth Engine geometry, `CATCHMENT_COORDS` for Open-Meteo lat/lon). `Historical_Data.ipynb` reads those two files, merges them, applies the flood register, and engineers features into `final_dataset.csv`. Adding Nzoia River, Nyando River and Tana River only needed the two dictionaries extended in the extraction notebook (no other code changes there) and the flood register fixed in `Historical_Data.ipynb`.

Points used (estimates pending confirmation, same 3km-buffered-point approach as the original four): Nzoia River -0.08, 34.07 (Budalangi); Nyando River -0.18, 34.93 (Ahero/Kano Plains); Tana River -2.27, 40.12 (Garsen/Tana Delta).

### Flood register: from `"catchment": "All"` to a sourced, catchment-specific register

The original register labelled six events with `"catchment": "All"`, applied by the masking code to every catchment present, which would have silently extended those dates to the three new catchments with no evidence they flooded then. Fixed by converting every event to an explicit `"catchments"` list.

The first attempt at sourcing dates for the new catchments relied on ReliefWeb/OCHA search results, which only turned up one single-day event for Nyando (3 January 2010) and nothing usable for Nzoia, leaving the three new catchments' combined contribution at 38 extra positive rows against 17,532 new negative rows, making the dataset's overall imbalance slightly worse (0.64% positive) rather than better. Checking the EM-DAT export already sitting in the project (`public_emdat_custom_request...xlsx`, CRED/UCLouvain) solved this properly: it has 32 Kenya flood/landslide records for 2010-2025, several with an explicit "River Basin" field naming the exact rivers affected, which is a far more systematic and citable source than manual search.

The final register (committed in `Historical_Data.ipynb`, 17 events):

Original four catchments (unchanged dates, now explicit instead of "All"): 2013-04-16/19, 2015-11-18/23, 2018-04-14/25, 2020-04-23/05-05, 2023-11-08/20, 2024-04-29/05-06.

New EM-DAT-sourced events: Motoine + Tana River 2016-04-29/05-02 (DisNo 2016-0161-KEN, fills one of the nine previously unresolved years for Motoine); Ngong 2018-03-14/20 (DisNo 2018-0116-KEN, kept as a separate event from the existing April 2018 window since EM-DAT gives it its own disaster number); Mathare 2024-04-23/24 (DisNo 2024-0247-KEN, same reasoning, kept separate from the existing late-April 2024 window); Nzoia River 2013-03-10/04-30 (DisNo 2013-0123-KEN); Nzoia+Nyando+Tana Rivers 2015-12-01/2016-01-06 (DisNo 2015-0564-KEN); Tana River 2021-04-07/05-30 (DisNo 2021-0227-KEN); Nyando River 2023-04-25/27 (DisNo 2023-0259-KEN); Tana River 2023-10-15/2024-01-01 (DisNo 2023-0721-KEN, 178 deaths); Tana River 2024-03-24/05-03 (DisNo 2024-0150-KEN, 353 deaths, replaces an earlier OCHA-sourced 2024-04-11/05-17 window for the same real event, since EM-DAT starts three weeks earlier and is a single, more authoritative source); Nzoia+Nyando Rivers 2024-12-01/12-05 (DisNo 2024-0892-KEN).

Kept from the earlier ReliefWeb pass: Nyando River 2010-01-03. Dropped: the earlier, unconfirmed Tana 2008-06-24 entry, both unverifiable and before the dataset's 2010 start, so it was never contributing any rows anyway.

Resulting positive-row counts (verified by direct computation against the full 2010-2025 daily calendar, not estimated): Nairobi River 56, Mathare 58, Ngong 63, Motoine 60, Nzoia River 94, Nyando River 46, Tana River 215. Total 592 out of 40,908 rows, 1.45%, now a better balance than the original four-catchment dataset's own 0.96%, a genuine fix to the imbalance Dr Owuor flagged rather than a cosmetic one.

### Data landed

`final_dataset.csv` (the earlier, ReliefWeb-only version) was committed as `data/raw/Dataset_labels_v5.csv`, with `CATCHMENTS` and `RAW_FEATURES_LABELS_FILE` in `src/config.py` updated to match, and `load_raw_data()`'s own validation passing cleanly (40,908 rows, 5,844 per catchment, no nulls, no missing dates). This was superseded by `Dataset_labels_v6.csv` once the EM-DAT-corrected register above was re-run and re-exported, which is what every result from Phase 8 onward uses.

## Phase 7: feature pruning

Following Dr Owuor's comment that some features are not needed for training, a correlation analysis was run across the six current features:
- `rainfall_anomaly` correlates with `rainfall_mm` at exactly 1.000 in every catchment. Reading the labelling notebook confirmed why: it is computed as `rainfall_mm` minus a constant (each catchment's mean over the full 2010-2025 span), so it is a pure linear shift of `rainfall_mm` and contributes no new information. Dropped from `FEATURE_COLUMNS` in `src/config.py`.
- The remaining five features are kept for now. `rainfall_3day` and `rainfall_7day` are correlated with `rainfall_mm` (0.65-0.85) but capture genuine accumulation effects and `rainfall_7day` is the single strongest predictor of `flood_event` (correlation 0.380), so they stay. `discharge_change` has near-zero raw correlation with the label but is the least correlated feature with the others, so it is kept pending a proper ablation test rather than dropped on correlation alone.
- `month`, `day_of_year` and `year` exist in the raw dataset but were confirmed to already be excluded from `FEATURE_COLUMNS`, so nothing changes there.

## Phase 8: threshold selection on the seven-catchment dataset, model comparison, and split narrowing

After retraining on `Dataset_labels_v6.csv` across all seven catchments (prompted in part by recovering from a corrupted `lstm_autoencoder_nairobi_river.keras` file, which forced a full retrain since `train.py` has no single-catchment option), two catchments' own independently-tuned thresholds turned out not to be meaningful: Nzoia River has 0 validation-period flood days and Nyando River has only 3, against 13 for each of the original four and 78 for Tana River, so their F1 search ties at zero everywhere and defaults to an untuned extreme percentile. This motivated a sequence of threshold-selection attempts, several of which were wrong in instructive ways.

**Attempt 1, pooling raw reconstruction error across all seven catchments into one shared threshold:** fixed Nzoia and Nyando's degenerate default, and genuinely helped four of the other five catchments, but distorted Tana River specifically (recall 0.293 to 0.146), because Tana's own validation set (78 positives) was already rich enough to tune reliably on its own, and pooling diluted that with six noisier catchments.

**Attempt 2, normalising each catchment's error by its own training-period median before pooling:** intended to fix the raw-scale mismatch between catchments, but made Nairobi River, Mathare, Ngong and Motoine collapse to recall 1.000 at precision 0.06-0.08 (effectively flagging almost every test day). Root cause, confirmed by `src/diagnose_separation.py`: these four catchments have the smallest training-period median error of all seven (0.009-0.015, well-fitted models), so dividing by that near-zero baseline turned an ordinary, modest rise in test-period error into a huge relative multiple, which is an artefact of how tightly the model already fit training data, not genuine anomalousness. `diagnose_separation.py` also confirmed the models do separate floods from ordinary days correctly in validation (flood-day median error 30-50x the ordinary-day median for every catchment with flood days in validation), ruling out "no signal" as the problem.

**Root cause identified:** validation-to-test drift. Nairobi River, Mathare, Ngong and Motoine run reconstruction error roughly three to four times higher in the 2024-2025 test window than in the 2022-2023 (later narrowed to 2023-only, see below) validation window, for ordinary and flood days alike, so a threshold tuned to validation's absolute error scale is stale by the time it meets test. Tana River, Nzoia River and Nyando River show much smaller or negative drift ratios.

**Attempt 3 and the version actually used (`src/evaluate_pooled_threshold.py`):** tune which percentile of the error distribution gives the best F1 on validation (using validation's labels), then only recalibrate that percentile against the test period's own, unlabelled error distribution for a catchment whose drift ratio (median test error over median validation error, no labels used) clears a fixed cutoff of 1.5x, decided before looking at any test result. Below that cutoff, a catchment keeps its plain validation-tuned threshold. Catchments with fewer than 10 validation positives (Nzoia, Nyando) still share one pooled threshold between themselves.

Results on the original split (train 2010-2021, val 2022-2023, test 2024-2025), `Dataset_labels_v6.csv`: Nairobi River 0.194/0.875/0.318, Mathare 0.139/1.000/0.244, Ngong 0.074/1.000/0.138, Motoine 0.131/1.000/0.232, Tana River 0.136/0.293/0.186, Nzoia River and Nyando River both 0.000/0.000/0.000 (still a data-scarcity problem, not a threshold-scheme problem: both catchments' pooled threshold has been reproduced independently by two different methods now, and no rearrangement of how the threshold is chosen manufactures flood examples their validation windows don't have), combined (precision/recall/f1) 0.123/0.529/0.199.

### Model comparison, prompted by a 50% precision / 65% recall target

Daniella set a target well above what threshold placement alone was closing in on, and asked to compare model families rather than continue tuning cutoffs. `src/compare_models.py` pools all seven catchments and trains logistic regression, random forest, gradient boosting (all supervised, using true labels with class weighting) and isolation forest (unsupervised, for a like-for-like comparison with the autoencoder), on six engineered inputs per final day: the five raw features already used for the LSTM plus that catchment's own autoencoder reconstruction error.

The motivation was that the autoencoder never trains on a single labelled flood day (by design), so its own threshold search only ever had validation-period positives to work with (13 or fewer for six of seven catchments). Supervised models are not under that restriction and can learn from the much richer training-period label counts (Nairobi River 35, Mathare 35, Ngong 42, Motoine 39, Nzoia River 89, Nyando River 37, Tana River 95), confirmed by `compare_models.py` before any model was trained.

Despite that richer signal, all four models converged on roughly the same ceiling as the LSTM threshold work: combined F1 between 0.118 (isolation forest) and 0.158 (gradient boosting), none better than the existing 0.199. Four different model families landing in the same place despite substantially more training examples is evidence the bottleneck is what the six features can tell any model, not which model is asked to interpret them. Closing the gap to 50/65 most likely needs richer features (rate-of-change, longer lag windows, a rainfall-discharge interaction term, a day's percentile rank against its own trailing history) or a supervised model that sees the full 14-day window rather than only the final day's snapshot, not a different off-the-shelf classifier on the same six numbers.

### Split-narrowing experiment

As a cheaper alternative to full walk-forward validation, `VAL_START_YEAR` was moved from 2022 to 2023 in `src/config.py` (train now 2010-2022, validation 2023 only, test unchanged at 2024-2025), to shrink the distance the model has to extrapolate forward from training to test. This required a full retrain, still on `Dataset_labels_v6.csv`, evaluated with `src/evaluate_pooled_threshold.py` (the drift-conditional pooled method above).

Result: a genuine but partial improvement. Combined F1 rose from 0.199 to 0.242 (precision 0.152, recall 0.600), and Mathare improved sharply (0.400/0.600/0.480, the best single-catchment result of the whole investigation so far). But Nairobi River, Ngong and Motoine still show recall pinned near 1.000 at precision 0.13-0.15 even after recalibration, and Nzoia River and Nyando River remain at 0.000/0.000/0.000. Narrowing the split by one year helped, but did not resolve the core drift problem for most catchments.

This split (`VAL_START_YEAR = 2023`) is now the default in `src/config.py` and carries forward into Phase 9 below.

## Phase 9: ERA5-Land soil moisture, evaporation and ONI features (`Dataset_labels_v7.csv`)

Three new features, ERA5-Land soil moisture (`soil_moisture_m3m3`), ERA5-Land evaporation (`evaporation_mm`) and the Oceanic Niño Index (`oni`), were added to `FEATURE_COLUMNS` and the dataset re-exported as `Dataset_labels_v7.csv`. The narrowed split from Phase 8 (`VAL_START_YEAR = 2023`) stayed in place, so this isolates the effect of the three new features on their own, not a combined change with the split.

Two evaluation methods were run on the retrained models, and it is worth being precise about which is which, since they produced different headline numbers from the same training run and that caused a mix-up before being sorted out:

**`src/train.py`'s own per-catchment threshold (no pooling, no drift recalibration), narrowed split, v7 features:** Nairobi River 0.041/1.000/0.079, Mathare 0.188/0.900/0.310, Ngong 0.060/1.000/0.113, Motoine 0.036/1.000/0.070, Nzoia River 0.000/0.000/0.000, Nyando River 0.077/0.200/0.111, Tana River 0.108/0.293/0.158, combined 0.096/0.529/0.162. Not directly comparable to any earlier number, since no prior result used plain `train.py` thresholds on the narrowed split.

**`src/evaluate_pooled_threshold.py`, the drift-conditional pooled method, narrowed split, v7 features (all three new features together), the actually comparable run against the logged 0.242 from Phase 8:** Nairobi River (drift 2.57, recalibrated) 0.085/1.000/0.157, Mathare (drift 2.88, recalibrated) 0.636/0.700/0.667, Ngong (drift 3.58, recalibrated) 0.182/1.000/0.308, Motoine (drift 2.79, recalibrated) 0.096/1.000/0.176, Nzoia River (drift 0.65, not recalibrated) 0.039/0.400/0.071, Nyando River (drift 0.77, not recalibrated) 0.077/0.200/0.111, Tana River (drift 0.56, not recalibrated) 0.108/0.293/0.158, combined 0.113/0.541/0.187.

### Apples-to-apples verdict: v6 versus v7 (all three features), same split, same method

Combined F1 fell from 0.242 (v6) to 0.187 (v7, all three features). Precision fell from 0.152 to 0.113 and recall fell from 0.600 to 0.541. On the method that is actually logged as the one in use, adding the three new features together made the combined result worse, not better.

The per-catchment picture explains why, and shows the new features are not a uniform loss. Mathare improved substantially (F1 0.480 to 0.667, now by far the best single-catchment result of the whole investigation). Nzoia River and Nyando River both moved off 0.000/0.000/0.000 for the first time, catching some real flood days (recall 0.400 and 0.200 respectively), though at a high false-alarm cost, especially for Nzoia (precision 0.039, meaning roughly 96 percent of its flagged days are false alarms). But Nairobi River, Motoine and Tana River all lost precision relative to their Phase 8 narrowed-split figures, and Nairobi River and Motoine in particular are now flagging almost every test day (recall pinned at 1.000) at precision below 0.10. Because the combined metric pools raw predictions across all seven catchments rather than averaging per-catchment F1, the degradation in the catchments that previously worked reasonably well outweighs the genuine gains in the catchments that previously had no signal at all.

This matches the risk flagged before these features were ever pulled (see `/projects/.../decisions-and-learnings.md`): "some ERA5 features (temperature, evaporation) may contribute noise rather than signal for these catchments." That risk has materialised asymmetrically, helping the catchments that had nothing to lose and hurting the catchments that already had clean rainfall-driven separation.

### Per-feature ablation

An `ABLATION_FEATURE` environment variable was added to `src/config.py` so each of the three new features could be trained and evaluated alone (base five features plus exactly one), without hand-editing the config between runs. Same narrowed split, same `Dataset_labels_v7.csv`, same `evaluate_pooled_threshold.py` method throughout, so this isolates each feature's individual contribution against the Phase 8 v6 baseline (combined 0.152/0.600/0.242) and the all-three-together Phase 9 result above (combined 0.113/0.541/0.187).

Results, precision/recall/F1 per catchment:

| catchment | soil moisture alone | evaporation alone | ONI alone |
|---|---|---|---|
| Nairobi River | 0.096/1.000/0.176 | 0.082/1.000/0.152 | 0.105/1.000/0.190 |
| Mathare | 0.106/1.000/0.192 | 0.127/1.000/0.225 | 0.500/0.400/0.444 |
| Ngong | 0.105/1.000/0.190 | 0.148/1.000/0.258 | 0.182/1.000/0.308 |
| Motoine | 0.092/1.000/0.168 | 0.123/1.000/0.219 | 0.079/1.000/0.147 |
| Nzoia River | 0.000/0.000/0.000 | 0.000/0.000/0.000 | 0.000/0.000/0.000 |
| Nyando River | 0.333/0.600/0.429 | 0.000/0.000/0.000 | 0.000/0.000/0.000 |
| Tana River | 0.145/0.293/0.194 | 0.127/0.488/0.201 | 0.132/0.341/0.190 |
| Combined | 0.110/0.576/0.184 | 0.118/0.635/0.200 | 0.125/0.494/0.199 |

No single feature alone recovers the v6 baseline's combined F1 of 0.242 (soil moisture alone 0.184, evaporation alone 0.200, ONI alone 0.199), though evaporation and ONI alone each edge out the all-three-together result (0.187). The more informative finding is that this is not one bad feature diluting two good ones. Each feature has its own, largely non-overlapping effect:

Soil moisture alone is entirely responsible for Nyando River's result: F1 0.429, by a wide margin the best single-catchment number for Nyando in the whole investigation, better even than the all-three combination (0.111). But alone it devastates Mathare (0.480 baseline down to 0.192) and does nothing for Nzoia.

Evaporation alone is the only condition that gives Tana River a real recall lift (0.488, versus 0.293-0.341 everywhere else), its best F1 (0.201) of any run. It also kills Nyando and Nzoia outright (0.000/0.000/0.000 for both) and still drags Mathare down, though less severely than soil moisture alone (0.225 versus 0.192).

ONI alone gives Mathare its highest-ever precision (0.500), though recall drops enough that F1 (0.444) still falls just short of the v6 baseline (0.480). It also reproduces the all-three result for Ngong exactly (0.182/1.000/0.308), suggesting ONI is doing most of Ngong's work in the full combination. Nzoia and Nyando are dead under ONI alone too.

Nzoia River gets zero signal from any single feature tested alone; its 0.039/0.400/0.071 in the all-three run only appears when all three are present together, which given Nzoia's near-total lack of validation-period flood days should be treated as a fragile, possibly unstable result rather than a reliable gain.

Mathare is the clearest case of genuine three-way interaction: the full combination (0.667) beats every single feature alone and beats the v6 baseline (0.480), but any subset of one loses badly (0.192-0.444), so Mathare's improvement cannot be attributed to any one of the three features on its own.

### Interpretation and implication for feature engineering

Nairobi River and Motoine are the clearest losers throughout: every ablation and the full combination underperform their Phase 8 v6 baseline (recall pinned at 1.000, precision 0.08-0.12 regardless of which new feature, or how many, is added). Neither catchment benefits from soil moisture, evaporation or ONI in their current form as raw point-in-time values. If more tuning time allows, re-deriving these as anomalies or rolling trends against each catchment's own history, the same treatment that worked for `rainfall_anomaly` and the 3/7-day rainfall windows, rather than discarding them outright, is a more promising direction than dropping them, since soil moisture and evaporation each independently unlock a different previously-dead catchment (Nyando, Tana) when used alone.

## Phase 10: final feature set and catchment scope decision

With all three evaluation methods and the three-way ablation on record, the question becomes which single global feature set to carry forward and whether every catchment still belongs in the system. The architecture trains one model per catchment but applies the same `FEATURE_COLUMNS` to all of them, so this is a genuine trade-off decision, not a search for a configuration that is best for everyone at once; no such configuration exists in the evidence gathered so far.

### Catchment scope: Nzoia River removed

Nzoia River is dropped from `CATCHMENTS` in `src/config.py`. The reasoning: it has 0 validation-period flood events under the current split, in every single configuration tried across Phases 8 to 9, so no catchment-specific threshold has ever been tunable for it on its own evidence. Its only non-zero appearance anywhere in the investigation (precision 0.039, recall 0.400, F1 0.071) occurred exclusively under the all-three-feature combination, riding on a pooled threshold shared with Nyando River rather than a threshold earned from Nzoia's own validation data, and that precision means roughly 96 percent of its flagged days in that one run were false alarms. Every single-feature ablation gave it exactly 0.000/0.000/0.000. This is not a volume problem (Nzoia actually has 94 positive rows across the full 2010-2025 span, more than any of the original four catchments), it is a temporal distribution problem: none of those 94 rows fall inside the 2023 validation window this split uses. No feature or threshold scheme can fix that without either resourcing more verified flood events specifically dated within the validation period, or re-splitting the data, both already flagged as open items and neither resolved yet. Given the time left in the year, scoping Nzoia out now and documenting it as a limitation (insufficient verified flood events in the validation window for reliable evaluation) is more defensible than reporting a result built on a borrowed threshold.

Nzoia is excluded by removing it from `CATCHMENTS` only, not by editing `Dataset_labels_v7.csv`; `src/data_loading.py` now filters the loaded dataframe to `CATCHMENTS` before validating, so the raw file (and Nzoia's rows within it) is untouched and the catchment can be reinstated later with a one-line change if more flood events are sourced for it. Confirmed working end to end: `load_raw_data()` now returns 35,064 rows across the six remaining catchments with no validation errors.

Nyando River is kept despite also having very few validation-period positives (3, against 13 for each of the original four and 78 for Tana), because unlike Nzoia it has shown a real, strong, non-pooled signal: F1 0.429 under soil moisture alone, the best single-catchment ablation result of the entire investigation. That result demonstrates Nyando's own validation and test periods do carry a genuine, catchable signal under the right feature, which Nzoia has not demonstrated under any configuration tested.

### Feature set: all three ERA5 features together, kept as final

No single feature set is optimal for every catchment, and that conflict is worth stating plainly rather than averaging over it. Per catchment, against the Phase 8 v6 baseline:

Nairobi River and Motoine are best left on the plain five-feature baseline. Every ERA5 addition tested, alone or combined, makes both worse (baseline precision roughly 0.13-0.15 at recall near 1.000, versus 0.08-0.19 with any new feature present). Neither benefits from soil moisture, evaporation or ONI in their current raw, point-in-time form. Ngong is best served by ONI, which reproduces the full three-feature result for Ngong exactly (0.182/1.000/0.308), identifying ONI as the catchment's active ingredient rather than the other two. Mathare is uniquely best under all three features together (F1 0.667), a result no subset reproduces (0.192-0.444 for any one feature alone). Nyando River is best under soil moisture alone (F1 0.429), and is actually hurt by adding evaporation and ONI on top (F1 0.111 once all three are present). Tana River is best under evaporation alone (F1 0.201, its only run with recall above 0.35).

No feature set dominates on every catchment, so the choice is a trade-off. All three ERA5 features together is kept as the final set, for three reasons. First, it is the only configuration that leaves no remaining catchment at a dead 0.000/0.000/0.000 (Nyando's weakest result under any ERA5 configuration is still 0.111, not zero). Second, it produces by far the strongest single result of the whole investigation (Mathare, 0.667) through a genuine interaction that cannot be reproduced by a smaller feature set, so dropping any one of the three forfeits that result entirely. Third, all three are independently defensible physical flood covariates (soil saturation, evapotranspiration deficit, ENSO-driven regional rainfall variability), which is easier to justify at the defence than a bespoke, catchment-specific feature list that the current architecture does not support without a larger engineering change to how windows are built per catchment.

This is a trade-off, not a fix, and should be presented as one. Nairobi River and Motoine remain fundamentally unresolved by this choice, exactly as they were unresolved under the Phase 8 baseline: recall pinned near 1.000, precision below 0.20, a pattern that holds across every configuration tested regardless of features. That is the validation-to-test drift problem identified in Phase 8, which the outstanding walk-forward validation run is meant to investigate, not something feature selection was ever going to fix for these two catchments.

`src/config.py` now documents this decision directly above `FEATURE_COLUMNS`, and keeps the `ABLATION_FEATURE` override as a diagnostic tool rather than an open question.

### Still to confirm

The six-catchment, final-feature-set combination (Nairobi River, Mathare, Ngong, Motoine, Nyando River, Tana River; all three ERA5 features; narrowed split) has not itself been run yet. Removing Nzoia changes the pooled combined metric (one of the noisiest, lowest-precision contributors is gone), so the real final combined number needs a fresh `python -m src.train` plus `python -m src.evaluate_pooled_threshold` pass rather than being inferred from the seven-catchment numbers above. Walk-forward validation (`src/walk_forward_validation.py`, added but not yet run on this final configuration) is still the outstanding structural check on whether the drift problem is a property of these catchments and this model generally.

## Phase 11: simplifying for explainability

Daniella flagged that the investigation (Phases 6 to 10, several evaluation scripts, several dataset versions, a drift-conditional pooled threshold scheme) had become too complex for her to explain confidently in her own words, and asked for something simple, effective and accurate instead. This phase is that simplification, done without reopening the Phase 10 decisions (final six catchments, final eight features), which stand.

### What changed

`src/config.py`'s `ABLATION_FEATURE` environment-variable branch is removed. The three-feature ablation it existed for is finished and logged (Phase 9), so the conditional logic was pure leftover complexity in the one file most likely to be read first. `FEATURE_COLUMNS` is now a single flat list of the final eight features, nothing else.

The project now has one designated "simple" headline method, `src/train.py`'s own independent per-catchment threshold (percentile search on validation maximising F1, no pooling, no drift-ratio recalibration), rather than `src/evaluate_pooled_threshold.py`'s more complex drift-conditional pooled scheme. The complex method is not deleted and is not wrong, it is kept as documented appendix material (it is modestly more effective, see Phase 9's 0.242 vs 0.199/0.187 comparisons), but it requires explaining drift ratios, a 1.5x recalibration cutoff, and shared pooled-threshold groups to justify, which is exactly the kind of thing that is hard to hold in your head and defend live. `python -m src.train` alone is now the one command that produces the headline numbers.

A new document, `system-overview-simple.md`, gives the plain-English version: what the model is (an autoencoder trained only on normal days, bad at reconstructing anything unlike what it has seen), what goes in (14 days of 8 features per river), how a flood gets flagged (final-day reconstruction error against a validation-tuned percentile cutoff), and the one honest limitation to lead with (Nairobi River and Motoine still over-flag, a known drift problem, not a bug). It also names the six files that make up the actual system (`config.py`, `data_loading.py`, `preprocessing.py`, `model.py`, `scoring.py`, `train.py`, roughly 435 lines total) versus the eight files of investigation material around them (roughly 960 lines: the `compare_models` variants, the `diagnose_` scripts, `evaluate_pooled_threshold.py`, `evaluate_consensus.py`, `walk_forward_validation.py`), so the system Daniella needs to explain is a third of the codebase, not all of it.

### Still outstanding

The final six-catchment, final-feature, simple-method numbers have not been generated yet. The code changes above were verified with the pandas-only checks available (`load_raw_data()` loads cleanly, `CATCHMENTS` and `FEATURE_COLUMNS` are correct), but training itself needs TensorFlow with the Apple Silicon `tensorflow-metal` build, which only exists in Daniella's own project virtualenv on her Mac, not in any environment Claude can execute code in directly. Running `python -m src.train` once, from the repository root with that virtualenv active, is the one remaining step; the output should be logged here as the confirmed final result once available, and used to fill in the numbers section of `system-overview-simple.md`.

## Files produced

`models/lstm_autoencoder_<catchment>.keras` and `models/lstm_autoencoder_combined.keras`, with matching figures under `reports/figures/training_curve_<name>.png`. The six core pipeline files are `config.py`, `data_loading.py`, `preprocessing.py`, `model.py`, `scoring.py` and `train.py`; `src/evaluate_pooled_threshold.py`, `src/diagnose_separation.py`, `src/diagnose_overfitting.py`, `src/evaluate_consensus.py`, `src/compare_models.py` (and its `_rank_only`/`_richer_features` variants) and `src/walk_forward_validation.py` are investigation/evaluation scripts documenting how the six core files' choices were reached, not part of running the system day to day. `src/config.py` documents the Phase 10 final feature set and catchment-scope decisions directly in its comments and, as of Phase 11, holds a single flat `FEATURE_COLUMNS` list with no runtime branching. `src/data_loading.py` filters the loaded dataframe to `CATCHMENTS` before validating, so a catchment can be scoped in or out via `CATCHMENTS` alone without editing the raw dataset file. `system-overview-simple.md` is the plain-English companion to this file, meant to be read and explained on its own. Phases 8 to 11 are committed and merged to `main`: Phases 8-9 via earlier PRs, and the Phase 10/11 `config.py`/`data_loading.py` changes via `feat/finalize-catchment-scope` (merged). The database, authentication and Kafka ingestion/stream-processing layers have since been built on top of this (see docs/development-plan.md phases 9-12).
