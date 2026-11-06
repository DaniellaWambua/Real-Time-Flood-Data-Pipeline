import json, os
import numpy as np, tensorflow as tf
import comparison_setup as cs
from sequences import make_windows, SEQ_FEATS, CATCHMENTS
from lstm_common import make_model, EPOCHS

# Saves the model the system currently uses: frozen lstm_raw, audited labels, today target, 2015-2023
D = "data_collection/data/08_model_ready/"
OUT = "models/flood_lstm/"
VERSION = "v1" 
TRAIN_YEARS = list(range(2015, 2024))
SEEDS = list(range(8))
THRESHOLD = 0.555  # best F1 of the 8-seed mean on the pooled development folds

cs.PATH = D + "features_daily_audited.csv"
X, meta = make_windows(path=cs.PATH)
lab = cs.load("today")[["catchment", "date", "y"]]
meta = meta.merge(lab, on=["catchment", "date"], how="left")
tr = (meta["year"].isin(TRAIN_YEARS) & meta["y"].notna()).values
y = meta["y"].fillna(0).astype("float32").values

# scaling values from the training windows only, as in fit_predict
flat = X[tr].reshape(-1, X.shape[2])
mu, sd = flat.mean(0), flat.std(0) + 1e-6
Xtr, ytr = (X[tr] - mu) / sd, y[tr]
w = float(np.sqrt((ytr == 0).sum() / (ytr == 1).sum()))

os.makedirs(OUT, exist_ok=True)
for seed in SEEDS:
    tf.keras.utils.set_random_seed(seed)
    model = make_model(X.shape[2])
    model.fit(Xtr, ytr, epochs=EPOCHS, batch_size=64, class_weight={0: 1.0, 1: w}, verbose=0)
    model.save_weights(OUT + f"lstm_raw_seed{seed}.weights.h5")
    print("saved seed", seed, flush=True)

config = {"version": VERSION, "features": SEQ_FEATS + [f"is_{c}" for c in CATCHMENTS], "window": 14,
          "mean": mu.tolist(), "std": sd.tolist(), "threshold": THRESHOLD, "seeds": SEEDS,
          "train_years": [TRAIN_YEARS[0], TRAIN_YEARS[-1]],
          "labels": "features_daily_audited.csv", "target": "today"}
with open(OUT + "config.json", "w") as f:
    json.dump(config, f, indent=2)
print("written", OUT)