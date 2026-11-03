import pandas as pd

df = pd.read_csv("data_collection/data/08_model_ready/features_daily.csv", parse_dates=["date"])

def fold(y):
    return "train" if y <= 2021 else ("val" if y <= 2023 else "test")

df["year"] = df["date"].dt.year
df["fold"] = df["year"].map(fold)
f = df[df["label_status"] == "flood"]

print("rows per fold")
print(df.groupby("fold").size())
print("\nflood days and events per fold and catchment")
print(f.groupby(["fold", "catchment"]).agg(flood_days=("date", "size"), events=("event_id", "nunique")))
print("\nflood days per year")
print(f.groupby("year").size())
print("\nevents spanning more than one fold:", (f.groupby("event_id")["fold"].nunique() > 1).sum())