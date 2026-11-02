import pandas as pd

d = "data_collection/data/02_weather/processed/"
ch = pd.read_csv(d + "chirps_daily_2004_2025.csv", parse_dates=["date"])
er = pd.read_csv(d + "era5land_daily_2004_2025.csv", parse_dates=["date"])
full = pd.date_range("2004-01-01", "2025-12-31")

for name, df in [("chirps", ch), ("era5land", er)]:
    print("\n==", name)
    print("missing values per column")
    print(df.isna().sum())
    print(df.describe().T[["min", "mean", "max"]])
    for c, g in df.groupby("catchment"):
        print(c, "missing days", len(full.difference(g["date"])), "duplicates", g["date"].duplicated().sum())