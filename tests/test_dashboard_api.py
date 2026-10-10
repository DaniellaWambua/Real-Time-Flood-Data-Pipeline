"""
Sanity checks for the dashboard API blueprint (backend/routes_dashboard.py),
run directly with plain Python (no pytest, no live Postgres), matching
tests/test_preprocessing.py's style.

db.query_all/db.query_one are monkeypatched with canned rows, so these
check the blueprint's routing, auth decorators and JSON/datetime
serialization only, not real SQL. db/seed.py plus a live Postgres (see
db/docker-compose.yml) remain the way to check the SQL itself.
"""

import datetime
import sys
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import app as app_module  # noqa: E402


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="disaster_management_agency"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test-user"
        sess["role"] = role


def test_catchments_requires_login():
    client = _client()
    resp = client.get("/api/catchments")
    assert resp.status_code == 401


def test_catchments_serializes_rows():
    client = _client()
    _login(client)
    rows = [
        {"id": 1, "name": "Nairobi River", "county": "Nairobi",
         "longitude": 36.8265, "latitude": -1.2864},
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows):
        resp = client.get("/api/catchments")
    assert resp.status_code == 200
    assert resp.get_json() == rows


def test_recent_readings_serializes_datetimes():
    client = _client()
    _login(client)
    now = datetime.datetime(2026, 10, 10, 12, 0, 0)
    rows = [
        {"id": 1, "recorded_at": now, "catchment": "Nairobi River",
         "source": "simulated-dataset-feed", "rainfall_mm": 5.0,
         "river_discharge_m3s": 1.2, "soil_moisture_m3m3": 0.3,
         "evaporation_mm": 2.0, "oni": 0.1},
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows) as mocked:
        resp = client.get("/api/readings/recent?catchment=Nairobi+River&limit=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["recorded_at"] == now.isoformat()
    # catchment filter and limit both reach the SQL params.
    args = mocked.call_args.args[1]
    assert args == ("Nairobi River", 10)


def test_alerts_filters_pass_through():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_all", return_value=[]) as mocked:
        resp = client.get("/api/alerts?severity=high&status=active")
    assert resp.status_code == 200
    args = mocked.call_args.args[1]
    assert "high" in args and "active" in args


def test_anomalies_recent_requires_login_only():
    client = _client()
    _login(client, role="emergency_responder")
    with patch("routes_dashboard.db.query_all", return_value=[]):
        resp = client.get("/api/anomalies/recent")
    assert resp.status_code == 200


def test_users_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.get("/api/users")
    assert resp.status_code == 403


def test_users_allows_system_administrator():
    client = _client()
    _login(client, role="system_administrator")
    rows = [{"id": 1, "username": "admin", "role": "system_administrator",
             "created_at": datetime.datetime(2026, 1, 1)}]
    with patch("routes_dashboard.db.query_all", return_value=rows):
        resp = client.get("/api/users")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "password_hash" not in body[0]


def test_sources_list():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_all", return_value=[]):
        resp = client.get("/api/sources")
    assert resp.status_code == 200


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
