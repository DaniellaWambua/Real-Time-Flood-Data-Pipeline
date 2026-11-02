import geopandas as gpd
import pandas as pd

cand_path = "data_collection/data/01_flood_labels/processed/groundsource_candidates.parquet"
catch_path = "data_collection/data/05_spatial/processed/catchments.geojson"
out = "data_collection/data/01_flood_labels/processed/groundsource_attribution.csv"

cand = gpd.read_parquet(cand_path).to_crs(32737)
catch = gpd.read_file(catch_path).to_crs(32737)

cand["area_m2"] = cand.geometry.area
for _, c in catch.iterrows():
    inter = cand.geometry.intersection(c.geometry).area
    cand["frac_" + c["catchment"]] = inter / cand["area_m2"]

frac_cols = [c for c in cand.columns if c.startswith("frac_")]
cand["best"] = cand[frac_cols].idxmax(axis=1).str.replace("frac_", "")
cand["best_frac"] = cand[frac_cols].max(axis=1)
cand["small"] = cand["area_km2"] <= 25

table = pd.DataFrame(cand.drop(columns="geometry"))
table.to_csv(out, index=False)

assigned = table[table["small"] & (table["best_frac"] >= 0.5)]
print(len(assigned), "small events mostly inside one catchment")
print(assigned["best"].value_counts())
print(assigned["start_date"].str[:4].value_counts().sort_index())