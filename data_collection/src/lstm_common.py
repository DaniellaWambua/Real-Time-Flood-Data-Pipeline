import numpy as np
import tensorflow as tf
from sequences import make_windows
from comparison_setup import load

EPOCHS = 15
# name, rainfall inputs, training mode
VARIANTS = [("raw", "raw", "weights"), ("log", "log", "weights"), ("batches", "raw", "batches")]


def load_windows(which, inputs, t=14):
    """Windows from sequences.py with known labels, aligned to the rows of comparison_setup.load."""
    X, meta = make_windows(t=t)
    if inputs == "log":
        X[:, :, :5] = np.log1p(X[:, :, :5])
    rows = load(which)[["catchment", "date", "tdate", "teid", "y"]]
    meta = meta[["catchment", "date", "year"]].merge(rows, on=["catchment", "date"], how="left")
    keep = meta["y"].notna().values
    meta = meta[keep].reset_index(drop=True)
    meta["y"] = meta["y"].astype(int)
    return X[keep], meta


def make_model(n_feats):
    # same network as train_lstm.py
    m = tf.keras.Sequential([
        tf.keras.layers.Input((14, n_feats)),
        tf.keras.layers.LSTM(32),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(1, activation="sigmoid"),
    ])
    m.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="binary_crossentropy")
    return m


def fit_predict(X, y, tr, va, seed, mode="weights"):
    # train_lstm.py modes: "weights" uses positive weight sqrt(neg/pos), "batches" pairs each
    # chunk of shuffled non-flood days with an equal draw of flood days, every epoch
    flat = X[tr].reshape(-1, X.shape[2])
    mu, sd = flat.mean(0), flat.std(0) + 1e-6
    Xtr, Xva = (X[tr] - mu) / sd, (X[va] - mu) / sd
    ytr = y[tr].astype("float32")
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
    return model.predict(Xva, verbose=0).ravel()


def make_model_cfg(t, n_feats, cfg):
    # tuning version of make_model; the frozen setting gives the same network
    m = tf.keras.Sequential([tf.keras.layers.Input((t, n_feats))] +
                            [tf.keras.layers.LSTM(cfg["units"], return_sequences=i < cfg["layers"] - 1)
                             for i in range(cfg["layers"])] +
                            [tf.keras.layers.Dropout(cfg["dropout"]), tf.keras.layers.Dense(1, activation="sigmoid")])
    m.compile(optimizer=tf.keras.optimizers.Adam(cfg["lr"]), loss="binary_crossentropy")
    return m


def fit_predict_cfg(X, y, tr, va, seed, mode, cfg):
    flat = X[tr].reshape(-1, X.shape[2])
    mu, sd = flat.mean(0), flat.std(0) + 1e-6
    Xtr, Xva = (X[tr] - mu) / sd, (X[va] - mu) / sd
    ytr = y[tr].astype("float32")
    tf.keras.utils.set_random_seed(seed)
    model = make_model_cfg(X.shape[1], X.shape[2], cfg)
    if mode == "weights":
        w = float(((ytr == 0).sum() / (ytr == 1).sum()) ** cfg["cw_power"])
        model.fit(Xtr, ytr, epochs=cfg["epochs"], batch_size=cfg["batch"], class_weight={0: 1.0, 1: w}, verbose=0)
    else:
        rng = np.random.default_rng(seed)
        pos, neg = np.where(ytr == 1)[0], np.where(ytr == 0)[0]
        for _ in range(cfg["epochs"]):
            rng.shuffle(neg)
            for chunk in np.array_split(neg, len(neg) // (cfg["batch"] // 2)):
                idx = np.concatenate([chunk, rng.choice(pos, size=len(chunk))])
                rng.shuffle(idx)
                model.train_on_batch(Xtr[idx], ytr[idx])
    return model.predict(Xva, verbose=0).ravel()
