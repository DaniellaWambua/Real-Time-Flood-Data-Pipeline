import json
import numpy as np, pandas as pd
from sequences import make_windows
from lstm_common import make_model

# Loads the saved model folder fresh and compares its 2024-2025 scores with the stored Chapter 5 scores
D = "data_collection/data/08_model_ready/"
M = "models/flood_lstm/"
cfg = json.load(open(M + "config.json"))
mu, sd = np.array(cfg["mean"]), np.array(cfg["std"])

X, meta = make_windows(path=D + cfg["labels"], t=cfg["window"])
va = meta["year"].isin([2024, 2025]).values
new = meta.loc[va, ["catchment", "date"]].reset_index(drop=True)
Xva = (X[va] - mu) / sd

old = pd.concat([pd.read_csv(D + f"audit_final_scores_lstm{x}.csv", parse_dates=["date"])
                 for x in ("", "_extra_seeds")])
old = old[(old["train_labels"] == "audited") & (old["target"] == "today")]

for seed in cfg["seeds"]:
    model = make_model(X.shape[2])
    model.load_weights(M + f"lstm_raw_seed{seed}.weights.h5")
    new[f"s{seed}"] = model.predict(Xva, verbose=0).ravel()
    o = new.merge(old[old["seed"] == seed][["catchment", "date", "score"]], on=["catchment", "date"])
    print("seed", seed, "rows", len(o), "max difference", round(float((o[f"s{seed}"] - o["score"]).abs().max()), 4))

new["mean"] = new[[f"s{s}" for s in cfg["seeds"]]].mean(axis=1)
print("days flagged at", cfg["threshold"], ":", int((new["mean"] >= cfg["threshold"]).sum()), "of", len(new))


# compare the 8-seed average with the stored one, and its AP on the audited labels
from sklearn.metrics import average_precision_score as ap
old_mean = old.groupby(["catchment", "date"])["score"].mean().rename("old_mean").reset_index()
new = new.merge(old_mean, on=["catchment", "date"])
print("seed 1 mean difference", round(float((new["s1"] - old[old["seed"] == 1].set_index(["catchment", "date"])
      .loc[list(zip(new["catchment"], new["date"])), "score"].values).__abs__().mean()), 4))
print("average max difference", round(float((new["mean"] - new["old_mean"]).abs().max()), 4))
t = new.merge(pd.read_csv(D + cfg["labels"], parse_dates=["date"])[["catchment", "date", "label_status"]],
              on=["catchment", "date"])
t = t[t["label_status"].isin(["flood", "no_flood"])]
y = (t["label_status"] == "flood").astype(int)
print("AP saved", round(ap(y, t["mean"]), 3), "AP stored", round(ap(y, t["old_mean"]), 3))
thr = cfg["threshold"]
print("days where the flag decision differs:", int(((t["mean"] >= thr) != (t["old_mean"] >= thr)).sum()))