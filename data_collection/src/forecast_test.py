import json
import sys
import numpy as np
import pandas as pd

# Forecast-driven early warning test (decisions.md, real-time design). Would the saved models have warned of
# the 2024-2025 floods in time if they had been fed only what a live system has on the day, instead of
# CHIRPS (about 42 days late) and ERA5-Land (about 8 days late)?
#
# Inputs a live system has: IMERG (about 1 day late), and Open-Meteo forecast models
# (fetch_forecast_archive.py): lead 0 is the models' own estimate of the day, lead 1 and lead 2 the forecast
# for the day made one and two days earlier.
#
# Matching: Open-Meteo's values are put on the scale the models were trained on with one least-squares line
# per catchment and feature (through the origin for rainfall), fitted on 2022-2023 only, before the test
# years, against ERA5-Land, IMERG and CHIRPS. No labels are used for this, and nothing is fitted on 2024-2025.
#
# Scenarios, for each target day T in 2024-2025 (issue = the day the score could have been sent):
#   archive  the models' published test inputs, for reference (issued about 8 or 42 days after T)
#   now      days up to T: IMERG + Open-Meteo lead 0 (issued T+1; no waiting for ERA5-Land or CHIRPS)
#   lead1    issued at the end of T-1: days up to T-2 as in now, T-1 from Open-Meteo lead 0 (IMERG not
#            in yet, so its features come from the model's hourly rain), T from the lead 1 forecast
#   lead2    issued at the end of T-2: T-1 from lead 1 and T from lead 2 forecasts, the rest as above
# Models: fast (no CHIRPS, threshold 0.663) and full (v2, threshold 0.528; CHIRPS replaced by the matched
# Open-Meteo rainfall outside the archive scenario). Thresholds are the ones set on the development years.
# The forecast rain rule (50 mm in a day) is scored on the same forecasts for comparison.
# Usage: forecast_test.py   (from the project folder; needs TensorFlow and the Open-Meteo archive file)
D = "data_collection/data/"
OM = D + "02_weather/processed/openmeteo_forecast_archive_2022_2025.csv"
FEATURES = D + "08_model_ready/features_daily_audited.csv"
OUT = D + "08_model_ready/"
DAY = pd.Timedelta(days=1)
TEST = (pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31"))
CAL = (pd.Timestamp("2022-01-01"), pd.Timestamp("2023-12-31"))
ERA = ["era5_rain_mm", "temp_c", "dewpoint_depression", "pressure_hpa", "soil_1", "soil_2"]
IMERG = {"imerg_max_rate": "fc_max_rate", "imerg_total_mm": "fc_total_mm", "imerg_hours_ge5": "fc_hours_ge5"}
THROUGH_ORIGIN = {"era5_rain_mm", "rain_mm", "imerg_max_rate", "imerg_total_mm", "imerg_hours_ge5"}
CATCHMENTS = ["ngong", "mathare", "nairobi"]
WINDOW = 14

feat = pd.read_csv(FEATURES, parse_dates=["date"]).set_index(["catchment", "date"]).sort_index()
om = pd.read_csv(OM, parse_dates=["date"])
om = {lead: g.drop(columns=["lead"]).set_index(["catchment", "date"]).sort_index() for lead, g in om.groupby("lead")}
FEAT = {k: r for k, r in zip(feat.index, feat.to_dict("records"))}  # fast lookups
OMD = {lead: {k: r for k, r in zip(t.index, t.to_dict("records"))} for lead, t in om.items()}


# 1. matching on 2022-2023
def fit(x, y, origin):
    ok = x.notna() & y.notna()
    x, y = x[ok].values, y[ok].values
    if origin:
        b = float((x * y).sum() / (x * x).sum())
        a = 0.0
    else:
        b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return float(a), float(b), float(r2), int(ok.sum())


pairs = {f: f for f in ERA} | {"rain_mm": "era5_rain_mm"} | {k: v for k, v in IMERG.items()}
cal_rows, coef = [], {}
for c in CATCHMENTS:
    f_c = feat.loc[c].loc[CAL[0]:CAL[1]]
    o_c = om[0].loc[c].loc[CAL[0]:CAL[1]]
    both = f_c.join(o_c, rsuffix="_om", how="inner")
    for target, source in pairs.items():
        x = both[source + "_om"] if source in f_c.columns else both[source]
        a, b, r2, n = fit(x, both[target], target in THROUGH_ORIGIN)
        coef[(c, target)] = (a, b)
        cal_rows.append({"catchment": c, "feature": target, "from": source, "intercept": a, "slope": b, "r2": r2, "days": n})
cal = pd.DataFrame(cal_rows)
cal.to_csv(OUT + "forecast_test_matching.csv", index=False)
print("matching on 2022-2023 (R squared, mean over catchments):")
print(cal.groupby("feature")["r2"].mean().round(2).to_string())


def matched(c, day, lead, imerg_from_forecast):
    """One day's inputs for catchment c from Open-Meteo at this lead, on the training scale, or None."""
    r = OMD.get(lead, {}).get((c, day))
    if r is None:
        return None
    out = {}
    for target in ERA + ["rain_mm"]:
        a, b = coef[(c, target)]
        out[target] = a + b * r["era5_rain_mm" if target == "rain_mm" else target]
    if imerg_from_forecast:
        for target, source in IMERG.items():
            a, b = coef[(c, target)]
            out[target] = a + b * r[source]
    for k in THROUGH_ORIGIN:
        if k in out:
            out[k] = max(out[k], 0.0)
    return None if any(pd.isna(v) for v in out.values()) else out


def observed(c, day):
    """A day as the archive scenario has it (the model's published inputs)."""
    return FEAT.get((c, day))


def day_inputs(scenario, c, day, target):
    """Inputs for one day of the window ending on target, as available at the scenario's issue time."""
    base = observed(c, day)
    if base is None:
        return None
    if scenario == "archive":
        return base
    lead_of = {"now": {}, "lead1": {target - DAY: 0, target: 1},
               "lead2": {target - 2 * DAY: 0, target - DAY: 1, target: 2}}[scenario]
    if day in lead_of:  # not observed yet at issue time: all from the forecast
        m = matched(c, day, lead_of[day], imerg_from_forecast=True)
    else:  # observed: real IMERG, Open-Meteo lead 0 in place of ERA5-Land and CHIRPS
        m = matched(c, day, 0, imerg_from_forecast=False)
    if m is None:
        return None
    return {**base, **m}


def windows(scenario, cfg):
    rows, xs = [], []
    for c in CATCHMENTS:
        for target in pd.date_range(*TEST):
            days = [target - k * DAY for k in range(WINDOW - 1, -1, -1)]
            vals = [day_inputs(scenario, c, d, target) for d in days]
            if any(v is None for v in vals):
                continue
            x = []
            for d, v in zip(days, vals):
                v = dict(v, month_sin=np.sin(2 * np.pi * d.month / 12), month_cos=np.cos(2 * np.pi * d.month / 12))
                x.append([1.0 if f == f"is_{c}" else 0.0 if f.startswith("is_") else v[f] for f in cfg["features"]])
            xs.append(x)
            issue = {"archive": target, "now": target + DAY, "lead1": target - DAY, "lead2": target - 2 * DAY}[scenario]
            rows.append({"catchment": c, "date": target, "issued": issue})
    return np.array(xs, dtype="float32"), pd.DataFrame(rows)


def score(kind, scenario):
    import tensorflow as tf
    sys.path.insert(0, "data_collection/src")
    from lstm_common import make_model
    cfg = json.load(open(f"models/{'flood_lstm' if kind == 'full' else 'flood_lstm_fast'}/config.json"))
    X, meta = windows(scenario, cfg)
    X = (X - np.array(cfg["mean"])) / np.array(cfg["std"])
    s = []
    for seed in cfg["seeds"]:
        m = make_model(X.shape[2])
        m.load_weights(f"models/{'flood_lstm' if kind == 'full' else 'flood_lstm_fast'}/lstm_raw_seed{seed}.weights.h5")
        s.append(m.predict(X.astype("float32"), verbose=0).ravel())
    meta["score"] = np.mean(s, axis=0)
    if scenario == "archive":  # the published inputs arrive about 8 (fast) or 42 (full) days after the day
        meta["issued"] = meta["date"] + DAY * (8 if kind == "fast" else 42)
    return meta, cfg["threshold"]


# 3. evaluation, as event_evaluate.py, plus how early each detected event was warned
labels = feat.reset_index()[["catchment", "date", "label_status", "event_id"]]
labels = labels[(labels["date"] >= TEST[0]) & (labels["date"] <= TEST[1])]
events = (labels[labels["label_status"] == "flood"].groupby("event_id")
          .agg(catchment=("catchment", "first"), start=("date", "min"), end=("date", "max")))


def ap(y, s):
    o = np.argsort(-s, kind="mergesort")
    y, s = y[o], s[o]
    last = np.r_[np.diff(s) != 0, True]
    tp = np.cumsum(y)[last]
    return float(np.sum(np.diff(np.r_[0, tp / tp[-1]]) * tp / np.arange(1, len(y) + 1)[last])) if tp[-1] else 0.0


def evaluate(meta, thr, name):
    m = meta.merge(labels, on=["catchment", "date"], how="left")
    known = m[m["label_status"].isin(["flood", "no_flood"])]
    y, s = known["label_status"].eq("flood").values, known["score"].values
    a = s >= thr
    tp, fp, fn = int((a & y).sum()), int((a & ~y).sum()), int((~a & y).sum())
    alarms = m[m["score"] >= thr]
    det = early = 0
    for e in events.itertuples():
        hit = alarms[(alarms["catchment"] == e.catchment) & (alarms["date"] >= e.start - DAY) & (alarms["date"] <= e.end + DAY)]
        if len(hit):
            det += 1
            early += bool((hit["issued"] < e.start).any())  # a warning sent before the flood's first day
    eps = false_eps = 0
    for c, x in alarms.sort_values("date").groupby("catchment"):
        ev = events[events["catchment"] == c]
        for _, ep in x.groupby((x["date"].diff() != DAY).cumsum()):
            eps += 1
            false_eps += not ((ev["start"] - DAY <= ep["date"].max()) & (ev["end"] + DAY >= ep["date"].min())).any()
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    er = det / len(events)
    ep_p = (eps - false_eps) / eps if eps else 0.0
    return {"scenario": name, "days_scored": len(m), "ap": ap(y.astype(int), s), "precision": p, "recall": r,
            "f1": 2 * p * r / (p + r) if p + r else 0.0, "events": len(events), "detected": det,
            "warned_before_start": early, "event_recall": er, "episode_precision": ep_p,
            "event_f1": 2 * ep_p * er / (ep_p + er) if ep_p + er else 0.0,
            "false_episodes_per_catchment_year": false_eps / 6}


results = []
for kind in ("fast", "full"):
    for scenario in ("archive", "now", "lead1", "lead2"):
        meta, thr = score(kind, scenario)
        meta.assign(model=kind, scenario=scenario).to_csv(OUT + f"forecast_test_scores_{kind}_{scenario}.csv", index=False)
        results.append({"model": kind, **evaluate(meta, thr, scenario)})
        print(kind, scenario, "scored", len(meta), flush=True)

# the forecast rain rule: 50 mm in a day on the catchment-average forecast, issued as for each lead
for lead, name in ((0, "now"), (1, "lead1"), (2, "lead2")):
    r = om[lead].reset_index()
    r = r[(r["date"] >= TEST[0]) & (r["date"] <= TEST[1])]
    meta = pd.DataFrame({"catchment": r["catchment"], "date": r["date"], "score": r["era5_rain_mm"],
                         "issued": r["date"] + DAY * (1 if lead == 0 else -lead)})
    results.append({"model": "rain_rule_50mm", **evaluate(meta, 50.0, name)})

res = pd.DataFrame(results)
res.to_csv(OUT + "forecast_test_results.csv", index=False)
print(res.round(3).to_string(index=False))
