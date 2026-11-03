import os
import pandas as pd
from sklearn.metrics import average_precision_score
from comparison_setup import FINAL_FOLD, SEEDS, OUT, score_rows
from lstm_common import load_windows, fit_predict, VARIANTS

# Final test: LSTM variants trained on 2015-2023, scored once on 2024-2025
path = f"{OUT}/final_scores_lstm.csv"
assert not os.path.exists(path), "final test already run"
train_years, test_years = FINAL_FOLD
parts = []
for which in ["today", "tomorrow"]:
    for variant, inputs, mode in VARIANTS:
        X, meta = load_windows(which, inputs)
        y = meta["y"].values
        tr = meta["year"].isin(list(train_years)).values
        te = meta["year"].isin(test_years).values
        for seed in SEEDS:
            s = fit_predict(X, y, tr, te, seed, mode)
            parts.append(score_rows(meta, te, which, test_years, f"lstm_{variant}", seed, s))
            print(which, variant, seed, "AP", round(average_precision_score(y[te], s), 3), flush=True)

pd.concat(parts).to_csv(path, index=False)
