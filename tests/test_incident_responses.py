"""
Tests for responses recorded against an incident (POST /api/incidents/<id>/responses, read through
GET /api/incidents/<id>): who may record which kind, when, and that each is logged. The database is a stand-in.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402

ROW = {"id": 3, "kind": "resources", "note": "two boats", "author": "official-1",
       "author_role": "government_official", "created_at": "2026-11-11T09:00:00+03:00"}


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role, username="user-1"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = username
        sess["role"] = role


def _post(role, kind, status="active", note="two boats", verification="verified"):
    client = _client()
    _login(client, role)
    incident = {"id": 7, "status": status, "verification": verification, "catchment": "Mathare"}
    with patch("routes_incidents.incidents.get", return_value=incident), \
         patch("routes_incidents.db.execute_returning", return_value=dict(ROW, kind=kind)) as insert, \
         patch("routes_incidents.models.log_event") as log:
        resp = client.post("/api/incidents/7/responses", json={"kind": kind, "note": note})
    return resp, insert, log


def test_an_official_records_resources_and_it_is_logged():
    resp, insert, log = _post("government_official", "resources")
    assert resp.status_code == 201 and resp.get_json()["kind"] == "resources"
    assert insert.call_args.args[1] == (7, "resources", "two boats", "user-1", "government_official")
    assert log.call_args.args[1] == "incident_response_resources"


def test_a_responder_records_field_updates_but_not_resources():
    assert _post("emergency_responder", "field")[0].status_code == 201
    assert _post("emergency_responder", "resources")[0].status_code == 403
    assert _post("government_official", "field")[0].status_code == 403


def test_other_roles_cannot_record_anything():
    assert _post("disaster_management_agency", "field")[0].status_code == 403
    assert _post("system_administrator", "resources")[0].status_code == 403


def test_recovery_only_after_resolution_and_nothing_else_after_it():
    assert _post("government_official", "recovery", status="active")[0].status_code == 409
    assert _post("government_official", "recovery", status="resolved")[0].status_code == 201
    assert _post("emergency_responder", "field", status="resolved")[0].status_code == 409


def test_a_bad_kind_or_empty_note_is_refused():
    assert _post("government_official", "money")[0].status_code == 400
    assert _post("government_official", "resources", note="   ")[0].status_code == 400
    assert _post("government_official", "resources", note="x" * 1001)[0].status_code == 400


def test_nothing_can_be_recorded_before_verification():
    assert _post("government_official", "resources", verification="pending")[0].status_code == 404


def test_the_detail_carries_the_days_and_the_history():
    client = _client()
    assert client.get("/api/incidents/7").status_code == 401
    _login(client, "disaster_management_agency")
    incident = {"id": 7, "verification": "pending", "status": "active", "catchment": "Mathare",
                "provisional": False, "confirmed_days": 0, "not_confirmed_days": 0, "flagged_days": 1}
    with patch("routes_incidents.incidents.get", return_value=incident), \
         patch("routes_incidents.db.query_all", side_effect=[[{"id": 1, "severity": "high"}], [dict(ROW)]]):
        body = client.get("/api/incidents/7").get_json()
    assert body["days_flagged"][0]["severity"] == "high" and body["response_list"][0]["note"] == "two boats"
