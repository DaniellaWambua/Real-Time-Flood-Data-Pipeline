"""
Tests for alert generation and the acknowledge/resolve workflow
(backend/flood_detection.py severity_for, PATCH /api/alerts/<id>).
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import app as app_module  # noqa: E402
import flood_detection  # noqa: E402


def _client():
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def _login(client, role="emergency_responder", username="responder-1"):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = username
        sess["role"] = role


def _alert(status):
    return {"id": 7, "status": status, "catchment": "Mathare"}


def test_severity_bands_split_the_room_above_the_threshold_in_thirds():
    assert flood_detection.severity_for(0.60, 0.555) == "low"
    assert flood_detection.severity_for(0.80, 0.555) == "medium"
    assert flood_detection.severity_for(0.95, 0.555) == "high"


def test_only_emergency_responders_can_change_alerts():
    client = _client()
    assert client.patch("/api/alerts/7", json={"action": "acknowledge"}).status_code == 401
    for role in ("government_official", "disaster_management_agency", "system_administrator"):
        _login(client, role=role)
        assert client.patch("/api/alerts/7", json={"action": "acknowledge"}).status_code == 403


def test_unknown_action_is_refused():
    client = _client()
    _login(client)
    assert client.patch("/api/alerts/7", json={"action": "delete"}).status_code == 400


def test_missing_alert_is_404():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_one", return_value=None):
        assert client.patch("/api/alerts/7", json={"action": "resolve"}).status_code == 404


def test_acknowledge_records_who_and_logs_it():
    client = _client()
    _login(client)
    with (
        patch("routes_dashboard.db.query_one", return_value=_alert("active")),
        patch("routes_dashboard.db.execute") as mock_execute,
        patch("routes_dashboard.models.log_event") as mock_log,
    ):
        resp = client.patch("/api/alerts/7", json={"action": "acknowledge"})
    assert resp.status_code == 200 and resp.get_json() == {"id": 7, "status": "acknowledged"}
    sql, params = mock_execute.call_args.args
    assert "acknowledged_at = now()" in sql and "acknowledged_by" in sql
    assert params == ("acknowledged", "responder-1", 7)
    mock_log.assert_called_once_with("responder-1", "alert_acknowledged", "alert 7 (Mathare)")


def test_resolve_works_from_acknowledged():
    client = _client()
    _login(client)
    with (
        patch("routes_dashboard.db.query_one", return_value=_alert("acknowledged")),
        patch("routes_dashboard.db.execute") as mock_execute,
        patch("routes_dashboard.models.log_event"),
    ):
        resp = client.patch("/api/alerts/7", json={"action": "resolve"})
    assert resp.status_code == 200
    assert mock_execute.call_args.args[1] == ("resolved", "responder-1", 7)


def test_a_resolved_alert_cannot_be_acknowledged_or_resolved_again():
    client = _client()
    _login(client)
    with patch("routes_dashboard.db.query_one", return_value=_alert("resolved")), \
         patch("routes_dashboard.db.execute") as mock_execute:
        assert client.patch("/api/alerts/7", json={"action": "acknowledge"}).status_code == 409
        assert client.patch("/api/alerts/7", json={"action": "resolve"}).status_code == 409
    mock_execute.assert_not_called()


def _run_detect(score):
    """detect() with the window, model and database replaced, returning its result and the SQL it ran."""
    from unittest.mock import MagicMock
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [[11], [22]]  # new result id, then new alert id
    with (
        patch("flood_detection.build_window", return_value=("window", None)),
        patch("flood_detection.score_window", return_value=score),
        patch("flood_detection.load_models", return_value=({"threshold": 0.555, "version": "v1"}, [])),
        patch("flood_detection.db.get_connection", return_value=conn),
    ):
        result = flood_detection.detect(2, "2024-04-29", 99)
    return result, [c.args[0] for c in cur.execute.call_args_list]


def test_a_flagged_day_raises_an_alert_with_its_severity():
    result, sql = _run_detect(0.9)
    assert result["flagged"] and result["severity"] == "high" and result["alert_id"] == 22
    assert any("INSERT INTO alerts" in s for s in sql)


def test_an_unflagged_day_raises_no_alert():
    result, sql = _run_detect(0.2)
    assert not result["flagged"] and result["alert_id"] is None
    assert not any("INSERT INTO alerts" in s for s in sql)
