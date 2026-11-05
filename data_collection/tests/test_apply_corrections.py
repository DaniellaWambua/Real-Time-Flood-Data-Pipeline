import os
import subprocess
import sys
import tempfile

# Run from the repo root: python data_collection/tests/test_apply_corrections.py (also works with pytest)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "src", "apply_corrections.py")
ORIGINAL = os.path.join(ROOT, "data", "01_flood_labels", "processed", "daily_labelled_2015_2025.csv")
HEADER = "date,catchment,old_status,new_status,source_type,source_name,source_url,evidence_note,checker,date_checked\n"


def test_no_corrections_gives_identical_file():
    with tempfile.TemporaryDirectory() as tmp:
        corr, out = os.path.join(tmp, "corrections.csv"), os.path.join(tmp, "audited.csv")
        with open(corr, "w") as f:
            f.write(HEADER)
        subprocess.run([sys.executable, SCRIPT, corr, out], check=True, capture_output=True,
                       cwd=os.path.dirname(ROOT))
        with open(ORIGINAL, "rb") as a, open(out, "rb") as b:
            assert a.read() == b.read(), "audited file differs from the original with no corrections"


if __name__ == "__main__":
    test_no_corrections_gives_identical_file()
    print("ok test_no_corrections_gives_identical_file")
