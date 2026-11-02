import pandas as pd

cl_path = "data_collection/data/01_flood_labels/processed/groundsource_clusters.csv"
em_path = "data_collection/data/01_flood_labels/processed/emdat_nairobi_events.csv"
PAD = 3

cl = pd.read_csv(cl_path, parse_dates=["first_date", "last_date", "modal_date"])
em = pd.read_csv(em_path)

em["start"] = pd.to_datetime(dict(year=em["Start Year"], month=em["Start Month"].astype(int), day=em["Start Day"].astype(int)))
em["end"] = pd.to_datetime(dict(year=em["End Year"], month=em["End Month"].astype(int), day=em["End Day"].astype(int)))
em = em[(em["end"] - em["start"]).dt.days <= 30]

def match(row):
    pad = pd.Timedelta(days=PAD)
    ok = em[(em["start"] - pad <= row["last_date"]) & (em["end"] + pad >= row["first_date"])]
    return ", ".join(ok["DisNo."])

cl["emdat_match"] = cl.apply(match, axis=1)
big = cl[cl["n_events"] >= 3]

print(len(em), "short EM-DAT windows used")
print(big.groupby("catchment")["emdat_match"].apply(lambda s: (s != "").sum()))
print(big[big["emdat_match"] != ""].to_string(index=False))