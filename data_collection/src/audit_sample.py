import os
import numpy as np
import pandas as pd

# Label audit sample (D11). Reads only the files in ALLOWED.
P = "data_collection/data/"
ALLOWED = {
    "labels": P + "01_flood_labels/processed/daily_labelled_2015_2025.csv",
    "register": P + "01_flood_labels/processed/event_register.csv",
    "clusters": P + "01_flood_labels/processed/groundsource_clusters.csv",
    "reports": P + "01_flood_labels/processed/groundsource_attribution.csv",
    "features": P + "08_model_ready/features_daily.csv",
}
OUT = P + "09_label_audit/"
CATCHMENTS = ["mathare", "ngong", "nairobi"]
DAY = pd.Timedelta(days=1)
SEED = 42
PER_CELL = 40
BINS = [-np.inf, 10, 25, 40, np.inf]
STRATA = ["under 10", "10 to 25", "25 to 40", "40 or more"]
EVIDENCE = ["evidence_found", "source_type", "source_name", "source_url", "evidence_note", "checker", "date_checked"]


def read_allowed(path, **kw):
    if path not in ALLOWED.values():
        raise ValueError(f"not an allowed input: {path}")
    return pd.read_csv(path, **kw)


def period(year):
    return np.where(year <= 2019, "2015-2019", "2020-2025")


def weak_windows():
    """(catchment, date, reason) for days within 1 day of a 1 to 2 report cluster or an unassigned report."""
    rows = []
    cl = read_allowed(ALLOWED["clusters"], parse_dates=["first_date", "last_date"])
    for r in cl[cl["n_events"] <= 2].itertuples():
        cid = f"cluster GS-{r.catchment}-{r.first_date.date()} ({r.n_events} report{'s' if r.n_events > 1 else ''})"
        for d in pd.date_range(r.first_date - DAY, r.last_date + DAY):
            rows.append((r.catchment, d, cid))
    rep = read_allowed(ALLOWED["reports"], parse_dates=["start_date", "end_date"])
    rep = rep[~(rep["small"] & (rep["best_frac"] >= 0.5))]
    for r in rep.itertuples():
        end = r.end_date if pd.notna(r.end_date) else r.start_date
        for c in CATCHMENTS:
            if getattr(r, "frac_" + c) > 0:
                for d in pd.date_range(r.start_date - DAY, end + DAY):
                    rows.append((c, d, f"report {r.uuid}"))
    w = pd.DataFrame(rows, columns=["catchment", "date", "reason"])
    return w.groupby(["catchment", "date"])["reason"].agg(lambda s: "; ".join(sorted(set(s)))).reset_index()


def load_days():
    lab = read_allowed(ALLOWED["labels"], parse_dates=["date"])[["catchment", "date", "label_status", "event_id"]]
    feat = read_allowed(ALLOWED["features"], parse_dates=["date"])[["catchment", "date", "rain_sum_3d", "label_status"]]
    d = lab.merge(feat, on=["catchment", "date"], suffixes=("", "_features"), validate="one_to_one")
    assert len(d) == len(lab) == len(feat), "labels and features do not cover the same days"
    assert (d["label_status"] == d["label_status_features"]).all(), "labels differ between the two tables"
    assert d["rain_sum_3d"].notna().all()
    d = d.drop(columns="label_status_features")
    d["year"] = d["date"].dt.year
    d["period"] = period(d["year"])
    d["rain_stratum"] = pd.cut(d["rain_sum_3d"], BINS, right=False, labels=STRATA).astype(str)
    return d


def select(d):
    a = d[d["label_status"] == "flood"].assign(group="A")
    a["reason"] = "flood label " + a["event_id"]
    nf = d[d["label_status"] == "no_flood"].merge(weak_windows(), on=["catchment", "date"], how="left")
    b = nf[nf["reason"].notna()].assign(group="B")
    pool = nf[nf["reason"].isna()].sort_values(["period", "rain_stratum", "catchment", "date"])
    rng = np.random.default_rng(SEED)
    parts = []
    for (p, s), cell in pool.groupby(["period", "rain_stratum"], sort=True):
        parts.append(cell.sample(n=min(PER_CELL, len(cell)), random_state=rng))
    c = pd.concat(parts).assign(group="C")
    c["reason"] = "random sample, rain " + c["rain_stratum"] + " mm, " + c["period"]
    days = pd.concat([a, b, c]).sort_values(["group", "catchment", "date"]).reset_index(drop=True)
    assert not days.duplicated(["catchment", "date"]).any(), "a day is in more than one group"
    return days


def make_units(days):
    new = ((days["group"] != days["group"].shift()) | (days["catchment"] != days["catchment"].shift())
           | (days["date"] - days["date"].shift() != DAY))
    days["unit_id"] = (days["group"] + new.groupby(days["group"]).cumsum().map("{:04d}".format))
    units = days.groupby("unit_id", sort=False).agg(
        catchment=("catchment", "first"), start_date=("date", "min"), end_date=("date", "max"),
        n_days=("date", "size"), group=("group", "first"), rain_sum_3d_max=("rain_sum_3d", "max"),
        reason=("reason", lambda s: "; ".join(dict.fromkeys(x for v in s for x in v.split("; "))))).reset_index()
    units["rain_sum_3d_max"] = units["rain_sum_3d_max"].round(1)
    return units.assign(**{c: "" for c in EVIDENCE})


def main():
    days = select(load_days())
    units = make_units(days)
    cols = ["unit_id", "group", "catchment", "date", "year", "period", "rain_sum_3d", "rain_stratum",
            "label_status", "event_id", "reason"]
    out = days[cols].assign(rain_sum_3d=days["rain_sum_3d"].round(1), **{c: "" for c in EVIDENCE})
    os.makedirs(OUT, exist_ok=True)
    out.to_csv(OUT + "audit_days.csv", index=False)
    units.to_csv(OUT + "audit_units.csv", index=False)

    pd.set_option("display.width", 200)
    print("days and units per group")
    print(pd.DataFrame({"days": days.groupby("group").size(), "units": units.groupby("group").size()}).to_string())
    for col in ["rain_stratum", "period", "catchment", "year"]:
        print(f"\ndays per group and {col}")
        print(pd.crosstab(days["group"], days[col], margins=True).to_string())


if __name__ == "__main__":
    main()
