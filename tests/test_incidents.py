"""
Tests for incidents (backend/incidents.py, routes_incidents.py): grouping flagged days, verification by
Disaster Management, what each role sees, acknowledging and resolving with a field outcome.
The database is a stand-in, so these check routing, rules and SQL parameters, not real queries.
"""
import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import incidents  # noqa: E402

DAY = datetime.date.today() - datetime.timedelta(days=9)


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role, username="user-1"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = username
        sess["role"] = role


def _incident(**over):
    row = {"id": 7, "catchment": "Mathare", "wards": ["Mabatini"], "start_day": DAY, "end_day": DAY,
           "severity": "high", "verification": "verified", "status": "active", "provisional": False,
           "confirmation": None}
    row.update(over)
    return row


# grouping
def test_a_flagged_day_next_to_an_open_incident_extends_it():
    cur = MagicMock()
    cur.fetchone.return_value = [5]
    assert incidents.attach(cur, 22, 2, DAY) == (5, False)
    sql = [c.args[0] for c in cur.execute.call_args_list]
    assert "BETWEEN start_day - 1 AND end_day + 1" in sql[0] and "verification <> 'dismissed'" in sql[0]
    assert sql[1].startswith("UPDATE incidents SET start_day = LEAST")
    assert cur.execute.call_args_list[2].args[1] == (5, 22)


def test_a_flagged_day_with_no_open_incident_nearby_opens_one():
    cur = MagicMock()
    cur.fetchone.side_effect = [None, [9]]
    assert incidents.attach(cur, 22, 2, DAY) == (9, True)
    assert cur.execute.call_args_list[1].args[0].startswith("INSERT INTO incidents")


def test_confirmation_rolls_up_from_the_days():
    base = {"provisional": False, "confirmed_days": 0, "not_confirmed_days": 0, "flagged_days": 3}
    assert incidents.confirmation({**base, "provisional": True}) == "provisional"
    assert incidents.confirmation({**base, "confirmed_days": 1, "not_confirmed_days": 2}) == "confirmed"
    assert incidents.confirmation({**base, "not_confirmed_days": 3}) == "not_confirmed"
    assert incidents.confirmation(base) is None


# what each role sees
def test_field_roles_only_see_verified_incidents():
    for role, scoped in (("emergency_responder", True), ("government_official", True),
                         ("disaster_management_agency", False), ("system_administrator", False)):
        client = _client()
        _login(client, role)
        with patch("routes_incidents.db.query_all", return_value=[]) as q:
            assert client.get("/api/incidents?status=open").status_code == 200
        sql = q.call_args.args[0]
        assert ("i.verification = 'verified'" in sql) is scoped, role
        assert "i.status <> 'resolved' AND i.verification <> 'dismissed'" in sql


def test_a_field_role_gets_404_for_an_unverified_incident():
    client = _client()
    _login(client, "emergency_responder")
    with patch("routes_incidents.incidents.get", return_value=_incident(verification="pending")):
        assert client.get("/api/incidents/7").status_code == 404


def test_summary_leaves_dismissed_incidents_out_of_the_queue_counts():
    client = _client()
    _login(client, "disaster_management_agency")
    rows = [{"verification": "pending", "status": "active", "severity": "high", "count": 3},
            {"verification": "dismissed", "status": "active", "severity": "low", "count": 2},
            {"verification": "verified", "status": "resolved", "severity": "medium", "count": 1}]
    with patch("routes_incidents.db.query_all", return_value=rows):
        body = client.get("/api/incidents/summary").get_json()
    assert body["total"] == 6 and body["pending"] == 3 and body["dismissed"] == 2
    assert body["active"] == 3 and body["low"] == 0 and body["by_severity"]["medium"]["resolved"] == 1


# verification
def _verify(role, decision, incident=None):
    client = _client()
    _login(client, role, "officer-1")
    with patch("routes_incidents.incidents.get", return_value=incident or _incident(verification="pending")), \
         patch("routes_incidents.db.execute") as execute, \
         patch("routes_incidents.models.log_event") as log, \
         patch("routes_incidents.notify.incident_verified", return_value=4) as told:
        resp = client.post("/api/incidents/7/verification", json={"decision": decision, "note": "Red Cross report"})
    return resp, execute, log, told


def test_only_disaster_management_can_verify():
    for role in ("emergency_responder", "government_official", "system_administrator"):
        assert _verify(role, "verify")[0].status_code == 403


def test_verifying_tells_the_field_and_is_logged():
    resp, execute, log, told = _verify("disaster_management_agency", "verify")
    assert resp.status_code == 200 and resp.get_json() == {"id": 7, "verification": "verified", "notified": 4}
    assert execute.call_args.args[1] == ("verified", "officer-1", "Red Cross report", 7)
    assert log.call_args.args[1] == "incident_verified"
    told.assert_called_once()


def test_dismissing_tells_nobody():
    resp, _, log, told = _verify("disaster_management_agency", "dismiss")
    assert resp.get_json()["verification"] == "dismissed" and log.call_args.args[1] == "incident_dismissed"
    told.assert_not_called()


def test_verifying_an_old_replayed_incident_does_not_notify():
    old = _incident(verification="pending", end_day=datetime.date(2024, 4, 29))
    resp, _, _, told = _verify("disaster_management_agency", "verify", old)
    assert resp.status_code == 200 and resp.get_json()["notified"] == 0
    told.assert_not_called()


def test_an_incident_is_verified_only_once():
    assert _verify("disaster_management_agency", "verify", _incident())[0].status_code == 409
    assert _verify("disaster_management_agency", "maybe")[0].status_code == 400


# acknowledging and resolving
def _act(path, body, incident, role="emergency_responder"):
    client = _client()
    _login(client, role, "responder-1")
    with patch("routes_incidents.incidents.get", return_value=incident), \
         patch("routes_incidents.db.execute") as execute, \
         patch("routes_incidents.models.log_event") as log:
        resp = client.post(f"/api/incidents/7/{path}", json=body)
    return resp, execute, log


def test_a_responder_acknowledges_a_verified_active_incident():
    resp, execute, log = _act("acknowledge", {}, _incident())
    assert resp.status_code == 200 and execute.call_args.args[1] == ("responder-1", 7)
    assert log.call_args.args[1] == "incident_acknowledged"
    assert _act("acknowledge", {}, _incident(status="acknowledged"))[0].status_code == 409
    assert _act("acknowledge", {}, _incident(), role="government_official")[0].status_code == 403


def test_resolving_needs_an_outcome_and_records_it():
    assert _act("resolve", {}, _incident())[0].status_code == 400
    resp, execute, log = _act("resolve", {"outcome": "flooding_observed", "places": "Mabatini", "note": "knee deep"},
                              _incident(status="acknowledged"))
    assert resp.status_code == 200 and resp.get_json()["outcome"] == "flooding_observed"
    assert execute.call_args.args[1] == ("responder-1", "flooding_observed", "Mabatini", "knee deep", 7)
    assert "flooding observed" in log.call_args.args[2]
    assert _act("resolve", {"outcome": "no_flooding"}, _incident(status="resolved"))[0].status_code == 409


def test_a_responder_cannot_act_on_an_unverified_incident():
    assert _act("acknowledge", {}, _incident(verification="pending"))[0].status_code == 404
