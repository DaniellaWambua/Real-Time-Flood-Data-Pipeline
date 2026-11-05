import sys, os
import pandas as pd
from comparison_setup import load, FEATS, DEV_FOLDS, SEEDS, OUT
from tuning_common import configs, build_tree, fold_metrics, run_row, LSTM_VARIANTS

# Development-fold search for one model family. Usage: tune_dev.py <family> [tf threads]
# Appends one block of rows per setting, and skips settings already in the file, so it can resume.
family = sys.argv[1]
os.makedirs(f"{OUT}/tuning", exist_ok=True)
path = f"{OUT}/tuning/runs_{family}.csv"
done = set(pd.read_csv(path)["config_id"]) if os.path.exists(path) else set()
is_lstm = family.startswith("lstm")
if is_lstm:
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(int(sys.argv[2]) if len(sys.argv) > 2 else 2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    from lstm_common import load_windows, fit_predict_cfg
    inputs, mode = LSTM_VARIANTS[family]
    windows = {}
else:
    data = {which: load(which) for which in ["today", "tomorrow"]}

for cid, cfg in configs(family):
    if cid in done:
        continue
    rows = []
    for which in ["today", "tomorrow"]:
        if is_lstm:
            key = (which, cfg["window"])
            if key not in windows:
                windows[key] = load_windows(which, inputs, cfg["window"])
            X, d = windows[key]
            y = d["y"].values
        else:
            d = data[which]
        for train_years, val_years in DEV_FOLDS:
            tr = d["year"].isin(list(train_years)).values
            va = d["year"].isin(val_years).values
            g = d.loc[va, ["y", "catchment", "tdate", "teid"]].copy()
            for seed in ([0] if family == "rule" else SEEDS):
                if family == "rule":
                    g["score"] = d.loc[va, cfg["feature"]].values
                elif is_lstm:
                    g["score"] = fit_predict_cfg(X, y, tr, va, seed, mode, cfg)
                else:
                    m = build_tree(family, cfg, seed)
                    m.fit(d.loc[tr, FEATS], d.loc[tr, "y"])
                    g["score"] = m.predict_proba(d.loc[va, FEATS])[:, 1]
                val = "-".join(map(str, sorted({val_years[0], val_years[-1]})))
                rows.append(run_row(family, cid, cfg, which, val, seed, fold_metrics(g)))
    pd.DataFrame(rows).to_csv(path, mode="a", header=not os.path.exists(path), index=False)
    r = pd.DataFrame(rows)
    print(cid, cfg, "mean AP", round(r["ap"].mean(), 3), flush=True)
