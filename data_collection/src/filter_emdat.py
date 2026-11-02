import glob
import pandas as pd

path = glob.glob("data_collection/data/01_flood_labels/raw/emdat/*.xlsx")[0]
df = pd.read_excel(path)

print("Newest Last Update in file", df["Last Update"].max())

floods = df[df["Disaster Type"] == "Flood"]
print("Kenya floods", len(floods))

def has_nairobi(col):
    return floods[col].astype(str).str.contains("Nairobi", case=False, na=False)

floods = floods.assign(
    in_location=has_nairobi("Location"),
    in_admin=has_nairobi("Admin Units"),
    in_gadm=has_nairobi("GADM Admin Units"),
)

mask = (floods.in_location | floods.in_admin | floods.in_gadm) & (floods["Start Year"] >= 2004)
hit = floods[mask]
print("Nairobi floods from 2004", len(hit))

cols = ["DisNo.", "Start Year", "Start Month", "Start Day", "End Year", "End Month", "End Day",
        "Total Deaths", "in_location", "in_admin", "in_gadm"]
print(hit[cols].to_string())

for _, r in hit.iterrows():
    print()
    print(r["DisNo."], r["Start Year"], "Origin", r["Origin"])
    print(r["Location"])