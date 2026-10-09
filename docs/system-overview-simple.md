
# The flood early-warning model, in plain terms

This is the version to actually say out loud at the defence. The detailed investigation behind every choice here lives in training-results.md; you don't need to recite that, just know it exists if someone pushes on a specific number.

## What it is

Six rivers around Nairobi (Nairobi River, Mathare, Ngong, Motoine, Nyando River, Tana River) each get their own small neural network, called an autoencoder. An autoencoder's only job is to compress something down to a few numbers and then rebuild the original from them. This one is trained only on ordinary, non-flood days, so it becomes good at rebuilding ordinary weeks and comparatively bad at rebuilding weeks that look unlike anything it was trained on. A flood week is exactly that kind of unlike-anything-it-has-seen week.

## What goes in

For every day, the model looks at the preceding 14 days of 8 numbers per river: rainfall that day, the river's discharge (flow), rainfall accumulated over the past 3 and 7 days, how sharply discharge is changing day to day, soil moisture, evaporation, and a Pacific Ocean climate index (ONI) that is linked to East African rainfall. Those are the final feature set, decided after testing each new addition on its own and all together.

## How a flood gets flagged

The model reconstructs the 14-day window and the reconstruction error is measured on the final day only, not averaged across all 14, because a flood label belongs to that one day and averaging would wash its signal out against 13 ordinary days beside it. A bigger final-day error means the model found that day harder to reconstruct, which is the anomaly signal.

Each river picks its own cutoff for "unusual enough to flag." This is done by trying a wide range of percentile cutoffs against a held-out validation period and keeping whichever gives the best F1 score there (the best balance of catching real floods against not crying wolf too often). That one cutoff, fixed after validation, is then applied unchanged to a separate, later test period the model has never seen, which is where every number below comes from.

## What the actual code is

Six files, roughly 435 lines total: `config.py` (the settings above), `data_loading.py` (reads and checks the data), `preprocessing.py` (builds the 14-day windows), `model.py` (the autoencoder itself), `scoring.py` (the reconstruction-error and threshold logic described above), `train.py` (runs the whole thing end to end, one river at a time, then once more with all rivers pooled together). Everything else in `src/` (the compare_models variants, the diagnose scripts, evaluate_pooled_threshold.py, evaluate_consensus.py, walk_forward_validation.py) is the investigation that justified the choices baked into those six files. It is not part of what you run day to day, and you do not need to hold it in your head to explain the system; it is backup material if someone asks a follow-up you want to answer with evidence.

Running `python -m src.train` from the repository root is the entire system, start to finish: load the data, train six models plus one combined model, pick each one's threshold, test it, print the results.

## The numbers

*(filled in once the first post-simplification run finishes: run `python -m src.train`, with Nzoia River already removed and the final 8-feature set already in place, and send the output to Claude)*

## The one honest limitation to lead with

Two of the six rivers, Nairobi River and Motoine, currently flag almost every day in the test period as a possible flood. Rainfall and discharge there in 2024-2025 run measurably higher than in the years the model learned "normal" from, which is a real shift in conditions, not a bug, and it makes the model's idea of "unusual" stale by the time it reaches the test period. That is the open problem the next piece of work, testing the model across several different historical time windows rather than just one, is meant to pin down. If asked, that is the honest answer: the model reliably catches floods, but for these two rivers it currently does so by flagging too many ordinary days alongside them.
