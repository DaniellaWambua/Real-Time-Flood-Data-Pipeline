import json, os
import numpy as np, pandas as pd, tensorflow as tf
import comparison_setup as cs
from sequences import make_windows, SEQ_FEATS, CATCHMENTS
from lstm_common import make_model, EPOCHS

# Saves the model the system uses (v2): the frozen lstm_raw network trained with event weights
# (event_train.py "eventweight"), audited labels, today target, 2015-2023, eight seeds.
# Event weights: flood days start at sqrt(dry days / flood days), then each is scaled by
# mean event length / its event length, so every flood event carries the same total weight.
# v1 (plain sqrt class weight, threshold 0.555) is kept in models/flood_lstm_v1/.
D = "data_collection/data/08_model_ready/"
OUT = "models/flood_lstm/"
VERSION = "v2"
TRAIN_YEARS = list(range(2015, 2024))
SEEDS = list(range(8))
THRESHOLD = 0.528  # best day-level F1 of the 8-seed mean on the pooled development folds (event_train_evaluate.py)

cs.PATH = D + "features_daily_audited.csv"
X, meta = make_windows(path=cs.PATH)
st = meta["label_status"].values
flood = st == "flood"
tr = meta["year"].isin(TRAIN_YEARS).values & np.isin(st, ["flood", "no_flood"])
y = flood.astype("float32")

# scaling values from the training windows only, as in fit_predict
flat = X[tr].reshape(-1, X.shape[2])
mu, sd = flat.mean(0), flat.std(0) + 1e-6
Xtr, ytr = (X[tr] - mu) / sd, y[tr]
w = float(np.sqrt((tr & ~flood).sum() / (tr & flood).sum()))
eid = meta["event_id"].where(flood)
L = meta[tr & flood].groupby(eid[tr & flood]).size()
sw = np.where(flood, w * L.mean() / eid.map(L).fillna(1).values, 1.0)[tr]

os.makedirs(OUT, exist_ok=True)
for seed in SEEDS:
    tf.keras.utils.set_random_seed(seed)
    model = make_model(X.shape[2])
    model.fit(Xtr, ytr, sample_weight=sw, epochs=EPOCHS, batch_size=64, verbose=0)
    model.save_weights(OUT + f"lstm_raw_seed{seed}.weights.h5")
    print("saved seed", seed, flush=True)

config = {"version": VERSION, "training": "event-weighted", "features": SEQ_FEATS + [f"is_{c}" for c in CATCHMENTS],
          "window": 14, "mean": mu.tolist(), "std": sd.tolist(), "threshold": THRESHOLD, "seeds": SEEDS,
          "train_years": [TRAIN_YEARS[0], TRAIN_YEARS[-1]],
          "labels": "features_daily_audited.csv", "target": "today"}
with open(OUT + "config.json", "w") as f:
    json.dump(config, f, indent=2)
print("written", OUT)
