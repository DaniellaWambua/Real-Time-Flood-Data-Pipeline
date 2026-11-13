"""
Checks for the dashboard endpoints (backend/routes_dashboard.py) with canned database rows:
routing, access control and JSON output, not the SQL itself.
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


def _login(client, role="disaster_management_agency", user_id=1, username="test-user"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
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


def test_recent_readings_returns_the_model_readings_only():
    client = _client()
    _login(client)
    now = datetime.datetime(2026, 10, 10, 12, 0, 0)
    rows = [
        {"id": 1, "recorded_at": now, "catchment": "Nairobi River",
         "source": "historical-replay", "rainfall_mm": 5.0, "era5_rain_mm": 4.1,
         "imerg_total_mm": 6.2, "imerg_max_rate": 1.8, "imerg_hours_ge5": 1.0,
         "soil_1": 0.31, "soil_2": 0.29, "temp_c": 18.4,
         "dewpoint_depression": 6.1, "pressure_hpa": 822.0},
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows) as mocked:
        resp = client.get("/api/readings/recent?catchment=Nairobi+River&limit=10")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["recorded_at"] == now.isoformat()
    assert body[0]["soil_2"] == 0.29
    sql = mocked.call_args.args[0]
    # the retired design's readings are gone, and rows without the model's own
    # inputs are left out rather than charted beside them
    assert "river_discharge_m3s" not in sql and "evaporation_mm" not in sql
    assert "era5_rain_mm IS NOT NULL" in sql
    # catchment filter and limit both reach the SQL params.
    assert mocked.call_args.args[1] == ("Nairobi River", 10)


def test_anomalies_recent_requires_login_only():
    client = _client()
    _login(client, role="emergency_responder")
    with patch("routes_dashboard.db.query_all", return_value=[]):
        resp = client.get("/api/anomalies/recent")
    assert resp.status_code == 200




def test_sources_list_hides_retired_sources():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_all", return_value=[]) as mocked:
        resp = client.get("/api/sources")
    assert resp.status_code == 200
    sql = mocked.call_args.args[0]
    # retired feeds are kept in the table, like the retired catchments, but the
    # screens only show the one that is still receiving
    assert "WHERE ds.is_active" in sql
    assert "ds.datasets" in sql


def test_sources_serializes_last_ingested_at():
    client = _client()
    _login(client)
    rows = [
        {
            "id": 1,
            "name": "CHIRPS",
            "source_type": "satellite_rainfall",
            "connection_status": "connected",
            "created_at": datetime.datetime(2026, 1, 1),
            "last_ingested_at": datetime.datetime(2026, 9, 1, 8, 30),
            "record_count": 1200,
        }
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows):
        resp = client.get("/api/sources")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["last_ingested_at"] == "2026-09-01T08:30:00"
    assert body[0]["record_count"] == 1200














def test_admin_stats_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.get("/api/admin/stats")
    assert resp.status_code == 403


def test_admin_stats_returns_counts_and_breakdowns():
    client = _client()
    _login(client, role="system_administrator")
    counts = {
        "users": 6,
        "users_pending": 1,
        "users_inactive": 0,
        "catchments": 3,
        "catchments_inactive": 2,
        "data_sources": 4,
        "sources_connected": 4,
        "readings": 40908,
        "readings_last_day": datetime.date(2025, 12, 31),
        "anomalies": 2193,
        "anomalies_flagged": 118,
        "incidents": 31,
        "incidents_pending": 4,
        "incidents_open": 2,
    }
    with patch("routes_dashboard.db.query_one", return_value=dict(counts)):
        resp = client.get("/api/admin/stats")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["users"] == 6 and body["users_pending"] == 1
    assert body["incidents_pending"] == 4 and body["anomalies_flagged"] == 118
    # the one date in the row is serialized, like every other endpoint here
    assert body["readings_last_day"] == "2025-12-31"


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
