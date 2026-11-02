import pandas as pd

path = "data_collection/data/01_flood_labels/processed/groundsource_attribution.csv"
out = "data_collection/data/01_flood_labels/processed/groundsource_clusters.csv"
GAP = 2

df = pd.read_csv(path)
df = df[df["small"] & (df["best_frac"] >= 0.5)].copy()
df["start"] = pd.to_datetime(df["start_date"])
df["end"] = pd.to_datetime(df["end_date"])

rows = []
for name, g in df.groupby("best"):
    g = g.sort_values("start")
    cluster_id = (g["start"].diff().dt.days.fillna(0) > GAP).cumsum()
    for cid, c in g.groupby(cluster_id):
        rows.append({
            "catchment": name,
            "first_date": c["start"].min().date(),
            "last_date": c["end"].max().date(),
            "modal_date": c["start"].mode().iloc[0].date(),
            "n_events": len(c),
        })

clusters = pd.DataFrame(rows).sort_values(["catchment", "first_date"])
clusters.to_csv(out, index=False)

print(clusters.groupby("catchment").size())
print(clusters[clusters["n_events"] >= 3].to_string(index=False))