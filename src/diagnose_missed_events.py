"""List which cross-validation flood events a selected model misses, and why.

Reads the saved out-of-fold predictions from src.model_selection (no
TensorFlow needed). For every labelled flood event (consecutive labelled
days in one catchment) it reports whether the model flagged it, how close
the nearest flag was, and how far the rainfall peak sits from the labelled
dates. It also shows how many "false alarms" are really near-misses.

Run from the repository root:
    python -m src.diagnose_missed_events --dataset v9 --model lstm
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.config import CATCHMENTS, RAW_DATA_DIR, TEST_START_YEAR

MAX_WINDOW = 30    # same as model_selection, so days line up with the predictions
CV_FIRST_YEAR = 2015
TOL = 3            # same tolerance as model_selection


def build_meta(csv_path):
    df = pd.read_csv(csv_path, parse_dates=["date"])
    parts = []
    for c in CATCHMENTS:
        g = df[df["catchment"] == c].sort_values("date").reset_index(drop=True)
        parts.append(g.iloc[MAX_WINDOW - 1:])
    meta = pd.concat(parts, ignore_index=True)
    meta["year"] = meta["date"].dt.year
    return meta


def events_of(group):
    d = group.loc[group["flood_event"] == 1, "date"]
    if d.empty:
        return []
    run = (d.diff() != pd.Timedelta(days=1)).cumsum()
    return [(r.min(), r.max()) for _, r in d.groupby(run)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="v9")
    ap.add_argument("--model", default="lstm")
    ap.add_argument("--part", default="cv", choices=["cv", "test"])
    a = ap.parse_args()

    rep = RAW_DATA_DIR.parent.parent / "reports" / "model_selection" / a.dataset
    preds = np.load(rep / f"{a.model}_predictions.npz")
    summary = json.load(open(rep / "summary.json"))
    name = next(k for k in summary["models"] if k.lower().replace(" ", "_").replace("+", "and") == a.model)
    thr = summary["models"][name]["threshold"]

    meta = build_meta(RAW_DATA_DIR / f"Dataset_labels_{a.dataset}.csv")
    is_test = (meta["year"] >= TEST_START_YEAR).to_numpy()
    if a.part == "cv":
        sel = ~is_test & (meta["year"] >= CV_FIRST_YEAR).to_numpy()
        probs = preds["oof"]
    else:
        sel, probs = is_test, preds["test"]
    m = meta[sel].reset_index(drop=True)
    assert len(m) == len(probs), f"alignment failed {len(m)} vs {len(probs)}; was this model run on {a.dataset}?"
    m["prob"], m["flag"] = probs, (probs >= thr).astype(int)

    tol = pd.Timedelta(days=TOL)
    rows = []
    for c, g in m.groupby("catchment"):
        g = g.set_index("date", drop=False)
        for s, e in events_of(g):
            win = g.loc[s - tol:e + tol]
            flagged = win[win["flag"] == 1]
            around = g.loc[s - pd.Timedelta(days=10):e + pd.Timedelta(days=10)]
            peak = around["rainfall_3day"].idxmax()
            rows.append(dict(
                catchment=c, start=s.date(), end=e.date(), days=(e - s).days + 1,
                caught=bool(len(flagged)), flagged_days=int(win["flag"].sum()),
                max_prob=round(float(win["prob"].max()), 3),
                rain_peak=peak.date(), peak_offset_days=int((peak - s).days),
                peak_outside_label=bool(peak < s - tol or peak > e + tol),
                peak_3day_mm=round(float(around["rainfall_3day"].max()), 1),
            ))
    ev = pd.DataFrame(rows)

    # False alarms: flagged days with no labelled flood day within TOL days.
    near = far = 0
    for c, g in m.groupby("catchment"):
        fl = g.loc[g["flood_event"] == 1, "date"]
        for d in g.loc[g["flag"] == 1, "date"]:
            if (fl - d).abs().le(tol).any() if len(fl) else False:
                near += 1
            else:
                far += 1

    out = rep / f"missed_events_{a.model}_{a.part}.csv"
    ev.to_csv(out, index=False)
    pd.set_option("display.width", 200)
    print(f"\n{a.dataset} / {name} / {a.part}, threshold {thr:.3f}\n")
    print(ev.to_string(index=False))
    print("\nBy catchment")
    print(ev.groupby("catchment").agg(events=("caught", "size"), caught=("caught", "sum"),
          median_days=("days", "median"), peak_outside=("peak_outside_label", "sum")).to_string())
    print(f"\nEvents caught {int(ev.caught.sum())}/{len(ev)}; rainfall peak outside labelled dates "
          f"(+/-{TOL}d) in {int(ev.peak_outside_label.sum())} events")
    print(f"Flagged days {near + far}; within {TOL}d of a labelled flood {near}; true false alarms {far}")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
