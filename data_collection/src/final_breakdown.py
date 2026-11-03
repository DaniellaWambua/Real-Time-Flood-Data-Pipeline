import pandas as pd
from sklearn.metrics import average_precision_score
from comparison_setup import OUT

# Final test scores split by catchment and by year (decisions.md D5), mean of seeds
DAY = pd.Timedelta(days=1)
sc = pd.concat([pd.read_csv(f"{OUT}/final_scores_{k}.csv", parse_dates=["date", "tdate"]) for k in ["trees", "lstm"]])
rows = []
for (which, model, seed), g in sc.groupby(["target", "model", "seed"]):
    alarms = g[g["score"] >= g["score"].quantile(0.95)]
    ev = g[g["y"] == 1].groupby("teid").agg(catchment=("catchment", "first"),
                                            start=("tdate", "min"), end=("tdate", "max"))
    ev["hit"] = [((alarms["catchment"] == e.catchment) & (alarms["tdate"] >= e.start - DAY) &
                  (alarms["tdate"] <= e.end + DAY)).any() for e in ev.itertuples()]
    ev["year"] = ev["start"].dt.year
    for by in ["catchment", "year"]:
        key = g[by] if by == "catchment" else g["tdate"].dt.year
        for part, gp in g.groupby(key):
            e = ev[ev[by] == part]
            rows.append({"target": which, "model": model, "seed": seed, "split_by": by, "part": part,
                         "days": len(gp), "flood_days": int(gp["y"].sum()), "base_rate": gp["y"].mean(),
                         "avg_precision": average_precision_score(gp["y"], gp["score"]),
                         "events": len(e), "event_recall_5pct": e["hit"].mean()})

res = pd.DataFrame(rows).groupby(["target", "split_by", "part", "model"], sort=False).mean(numeric_only=True)
res = res.drop(columns="seed").reset_index()
res["ap_lift"] = res["avg_precision"] / res["base_rate"]
res = res.round(3)
print(res.to_string(index=False))
res.to_csv(f"{OUT}/comparison_final_breakdown.csv", index=False)
