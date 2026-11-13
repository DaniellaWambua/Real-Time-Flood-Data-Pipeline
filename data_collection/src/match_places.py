import json
import re
import sys
import pandas as pd
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

# Ties place names in flood reports to catchments through wards (D12).
# Run from the project folder:
#   python data_collection/src/match_places.py            build shares, DesInventar candidates, worklist
#   python data_collection/src/match_places.py resolve    match the place_text filled in the worklist
P = "data_collection/data/"
WARDS = "db/reference/wards_nairobi_area.geojson"
OUT = P + "10_place_matching/"
CATCHMENTS = ["mathare", "nairobi", "ngong"]
SUPPORT, POSSIBLE = 0.5, 0.25  # share of a ward's area inside a catchment

# Estate and area names that are not ward names, mapped to the wards they cover
ALIASES = {
    "kibera": ["Laini Saba", "Lindi", "Makina", "Sarangombe", "Woodley/Kenyatta Golf"],
    "mathare": ["Mabatini", "Mlango Kubwa", "Hospital", "Huruma", "Kiamaiko", "Ngei", "Mathare North"],
    "cbd": ["Nairobi Central"],
    "city centre": ["Nairobi Central"],
    "city center": ["Nairobi Central"],
    "industrial area": ["Viwandani", "Landimawe"],
    "mukuru": ["Viwandani", "Kware", "Kwa Njenga", "Kwa Reuben"],
    "south c": ["South-C"],
    "eastleigh": ["Eastleigh North", "Eastleigh South"],
    "parklands": ["Parklands/Highridge"],
    "kariobangi": ["Kariobangi North", "Kariobangi South"],
    "dandora": ["Dandora Area I", "Dandora Area Ii", "Dandora Area Iii", "Dandora Area Iv"],
    "kayole": ["Kayole Central", "Kayole North", "Kayole South"],
    "umoja": ["Umoja I", "Umoja II"],
}
# Ward names that are also ordinary words or other places, matched only through ALIASES
NOT_DIRECT = {"Hospital", "Harambee", "California", "Utalii", "Airbase", "Pipeline", "Ngong",
              "Township (Kiambu)", "Township (Thika)", "Theta", "Mathare North"}


CATCH_SHAPES = {f["properties"]["catchment"]: make_valid(shape(f["geometry"]))
                for f in json.load(open(P + "05_spatial/processed/catchments.geojson"))["features"]}
WARD_SHAPES = {}
for _f in json.load(open(WARDS))["features"]:  # two features share a name (Mwiki), so join them
    _g = make_valid(shape(_f["geometry"]))
    _w = _f["properties"]["ward"]
    WARD_SHAPES[_w] = unary_union([WARD_SHAPES[_w], _g]) if _w in WARD_SHAPES else _g


def area_shares(geom):
    """Share of a shape's area inside each catchment."""
    return {c: round(geom.intersection(CATCH_SHAPES[c]).area / geom.area, 3) for c in CATCHMENTS}


def ward_shares():
    """Share of each ward's area inside each catchment."""
    return pd.DataFrame([{"ward": w, **area_shares(g)} for w, g in WARD_SHAPES.items()])


def gazetteer(shares):
    """Lower-case name -> wards, from ward names (each part of a split name) and ALIASES."""
    names = {}
    for w in shares["ward"]:
        if w in NOT_DIRECT:
            continue
        for part in [w] + (w.split("/") if "/" in w else []):
            names.setdefault(part.lower(), set()).add(w)
    for alias, wards in ALIASES.items():
        names.setdefault(alias, set()).update(wards)
    return names


def match(text, names, shares):
    """Places found in text, their wards and the catchments they support."""
    text = str(text or "").lower()
    found = {}
    for name in sorted(names, key=len, reverse=True):  # longest first, so 'mathare north' wins over 'mathare'
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text):
            found[name] = names[name]
            text = re.sub(rf"(?<![a-z]){re.escape(name)}(?![a-z])", " ", text)
    # a place covering several wards is judged on their combined area
    per_place = [area_shares(unary_union([WARD_SHAPES[w] for w in ws])) for ws in found.values()]
    best = {c: max((p[c] for p in per_place), default=0.0) for c in CATCHMENTS}
    supported = [c for c in CATCHMENTS if best[c] >= SUPPORT]
    possible = [c for c in CATCHMENTS if POSSIBLE <= best[c] < SUPPORT]
    decision = "matched" if supported else "possible" if possible else "outside catchments" if found else "no place found"
    return {"places": "; ".join(f"{n} -> {', '.join(sorted(ws))}" for n, ws in found.items()),
            "supported": ", ".join(supported), "possible": ", ".join(possible), "place_decision": decision,
            **{f"share_{c}": best[c] for c in CATCHMENTS}}


def current_labels():
    lab = pd.read_csv(P + "01_flood_labels/processed/daily_labelled_2015_2025_audited.csv", usecols=["catchment", "date", "label_status"])
    return lab.pivot(index="date", columns="catchment", values="label_status").add_prefix("label_")


def desinventar(names, shares, labels):
    d = pd.read_csv(P + "01_flood_labels/raw/desinventar/desinventar_nairobi_audited.csv")
    d = d[d["decision"] != "EXCLUDE"]
    m = pd.DataFrame([match(f"{r.location} {r.clean_location} {r.comments}", names, shares) for r in d.itertuples()], index=d.index)
    out = pd.concat([d[["serial", "date", "decision", "confidence", "clean_location"]], m], axis=1)
    return out.merge(labels, left_on="date", right_index=True, how="left")


def worklist(labels):
    """Days with a county-wide Groundsource report but no flood label in any catchment, to be checked against dated reports."""
    rep = pd.read_csv(P + "01_flood_labels/processed/groundsource_attribution.csv", parse_dates=["start_date", "end_date"])
    rep = rep[~rep["small"].astype(str).str.lower().isin(["true", "1"])]
    days = pd.Series([d.date().isoformat() for r in rep.itertuples()
                      for d in pd.date_range(r.start_date.normalize(), min(r.end_date.normalize(), r.start_date.normalize() + pd.Timedelta(days=4)))])
    counts = days.value_counts().rename("county_reports")
    w = labels.join(counts, how="inner")
    w = w[~(w[[f"label_{c}" for c in CATCHMENTS]] == "flood").any(axis=1)]
    w = w[~(w[[f"label_{c}" for c in CATCHMENTS]] == "unknown").all(axis=1)]
    for col in ["place_text", "source_name", "source_url", "checker", "date_checked"]:
        w[col] = ""
    return w.reset_index().rename(columns={"index": "date"})


def resolve(names, shares):
    w = pd.read_csv(OUT + "countywide_worklist.csv", dtype=str).fillna("")
    filled = w[w["place_text"].str.strip() != ""]
    m = pd.DataFrame([match(t, names, shares) for t in filled["place_text"]], index=filled.index)
    out = pd.concat([filled, m], axis=1)
    out.to_csv(OUT + "countywide_candidates.csv", index=False)
    print(f"{len(filled)} filled rows matched; decisions: {out['place_decision'].value_counts().to_dict()}")


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    shares = ward_shares()
    names = gazetteer(shares)
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        resolve(names, shares)
        sys.exit()
    shares.to_csv(OUT + "ward_catchment_shares.csv", index=False)
    labels = current_labels()
    des = desinventar(names, shares, labels)
    des.to_csv(OUT + "desinventar_candidates.csv", index=False)
    w = worklist(labels)
    if os.path.exists(OUT + "countywide_worklist.csv"):
        print("countywide_worklist.csv already exists, not overwritten (it may hold filled-in evidence)")
    else:
        w.to_csv(OUT + "countywide_worklist.csv", index=False)
    print(f"{len(shares)} wards; DesInventar {len(des)} rows: {des['place_decision'].value_counts().to_dict()}")
    print(f"worklist: {len(w)} days, by year {w['date'].str[:4].value_counts().sort_index().to_dict()}")
