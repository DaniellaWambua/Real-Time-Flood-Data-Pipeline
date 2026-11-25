"""Test-only settings, so the suite runs without a real backend/.env."""
import os
import sys
from pathlib import Path

import pytest

for name, value in {
    "DB_PASSWORD": "test-db-password",
    "SECRET_KEY": "test-secret-key",
    "INTERNAL_API_TOKEN": "test-internal-token",
    "RATE_LIMITS": "off",  # tests/test_security.py turns the limits on where it checks them
}.items():
    os.environ.setdefault(name, value)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


@pytest.fixture(autouse=True)
def session_matches_the_account(request):
    """Every signed-in request checks the session against the account in the database
    (decorators.current_user). Tests have no database, so by default the account is taken to be
    active, with the role and session version the test put in the session. Tests marked
    real_session_check (tests/test_security.py) supply their own account instead."""
    if request.node.get_closest_marker("real_session_check"):
        yield
        return
    import flask
    import models

    def state(user_id):
        return {"id": user_id, "username": flask.session.get("username"), "role": flask.session.get("role"),
                "is_active": True, "session_version": flask.session.get("sv")}

    original = models.session_state
    models.session_state = state
    yield
    models.session_state = original


def pytest_configure(config):
    config.addinivalue_line("markers", "real_session_check: use the test's own models.session_state")
