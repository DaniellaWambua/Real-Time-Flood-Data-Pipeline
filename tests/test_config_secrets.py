"""Both config files must refuse to start when a required secret is missing."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ["DB_PASSWORD", "SECRET_KEY", "INTERNAL_API_TOKEN"]


def _load(path):
    """Run a config file fresh, as a separate module."""
    spec = importlib.util.spec_from_file_location(f"cfg_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch):
    # ignore the developer's own backend/.env so only the test's settings count
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)


@pytest.mark.parametrize("path", [ROOT / "backend" / "config.py", ROOT / "ingestion" / "config.py"])
@pytest.mark.parametrize("missing", SECRETS)
def test_a_missing_secret_stops_start_up(monkeypatch, path, missing):
    if missing == "SECRET_KEY" and path.parent.name == "ingestion":
        pytest.skip("the ingestion layer does not use SECRET_KEY")
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match=missing):
        _load(path)


@pytest.mark.parametrize("path", [ROOT / "backend" / "config.py", ROOT / "ingestion" / "config.py"])
def test_secrets_come_from_the_environment(monkeypatch, path):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "from-the-environment")
    assert _load(path).INTERNAL_API_TOKEN == "from-the-environment"
