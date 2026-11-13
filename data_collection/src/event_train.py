import sys
import numpy as np, pandas as pd
import tensorflow as tf
sys.path.insert(0, "data_collection/src")
import comparison_setup as cs
from sequences import make_windows
from lstm_common import make_model, EPOCHS

# Event-aware training for the frozen lstm_raw network (same inputs, layers, epochs and batch size).
#   day          current method, day labels, flood days weighted sqrt(dry/flood)
#   eventweight  day labels, each flood day weighted by mean event length / its event length, so every event
#                carries the same total weight (total flood weight kept equal to "day")
#   window       the day before and after each flood day become flood days (the +-1 day tolerance used in
#                event scoring), the second buffer day stays unknown; sqrt(dry/flood) weight
#   anyday       multiple-instance loss: each event (its days plus one day either side) is one bag that only
#                needs its highest score to be high; dry days use ordinary cross-entropy
# Usage: event_train.py variant dev|final first-last [drop=feature,feature]
# drop= removes input features, e.g. drop=rain_mm for a model that does not wait for CHIRPS.
D = "data_collection/data/08_model_ready/"
VARIANT, SPLIT = sys.argv[1], sys.argv[2]
lo, hi = map(int, sys.argv[3].split("-"))
cs.PATH = D + "features_daily_audited.csv"
FOLDS = cs.DEV_FOLDS if SPLIT == "dev" else [cs.FINAL_FOLD]
DAY = pd.Timedelta(days=1)

X, meta = make_windows(path=cs.PATH)
DROP = sys.argv[4].split("=", 1)[1].split(",") if len(sys.argv) > 4 else []
TAG = ("_no_" + "_".join(DROP)) if DROP else ""
if DROP:
    from sequences import SEQ_FEATS, CATCHMENTS
    names = SEQ_FEATS + [f"is_{c}" for c in CATCHMENTS]
    X = X[:, :, [i for i, n in enumerate(names) if n not in DROP]]
st = meta["label_status"].values
flood = st == "flood"
known = np.isin(st, ["flood", "no_flood"])
# event membership and +-1 day neighbours, per catchment
meta["eid"] = meta["event_id"].where(flood)
nb_eid = pd.Series(np.nan, index=meta.index, dtype=object)
for c, g in meta.groupby("catchment"):
    e = g["eid"]
    for k in (-1, 1):
        sh = e.shift(-k)  # event id of the day k days ahead
        nb_eid.loc[g.index] = nb_eid.loc[g.index].where(nb_eid.loc[g.index].notna(), sh)
bag_id = meta["eid"].where(meta["eid"].notna(), nb_eid)  # event id for event days and their +-1 neighbours


def standardise(tr, va):
    flat = X[tr].reshape(-1, X.shape[2])
    mu, sd = flat.mean(0), flat.std(0) + 1e-6
    return (X[tr] - mu) / sd, (X[va] - mu) / sd, mu, sd


def fit_weighted(tr, va, y, sw, seed):
    Xtr, Xva, _, _ = standardise(tr, va)
    tf.keras.utils.set_random_seed(seed)
    m = make_model(X.shape[2])
    m.fit(Xtr, y[tr].astype("float32"), sample_weight=sw[tr], epochs=EPOCHS, batch_size=64, verbose=0)
    return m.predict(Xva, verbose=0).ravel()


def fit_anyday(tr_years, va, seed):
    yr = meta["year"].isin(list(tr_years)).values
    neg = np.where(yr & (st == "no_flood"))[0]
    bags = meta[yr & bag_id.notna().values].groupby(bag_id[yr & bag_id.notna().values]).indices
    bags = [meta.index[yr & bag_id.notna().values][v] for v in bags.values()]
    tr = yr & (known | bag_id.notna().values)
    flat = X[tr].reshape(-1, X.shape[2])
    mu, sd = flat.mean(0), flat.std(0) + 1e-6
    Xs = ((X - mu) / sd).astype("float32")
    bag_idx = np.concatenate(bags)
    seg = np.concatenate([np.full(len(b), i) for i, b in enumerate(bags)]).astype("int32")
    Xbag = tf.constant(Xs[bag_idx])
    tf.keras.utils.set_random_seed(seed)
    m = make_model(X.shape[2])
    opt = tf.keras.optimizers.Adam(1e-3)
    nb = len(bags)

    @tf.function
    def step(xn):
        with tf.GradientTape() as tape:
            pn = tf.squeeze(m(xn, training=True), 1)
            pb = tf.squeeze(m(Xbag, training=True), 1)
            pmax = tf.math.unsorted_segment_max(pb, seg, nb)
            eps = 1e-6
            loss = -tf.reduce_mean(tf.math.log(1 - pn + eps)) - tf.reduce_mean(tf.math.log(pmax + eps))
        g = tape.gradient(loss, m.trainable_variables)
        opt.apply_gradients(zip(g, m.trainable_variables))

    rng = np.random.default_rng(seed)
    for _ in range(EPOCHS):
        rng.shuffle(neg)
        for chunk in np.array_split(neg, len(neg) // 64):
            step(tf.constant(Xs[chunk]))
    return m.predict(Xs[va], verbose=0).ravel()


parts = []
for train_years, val_years in FOLDS:
    yr = meta["year"].isin(list(train_years)).values
    va = meta["year"].isin(val_years).values
    if VARIANT in ("day", "eventweight"):
        y = flood.astype(int)
        tr = yr & known
        w = np.sqrt((tr & ~flood).sum() / (tr & flood).sum())
        sw = np.where(flood, w, 1.0)
        if VARIANT == "eventweight":
            L = meta[tr & flood].groupby("eid").size()
            sw = np.where(flood & tr, w * L.mean() / meta["eid"].map(L).fillna(1).values, sw)
    elif VARIANT == "window":
        y = (flood | nb_eid.notna().values).astype(int)
        tr = yr & (known | nb_eid.notna().values)
        w = np.sqrt((tr & (y == 0)).sum() / (tr & (y == 1)).sum())
        sw = np.where(y == 1, w, 1.0)
    for seed in range(lo, hi + 1):
        s = fit_anyday(train_years, va, seed) if VARIANT == "anyday" else fit_weighted(tr, va, y, sw, seed)
        parts.append(pd.DataFrame({"variant": VARIANT, "val": val_years[0], "seed": seed,
                                   "catchment": meta.loc[va, "catchment"].values,
                                   "date": meta.loc[va, "date"].values, "score": s}))
        print(VARIANT, SPLIT, val_years[0], "seed", seed, flush=True)
pd.concat(parts).to_csv(D + f"event_train_{SPLIT}_scores_{VARIANT}{TAG}_s{lo}-{hi}.csv", index=False)
