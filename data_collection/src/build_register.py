import pandas as pd

cl_path = "data_collection/data/01_flood_labels/processed/groundsource_clusters.csv"
em_path = "data_collection/data/01_flood_labels/processed/emdat_nairobi_events.csv"
out = "data_collection/data/01_flood_labels/processed/event_register.csv"
PAD = pd.Timedelta(days=3)

cl = pd.read_csv(cl_path, parse_dates=["first_date", "last_date", "modal_date"])
em = pd.read_csv(em_path)

em["start"] = pd.to_datetime(dict(year=em["Start Year"], month=em["Start Month"].astype(int), day=em["Start Day"].astype(int)))
em["end"] = pd.to_datetime(dict(year=em["End Year"], month=em["End Month"].astype(int), day=em["End Day"].astype(int)))
em = em[em["end"] < "2026-01-01"].copy()
em["days"] = (em["end"] - em["start"]).dt.days

cl = cl[(cl["n_events"] >= 3) & (cl["first_date"] >= "2015-01-01")].copy()

def em_ids(row):
    ok = em[(em["days"] <= 30) & (em["start"] - PAD <= row["last_date"]) & (em["end"] + PAD >= row["first_date"])]
    return ", ".join(ok["DisNo."])

cl["emdat"] = cl.apply(em_ids, axis=1)

rows = []
for _, r in cl.iterrows():
    wide = (r["last_date"] - r["first_date"]).days > 7
    rows.append({
        "event_id": f"GS-{r['catchment']}-{r['first_date'].date()}",
        "catchment": r["catchment"],
        "spatial_level": "catchment",
        "place_text": f"{r['n_events']} news-derived reports",
        "onset_date": r["first_date"].date(),
        "peak_date": r["modal_date"].date(),
        "end_date": r["last_date"].date(),
        "date_precision": "approximate" if wide else "day",
        "evidence_type": "news-derived",
        "source": "Groundsource v1",
        "source_ref": "groundsource_clusters.csv",
        "confidence": "High" if r["emdat"] else "Medium",
        "notes": ("EM-DAT " + r["emdat"]) if r["emdat"] else "",
    })

for _, e in em.iterrows():
    seen = cl[(cl["first_date"] <= e["end"] + PAD) & (cl["last_date"] >= e["start"] - PAD)]
    corroborated = e["days"] <= 30 and len(seen) > 0
    only = str(e["Location"]).strip() == "Nairobi"
    rows.append({
        "event_id": f"EMDAT-{e['DisNo.']}",
        "catchment": "unassigned",
        "spatial_level": "county",
        "place_text": "Nairobi only" if only else "Nairobi among other listed regions",
        "onset_date": e["start"].date(),
        "peak_date": "",
        "end_date": e["end"].date(),
        "date_precision": "window",
        "evidence_type": "disaster database",
        "source": "EM-DAT",
        "source_ref": e["DisNo."],
        "confidence": "High" if corroborated else "Medium",
        "notes": "",
    })

register = pd.DataFrame(rows).sort_values(["onset_date", "catchment"])
register.to_csv(out, index=False)
print(len(register), "rows")
print(register.groupby(["source", "catchment", "confidence"]).size())