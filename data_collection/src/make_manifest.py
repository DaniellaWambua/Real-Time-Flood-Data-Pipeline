import hashlib, pathlib, csv

root = pathlib.Path("data_collection/data")
skip = {".gitkeep", ".DS_Store", "manifest.csv"}
rows = []
for p in sorted(root.rglob("*")):
    if p.is_file() and p.name not in skip and "07_documentation" not in p.parts:
        rows.append([str(p.relative_to(root)), p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()])

with open(root / "07_documentation" / "manifest.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "bytes", "sha256"])
    w.writerows(rows)
print(len(rows), "files listed")