import sys
import pandas as pd

# Applies audited label corrections (D11) to a copy of the daily labelled table. The original is never written.
# Usage: apply_corrections.py [corrections_csv] [output_csv]
P = "data_collection/data/"
ORIGINAL = P + "01_flood_labels/processed/daily_labelled_2015_2025.csv"
CORR = sys.argv[1] if len(sys.argv) > 1 else P + "09_label_audit/label_corrections.csv"
OUT = sys.argv[2] if len(sys.argv) > 2 else P + "01_flood_labels/processed/daily_labelled_2015_2025_audited.csv"
STATUSES = {"flood", "no_flood", "unknown"}
assert OUT != ORIGINAL, "refusing to overwrite the original table"

orig = pd.read_csv(ORIGINAL, parse_dates=["date"])
corr = pd.read_csv(CORR, parse_dates=["date"], dtype=str, keep_default_na=False)
corr["date"] = pd.to_datetime(corr["date"])
m = corr.merge(orig[["catchment", "date", "label_status"]], on=["catchment", "date"], how="left")

problems = []
for i, r in m.iterrows():
    row = f"row {i + 2} ({r['catchment']} {r['date'].date()})"
    if not r["source_url"].strip():
        problems.append(f"{row}: no source_url")
    if r["new_status"] not in STATUSES:
        problems.append(f"{row}: new_status '{r['new_status']}' is not flood, no_flood or unknown")
    if pd.isna(r["label_status"]):
        problems.append(f"{row}: day not in the original table")
    elif r["old_status"] != r["label_status"]:
        problems.append(f"{row}: old_status '{r['old_status']}' but original is '{r['label_status']}'")
    elif r["new_status"] == r["old_status"]:
        problems.append(f"{row}: new_status equals old_status")
dup = corr[corr.duplicated(["catchment", "date"], keep=False)]
problems += [f"duplicate correction for {r.catchment} {r.date.date()}" for r in dup.itertuples()]
if problems:
    sys.exit("corrections refused, nothing written:\n" + "\n".join(problems))

out = orig.copy()
key = out.set_index(["catchment", "date"]).index
for r in corr.itertuples():
    i = key.get_loc((r.catchment, r.date))
    out.loc[i, "label_status"] = r.new_status
    out.loc[i, "event_id"] = None
# new flood days get one event id per run of consecutive days in a catchment
new = out[out["label_status"].eq("flood") & out["event_id"].isna()].sort_values(["catchment", "date"])
run = ((new["catchment"] != new["catchment"].shift()) | (new["date"].diff() != pd.Timedelta(days=1))).cumsum()
for _, g in new.groupby(run):
    out.loc[g.index, "event_id"] = f"AUDIT-{g['catchment'].iloc[0]}-{g['date'].min().date()}"

# same rules as build_daily_table.py: 2-day unknown buffer around flood days, then gap years.
# Corrected days keep their status, and only no_flood days become unknown.
BUFFER = 2
GAP_YEARS = [2017, 2020]
corrected = key.isin(pd.MultiIndex.from_frame(corr[["catchment", "date"]]))
free = out["label_status"].eq("no_flood") & ~corrected
flood = out[out["label_status"].eq("flood")]
near = pd.MultiIndex.from_tuples([(c, d + pd.Timedelta(days=k)) for c, d in zip(flood["catchment"], flood["date"])
                                  for k in range(-BUFFER, BUFFER + 1)])
buf = free & key.isin(near)
out.loc[buf, "label_status"] = "unknown"
gap = free & ~buf & out["date"].dt.year.isin(GAP_YEARS)
out.loc[gap, "label_status"] = "unknown"
print(int(buf.sum()), "buffer days and", int(gap.sum()), "gap-year days set from no_flood to unknown")

out.to_csv(OUT, index=False)
print(len(corr), "corrections applied, written to", OUT)
changed = pd.crosstab(orig["label_status"], out["label_status"]).rename_axis(index="original", columns="audited")
print(changed.to_string())
moves = [(a, b, n) for (a, b), n in changed.stack().items() if a != b and n]
for a, b, n in moves:
    print(f"{a} to {b}: {n} rows")
if not moves:
    print("no rows changed")
