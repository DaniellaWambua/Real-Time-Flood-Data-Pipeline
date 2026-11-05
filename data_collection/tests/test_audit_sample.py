import ast
import os
import re
import sys

# Run from the repo root: python data_collection/tests/test_audit_sample.py (also works with pytest)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "src", "audit_sample.py")
BANNED = ("score", "pred", "tuned", "dev_")
FILE = re.compile(r"[\w./-]+\.(?:csv|parquet|pkl|json|npy|npz|h5|keras|joblib|txt)", re.I)
sys.path.insert(0, os.path.join(ROOT, "src"))


def test_script_names_no_model_output_files():
    text = open(SCRIPT).read()
    names = set(FILE.findall(text))
    names |= {n.value for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    bad = sorted(n for n in names if any(b in n.lower() for b in BANNED))
    assert not bad, f"audit_sample.py mentions model output files: {bad}"


def test_allowed_inputs_are_clean():
    import audit_sample
    for path in audit_sample.ALLOWED.values():
        assert not any(b in path.lower() for b in BANNED), path


def test_other_files_are_refused():
    import audit_sample
    try:
        audit_sample.read_allowed("data_collection/data/08_model_ready/other.csv")
    except ValueError:
        return
    raise AssertionError("read_allowed opened a file outside ALLOWED")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
