import os, sys
import numpy as np, pandas as pd
import comparison_setup as cs

# Label audit comparison on the development folds only (decisions.md D8, D11).
# Each frozen D8 model is trained on one label set and scores every day of the validation years,
# so the scores can later be judged against either label set.
# Usage: audit_scores.py trees|lstm [dev|final]
# "final" refits on 2015-2023 and scores 2024-2025. That period was already seen (D9, D10), so it is a
# label sensitivity check of the test result, not a new unseen test.
D = "data_collection/data/08_model_ready/"
LABELS = {"original": D + "features_daily.csv", "audited": D + "features_daily_audited.csv"}
FAMILY = sys.argv[1] if len(sys.argv) > 1 else "trees"
SPLIT = sys.argv[2] if len(sys.argv) > 2 else "dev"
FOLDS = cs.DEV_FOLDS if SPLIT == "dev" else [cs.FINAL_FOLD]
# Optional robustness check: AUDIT_SEEDS="3,4,5,6,7" adds seeds beyond the three of D8, written to a separate file
EXTRA = os.environ.get("AUDIT_SEEDS")
if EXTRA:
    cs.SEEDS = [int(x) for x in EXTRA.split(",")]


def all_rows(path, which):
    """Every row of the validation years with the target label of this label set (may be unknown)."""
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"] = df["date"].dt.year
    col = "label_status" if which == "today" else "next_status"
    if which == "today":
        df["tdate"], df["teid"] = df["date"], df["event_id"]
    else:
        df["tdate"] = df["date"] + pd.Timedelta(days=1)
        df["teid"] = df.groupby("catchment")["event_id"].shift(-1)
    df["status"] = df[col]
    return df


parts = []
for train_set, path in LABELS.items():
    cs.PATH = path
    for which in ["today", "tomorrow"]:
        d = cs.load(which)
        full = all_rows(path, which)
        for train_years, val_years in FOLDS:
            tr = d["year"].isin(train_years).values
            vmask = full["year"].isin(val_years).values
            V = full.loc[vmask]
            val = "-".join(map(str, sorted({val_years[0], val_years[-1]})))
            if FAMILY == "trees":
                models = [("rule_rain_3d", 0, None)] + [(n, s, None) for n in cs.TREES for s in cs.SEEDS]
                for name, seed, _ in models:
                    if name == "rule_rain_3d":
                        s = V["rain_sum_3d"].values
                    else:
                        m = cs.build(name, seed)
                        m.fit(d.loc[tr, cs.FEATS], d.loc[tr, "y"])
                        s = m.predict_proba(V[cs.FEATS])[:, 1]
                    parts.append(pd.DataFrame({"train_labels": train_set, "target": which, "val": val, "model": name,
                                               "seed": seed, "catchment": V["catchment"].values,
                                               "date": V["date"].values, "score": np.round(s, 7)}))
            else:
                from lstm_common import fit_predict
                from sequences import make_windows
                X, meta = make_windows(path=path)
                rows = d[["catchment", "date", "y"]]
                meta = meta.merge(rows, on=["catchment", "date"], how="left")
                trw = (meta["year"].isin(list(train_years)) & meta["y"].notna()).values
                vaw = meta["year"].isin(val_years).values
                y = meta["y"].fillna(0).astype(int).values
                for seed in cs.SEEDS:
                    s = fit_predict(X, y, trw, vaw, seed, "weights")
                    parts.append(pd.DataFrame({"train_labels": train_set, "target": which, "val": val,
                                               "model": "lstm_raw", "seed": seed,
                                               "catchment": meta.loc[vaw, "catchment"].values,
                                               "date": meta.loc[vaw, "date"].values, "score": np.round(s, 7)}))
                    print(train_set, which, val, seed, flush=True)
            print(FAMILY, train_set, which, val, "train", int(tr.sum()), "floods", int(d.loc[tr, "y"].sum()), flush=True)

pd.concat(parts).to_csv(D + f"audit_{SPLIT}_scores_{FAMILY}{'_extra_seeds' if EXTRA else ''}.csv", index=False)
