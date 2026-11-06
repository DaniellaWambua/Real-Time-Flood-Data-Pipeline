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


def test_alerts_summary_requires_login():
    client = _client()
    resp = client.get("/api/alerts/summary")
    assert resp.status_code == 401


def test_alerts_summary_counts_across_status_and_severity():
    client = _client()
    _login(client)
    # Three grouped rows, as GROUP BY status, severity would return them.
    rows = [
        {"status": "active", "severity": "high", "count": 3},
        {"status": "active", "severity": "low", "count": 2},
        {"status": "resolved", "severity": "medium", "count": 5},
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows):
        resp = client.get("/api/alerts/summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {
        "total": 10,
        "active": 5,
        "resolved": 5,
        "low": 2,
        "medium": 5,
        "high": 3,
        "by_severity": {
            "low": {"active": 2, "resolved": 0},
            "medium": {"active": 0, "resolved": 5},
            "high": {"active": 3, "resolved": 0},
        },
    }


def test_alerts_summary_catchment_filter_reaches_sql():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_all", return_value=[]) as mocked:
        resp = client.get("/api/alerts/summary?catchment=Mathare")
    assert resp.status_code == 200
    args = mocked.call_args.args[1]
    assert args == ("Mathare",)


def test_alerts_trend_requires_login():
    client = _client()
    resp = client.get("/api/alerts/trend")
    assert resp.status_code == 401


def test_alerts_trend_serializes_daily_counts():
    client = _client()
    _login(client)
    rows = [
        {"day": datetime.datetime(2026, 9, 1), "count": 4},
        {"day": datetime.datetime(2026, 9, 2), "count": 7},
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows):
        resp = client.get("/api/alerts/trend")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == [
        {"day": "2026-09-01T00:00:00", "count": 4},
        {"day": "2026-09-02T00:00:00", "count": 7},
    ]


def test_alerts_trend_catchment_filter_reaches_sql():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_all", return_value=[]) as mocked:
        resp = client.get("/api/alerts/trend?catchment=Mathare")
    assert resp.status_code == 200
    args = mocked.call_args.args[1]
    assert args == ("Mathare",)


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


def test_create_user_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.post("/api/users", json={"username": "a", "password": "longenough", "role": "emergency_responder"})
    assert resp.status_code == 403


def test_create_user_validates_missing_fields():
    client = _client()
    _login(client, role="system_administrator")
    resp = client.post("/api/users", json={"username": "", "password": "", "role": ""})
    assert resp.status_code == 400


def test_create_user_rejects_invalid_role():
    client = _client()
    _login(client, role="system_administrator")
    resp = client.post(
        "/api/users",
        json={"username": "newbie", "password": "longenough", "role": "not_a_real_role"},
    )
    assert resp.status_code == 400


def test_create_user_rejects_short_password():
    client = _client()
    _login(client, role="system_administrator")
    resp = client.post(
        "/api/users",
        json={"username": "newbie", "password": "short", "role": "emergency_responder"},
    )
    assert resp.status_code == 400


def test_create_user_rejects_duplicate_username():
    client = _client()
    _login(client, role="system_administrator")
    with patch("routes_dashboard.models.get_user_by_username", return_value={"id": 1}):
        resp = client.post(
            "/api/users",
            json={"username": "existing", "password": "longenough", "role": "emergency_responder"},
        )
    assert resp.status_code == 409


def test_create_user_success_logs_event():
    client = _client()
    _login(client, role="system_administrator", username="root-admin")
    with (
        patch("routes_dashboard.models.get_user_by_username", return_value=None),
        patch("routes_dashboard.models.create_user", return_value=42) as mock_create,
        patch("routes_dashboard.models.log_event") as mock_log,
    ):
        resp = client.post(
            "/api/users",
            json={"username": "newbie", "password": "longenough", "role": "emergency_responder"},
        )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body == {"id": 42, "username": "newbie", "role": "emergency_responder", "is_active": True, "email": None}
    mock_create.assert_called_once_with("newbie", "longenough", "emergency_responder", email=None)
    mock_log.assert_called_once_with("root-admin", "user_created", "newbie (emergency_responder)")


def test_update_user_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.patch("/api/users/1", json={"role": "emergency_responder"})
    assert resp.status_code == 403


def test_update_user_no_such_user():
    client = _client()
    _login(client, role="system_administrator")
    with patch("routes_dashboard.models.get_user_by_id", return_value=None):
        resp = client.patch("/api/users/999", json={"role": "emergency_responder"})
    assert resp.status_code == 404


def test_update_user_prevents_self_deactivation():
    client = _client()
    _login(client, role="system_administrator", user_id=7)
    target = {"id": 7, "username": "root-admin", "role": "system_administrator", "is_active": True}
    with patch("routes_dashboard.models.get_user_by_id", return_value=target):
        resp = client.patch("/api/users/7", json={"is_active": False})
    assert resp.status_code == 400


def test_update_user_rejects_invalid_role():
    client = _client()
    _login(client, role="system_administrator", user_id=1)
    target = {"id": 2, "username": "someone", "role": "emergency_responder", "is_active": True}
    with patch("routes_dashboard.models.get_user_by_id", return_value=target):
        resp = client.patch("/api/users/2", json={"role": "not_a_real_role"})
    assert resp.status_code == 400


def test_update_user_changes_role_and_logs_event():
    client = _client()
    _login(client, role="system_administrator", user_id=1, username="root-admin")
    before = {"id": 2, "username": "someone", "role": "emergency_responder", "is_active": True, "email": None}
    after = {"id": 2, "username": "someone", "role": "government_official", "is_active": True, "email": None}
    with (
        patch("routes_dashboard.models.get_user_by_id", side_effect=[before, after]),
        patch("routes_dashboard.models.update_user_role") as mock_update_role,
        patch("routes_dashboard.models.log_event") as mock_log,
    ):
        resp = client.patch("/api/users/2", json={"role": "government_official"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"id": 2, "username": "someone", "role": "government_official", "is_active": True, "email": None}
    mock_update_role.assert_called_once_with(2, "government_official")
    mock_log.assert_called_once_with("root-admin", "user_role_changed", "someone -> government_official")


def test_update_user_resets_password_and_logs_event():
    client = _client()
    _login(client, role="system_administrator", user_id=1, username="root-admin")
    target = {"id": 2, "username": "someone", "role": "emergency_responder", "is_active": True, "email": None}
    with (
        patch("routes_dashboard.models.get_user_by_id", return_value=target),
        patch("routes_dashboard.models.update_password") as mock_update_password,
        patch("routes_dashboard.models.log_event") as mock_log,
    ):
        resp = client.patch("/api/users/2", json={"password": "a-new-password-123"})
    assert resp.status_code == 200
    mock_update_password.assert_called_once_with("someone", "a-new-password-123")
    mock_log.assert_called_once_with("root-admin", "user_password_reset", "someone")


def test_admin_stats_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.get("/api/admin/stats")
    assert resp.status_code == 403


def test_admin_stats_returns_counts():
    client = _client()
    _login(client, role="system_administrator")
    counts = iter([3, 6, 3, 40908, 1500, 1828])
    with patch("routes_dashboard.db.query_one", side_effect=lambda *a, **k: {"count": next(counts)}):
        resp = client.get("/api/admin/stats")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "users": 3,
        "catchments": 6,
        "data_sources": 3,
        "readings": 40908,
        "anomalies": 1500,
        "alerts": 1828,
    }


def test_logs_requires_system_administrator_role():
    client = _client()
    _login(client, role="emergency_responder")
    resp = client.get("/api/logs")
    assert resp.status_code == 403


def test_logs_returns_rows():
    client = _client()
    _login(client, role="system_administrator")
    rows = [
        {
            "id": 1,
            "occurred_at": datetime.datetime(2026, 9, 1, 8, 30),
            "actor": "root-admin",
            "action": "login_success",
            "detail": None,
        }
    ]
    with patch("routes_dashboard.db.query_all", return_value=rows) as mocked:
        resp = client.get("/api/logs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body[0]["occurred_at"] == "2026-09-01T08:30:00"
    args = mocked.call_args.args[1]
    assert args == (20,)


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
