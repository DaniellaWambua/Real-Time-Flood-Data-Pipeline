import sys
import numpy as np, pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score
from sequences import make_windows

which, mode = sys.argv[1], sys.argv[2]   # today or tomorrow, weights or batches
tf_mode = sys.argv[3] if len(sys.argv) > 3 else "raw"
col = "label_status" if which == "today" else "next_status"
EPOCHS = 15
FOLDS = [(range(2015, 2019), [2019]), (range(2015, 2021), [2021, 2022]), (range(2015, 2023), [2023])]

X, meta = make_windows()
if tf_mode == "log":
    X[:, :, :5] = np.log1p(X[:, :, :5])
keep = meta[col].isin(["flood", "no_flood"]).values
X, meta = X[keep], meta[keep].reset_index(drop=True)
y = (meta[col] == "flood").astype("float32").values

def recall_top(yv, s, q=0.05):
    k = max(1, int(len(yv) * q))
    return yv[np.argsort(-s)[:k]].sum() / yv.sum()

def make_model(n_feats):
    m = tf.keras.Sequential([
        tf.keras.layers.Input((14, n_feats)),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    return m

rows = []
for train_years, val_years in FOLDS:
    tr = meta["year"].isin(list(train_years)).values
    va = meta["year"].isin(val_years).values
    flat = X[tr].reshape(-1, X.shape[2])
    mu, sd = flat.mean(0), flat.std(0) + 1e-6
    Xtr, Xva = (X[tr] - mu) / sd, (X[va] - mu) / sd
    ytr, yva = y[tr], y[va]
    aps, recs = [], []
    for seed in range(3):
        tf.keras.utils.set_random_seed(seed)
        model = make_model(X.shape[2])
        if mode == "weights":
            w = float(np.sqrt((ytr == 0).sum() / (ytr == 1).sum()))
            model.fit(Xtr, ytr, epochs=EPOCHS, batch_size=64, class_weight={0: 1.0, 1: w}, verbose=0)
        else:
            rng = np.random.default_rng(seed)
            pos, neg = np.where(ytr == 1)[0], np.where(ytr == 0)[0]
            for _ in range(EPOCHS):
                rng.shuffle(neg)
                for chunk in np.array_split(neg, len(neg) // 32):
                    idx = np.concatenate([chunk, rng.choice(pos, size=len(chunk))])
                    rng.shuffle(idx)
                    model.train_on_batch(Xtr[idx], ytr[idx])
        s = model.predict(Xva, verbose=0).ravel()
        aps.append(average_precision_score(yva, s))
        recs.append(recall_top(yva, s))
    rows.append({"target": which, "mode": mode, "val": val_years[0], "base_rate": round(yva.mean(), 3),
                 "avg_precision": round(np.mean(aps), 3), "recall_top5pct": round(np.mean(recs), 2)})
    print(rows[-1], flush=True)

res = pd.DataFrame(rows)
print(res.to_string(index=False))
print("mean avg_precision", round(res["avg_precision"].mean(), 3),
      "mean recall_top5pct", round(res["recall_top5pct"].mean(), 2))
res.to_csv(f"data_collection/data/08_model_ready/lstm_{which}_{mode}_{tf_mode}.csv", index=False)