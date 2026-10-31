
# The flood early-warning model, in plain terms

This is the version to actually say out loud at the defence. The detailed investigation behind every choice here lives in training-results.md; you don't need to recite that, just know it exists if someone pushes on a specific number.

## What it is

Six rivers around Nairobi (Nairobi River, Mathare, Ngong, Motoine, Mukuru, Ruaraka) each get their own small neural network, called an autoencoder. This set matches the proposal's own scope (Nairobi and its immediate catchments); Nyando River and Tana River, added partway through for data volume, have since been dropped in favour of Mukuru and Ruaraka, two Nairobi catchments identified from flood reports as data-rich and flood-prone. An autoencoder's only job is to compress something down to a few numbers and then rebuild the original from them. This one is trained only on ordinary, non-flood days, so it becomes good at rebuilding ordinary weeks and comparatively bad at rebuilding weeks that look unlike anything it was trained on. A flood week is exactly that kind of unlike-anything-it-has-seen week.

## What goes in

For every day, the model looks at the preceding 14 days of 8 numbers per river: rainfall that day, the river's discharge (flow), rainfall accumulated over the past 3 and 7 days, how sharply discharge is changing day to day, soil moisture, evaporation, and a Pacific Ocean climate index (ONI) that is linked to East African rainfall. Those are the final feature set, decided after testing each new addition on its own and all together.

## How a flood gets flagged

The model reconstructs the 14-day window and the reconstruction error is measured on the final day only, not averaged across all 14, because a flood label belongs to that one day and averaging would wash its signal out against 13 ordinary days beside it. A bigger final-day error means the model found that day harder to reconstruct, which is the anomaly signal.

Each river picks its own cutoff for "unusual enough to flag." This is done by trying a wide range of percentile cutoffs against a held-out validation period and keeping whichever gives the best F1 score there (the best balance of catching real floods against not crying wolf too often). That one cutoff, fixed after validation, is then applied unchanged to a separate, later test period the model has never seen, which is where every number below comes from.

## What the actual code is

Six files, roughly 435 lines total: `config.py` (the settings above), `data_loading.py` (reads and checks the data), `preprocessing.py` (builds the 14-day windows), `model.py` (the autoencoder itself), `scoring.py` (the reconstruction-error and threshold logic described above), `train.py` (runs the whole thing end to end, one river at a time, then once more with all rivers pooled together). Everything else in `src/` (the compare_models variants, the diagnose scripts, evaluate_pooled_threshold.py, evaluate_consensus.py, walk_forward_validation.py) is the investigation that justified the choices baked into those six files. It is not part of what you run day to day, and you do not need to hold it in your head to explain the system; it is backup material if someone asks a follow-up you want to answer with evidence.

Running `python -m src.train` from the repository root is the entire system, start to finish: load the data, train six models plus one combined model, pick each one's threshold, test it, print the results.

## The numbers

Test set 2024-2025, `src/train.py`'s own per-catchment threshold:

| catchment | precision | recall | F1 |
|---|---|---|---|
| Nairobi River | 0.234 | 0.767 | 0.358 |
| Mathare | 0.283 | 0.609 | 0.386 |
| Ngong | 0.198 | 0.831 | 0.320 |
| Motoine | 0.178 | 0.906 | 0.297 |
| Mukuru | 0.373 | 0.610 | 0.463 |
| Ruaraka | 0.378 | 0.705 | 0.492 |
| Combined | 0.172 | 0.901 | 0.288 |

In plain terms: the model catches most real floods (recall mostly 0.6-0.9), but still raises a lot of false alarms (precision mostly 0.18-0.38), so roughly five of every six flagged days across the whole system are not actually flood days.

## The one honest limitation to lead with

Motoine and Ngong still flag most days in the test period as a possible flood (recall 0.91 and 0.83) at modest precision (0.18 and 0.20), so they lean toward over-flagging rather than genuinely discriminating. Mukuru and Ruaraka, the two newest catchments, are currently the model's best performers by a clear margin, which is encouraging but still only two rivers' worth of evidence. If asked, that is the honest answer: the model reliably catches most real floods, but combined precision of 0.17 means the system still cries wolf considerably more often than it is right.
