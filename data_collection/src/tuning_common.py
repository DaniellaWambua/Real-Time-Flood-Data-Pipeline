import itertools, json
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier

# Search spaces for the development-fold tuning run (decisions.md D10). Setting 00 is always the frozen D8 setting.
DAY = pd.Timedelta(days=1)
RULE_FEATS = ["rain_sum_3d", "rain_mm", "rain_sum_7d", "rain_sum_14d", "api",
              "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5", "rain_anom_7d"]
FOREST_GRID = {"n_estimators": [300, 600], "min_samples_leaf": [5, 1, 3, 10, 20],
               "max_features": ["sqrt", 0.3, 0.5], "max_depth": [None, 8],
               "class_weight": ["balanced_subsample", "balanced"]}
BOOST_GRID = {"max_depth": [3, 2, 4, 6], "learning_rate": [0.05, 0.02, 0.1], "max_iter": [200, 100, 400],
              "l2_regularization": [0.0, 1.0], "min_samples_leaf": [20, 50]}
LSTM_GRID = {"units": [32, 16, 64], "layers": [1, 2], "dropout": [0.3, 0.1, 0.5], "lr": [1e-3, 3e-4, 3e-3],
             "epochs": [15, 10, 30], "window": [14, 7, 30], "batch": [64, 32, 128], "cw_power": [0.5, 1.0]}
LSTM_VARIANTS = {"lstm_raw": ("raw", "weights"), "lstm_log": ("log", "weights"), "lstm_batches": ("raw", "batches")}
N_TREE, N_LSTM = 30, 14


def sample(grid, n, seed):
    """The first value of every list is the frozen setting; it is kept as setting 00, the rest are a random draw."""
    keys = list(grid)
    default = {k: v[0] for k, v in grid.items()}
    combos = [dict(zip(keys, c)) for c in itertools.product(*grid.values())]
    combos = [c for c in combos if c != default]
    idx = np.random.default_rng(seed).choice(len(combos), size=n - 1, replace=False)
    return [default] + [combos[i] for i in sorted(idx)]


def configs(family):
    if family == "rule":
        cfgs = [{"feature": f} for f in RULE_FEATS]
    elif family in ("forest", "extra_trees"):
        cfgs = sample(FOREST_GRID, N_TREE, 1)
    elif family == "boosting":
        cfgs = sample(BOOST_GRID, N_TREE, 2)
    else:
        grid = dict(LSTM_GRID)
        if LSTM_VARIANTS[family][1] == "batches":
            grid.pop("cw_power")
        cfgs = sample(grid, N_LSTM, 3)
    return [(f"{family}_{i:02d}", c) for i, c in enumerate(cfgs)]


def build_tree(family, cfg, seed):
    if family == "boosting":
        return HistGradientBoostingClassifier(class_weight="balanced", random_state=seed, **cfg)
    cls = RandomForestClassifier if family == "forest" else ExtraTreesClassifier
    return cls(random_state=seed, n_jobs=2, **cfg)


def fold_metrics(g):
    """g has y, score, catchment, tdate, teid for one fold. Alarm rule as in event_eval.py at a 5% share."""
    y, s = g["y"].values, g["score"].values
    o = np.argsort(-s, kind="mergesort")
    ys, ss = y[o], s[o]
    last = np.r_[np.diff(ss) != 0, True]
    tp = np.cumsum(ys)[last]
    ap = np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(ys) + 1)[last])
    k = max(1, int(len(y) * 0.05))
    alarms = g[g["score"] >= g["score"].quantile(0.95)]
    ev = g[g["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                            start=("tdate", "min"), end=("tdate", "max"))
    det = sum(((alarms["catchment"] == e.catchment) & (alarms["tdate"] >= e.start - DAY) &
               (alarms["tdate"] <= e.end + DAY)).any() for e in ev.itertuples())
    return {"days": len(y), "floods": int(y.sum()), "ap": ap, "top5_hits": int(ys[:k].sum()),
            "events": len(ev), "det5": int(det)}


def run_row(family, cid, cfg, which, val, seed, m):
    return {"family": family, "config_id": cid, "config": json.dumps(cfg), "target": which,
            "val": val, "seed": seed, **m}
