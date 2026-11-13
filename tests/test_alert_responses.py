"""
Tests for responses recorded against an alert (GET/POST /api/alerts/<id>/responses):
who may record which kind, when, and that each is logged. The database is a stand-in.
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


def _post(role, kind, status="active", note="two boats"):
    client = _client()
    _login(client, role)
    with patch("routes_dashboard.db.query_one", return_value={"id": 7, "status": status, "catchment": "Mathare"}), \
         patch("routes_dashboard.db.execute_returning", return_value=dict(ROW, kind=kind)) as insert, \
         patch("routes_dashboard.models.log_event") as log:
        resp = client.post("/api/alerts/7/responses", json={"kind": kind, "note": note})
    return resp, insert, log


def test_an_official_records_resources_and_it_is_logged():
    resp, insert, log = _post("government_official", "resources")
    assert resp.status_code == 201 and resp.get_json()["kind"] == "resources"
    assert insert.call_args.args[1] == (7, "resources", "two boats", "user-1", "government_official")
    assert log.call_args.args[1] == "alert_response_resources"


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


def test_every_signed_in_role_can_read_the_history():
    client = _client()
    assert client.get("/api/alerts/7/responses").status_code == 401
    _login(client, "disaster_management_agency")
    with patch("routes_dashboard.db.query_all", return_value=[dict(ROW)]):
        resp = client.get("/api/alerts/7/responses")
    assert resp.status_code == 200 and resp.get_json()[0]["note"] == "two boats"
