import pandas as pd

D = "data_collection/data/"
reg = pd.read_csv(D + "01_flood_labels/processed/event_register.csv",
                  parse_dates=["onset_date", "peak_date", "end_date"])
ch = pd.read_csv(D + "02_weather/processed/chirps_daily_2004_2025.csv", parse_dates=["date"])
er = pd.read_csv(D + "02_weather/processed/era5land_daily_2004_2025.csv", parse_dates=["date"])

df = ch.merge(er, on=["catchment", "date"], how="inner")
df = df[df["date"] >= "2015-01-01"].copy()
df["label_status"] = "no_flood"
df["event_id"] = ""
BUFFER = pd.Timedelta(days=2)
ONE = pd.Timedelta(days=1)

def window(catchment, a, b):
    m = (df["date"] >= a) & (df["date"] <= b)
    return m if catchment is None else m & (df["catchment"] == catchment)

gs = reg[reg["source"] == "Groundsource v1"]
em = reg[(reg["source"] == "EM-DAT") & ((reg["end_date"] - reg["onset_date"]).dt.days <= 30)]

for _, r in em.iterrows():
    df.loc[window(None, r["onset_date"], r["end_date"]), "label_status"] = "unknown"

spans = []
for _, r in gs.iterrows():
    if r["date_precision"] == "day":
        a, b = r["onset_date"], r["end_date"]
    else:
        a, b = r["peak_date"] - ONE, r["peak_date"] + ONE
        df.loc[window(r["catchment"], r["onset_date"], r["end_date"]), "label_status"] = "unknown"
    spans.append((r["catchment"], a, b, r["event_id"]))

for c, a, b, eid in spans:
    m = window(c, a - BUFFER, b + BUFFER) & (df["label_status"] == "no_flood")
    df.loc[m, "label_status"] = "unknown"

for c, a, b, eid in spans:
    m = window(c, a, b)
    df.loc[m, "label_status"] = "flood"
    df.loc[m, "event_id"] = eid

df = df.sort_values(["catchment", "date"])
df.to_csv(D + "01_flood_labels/processed/daily_labelled_2015_2025.csv", index=False)
print(len(df), "rows")
print(df.groupby(["catchment", "label_status"]).size())