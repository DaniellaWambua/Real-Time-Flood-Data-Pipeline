import pandas as pd
from sklearn.metrics import average_precision_score
from comparison_setup import DEV_FOLDS, SEEDS, OUT, score_rows
from lstm_common import load_windows, fit_predict, VARIANTS

# LSTM on the development folds: class weights with raw or log rainfall, and balanced batches
parts = []
for which in ["today", "tomorrow"]:
    for variant, inputs, mode in VARIANTS:
        X, meta = load_windows(which, inputs)
        y = meta["y"].values
        for train_years, val_years in DEV_FOLDS:
            tr = meta["year"].isin(list(train_years)).values
            va = meta["year"].isin(val_years).values
            for seed in SEEDS:
                s = fit_predict(X, y, tr, va, seed, mode)
                parts.append(score_rows(meta, va, which, val_years, f"lstm_{variant}", seed, s))
                print(which, variant, val_years[0], seed, "AP", round(average_precision_score(y[va], s), 3), flush=True)

pd.concat(parts).to_csv(f"{OUT}/dev_scores_lstm.csv", index=False)
