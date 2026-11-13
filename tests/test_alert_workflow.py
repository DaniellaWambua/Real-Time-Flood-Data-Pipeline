"""
Tests for alert generation (backend/flood_detection.py): severity bands, and that a flagged day raises
an alert filed under an incident. The incident workflow itself is in tests/test_incidents.py.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import flood_detection  # noqa: E402


def test_severity_bands_split_the_room_above_the_threshold_in_thirds():
    assert flood_detection.severity_for(0.60, 0.555) == "low"
    assert flood_detection.severity_for(0.80, 0.555) == "medium"
    assert flood_detection.severity_for(0.95, 0.555) == "high"


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
        patch("flood_detection.has_model", return_value=False),  # no fast model: nothing provisional to settle
        patch("incidents.attach", return_value=(5, True)) as attach,
    ):
        result = flood_detection.detect(2, "2024-04-29", 99)
    _run_detect.attach = attach
    return result, [c.args[0] for c in cur.execute.call_args_list]


def test_a_flagged_day_raises_an_alert_with_its_severity():
    result, sql = _run_detect(0.9)
    assert result["flagged"] and result["severity"] == "high" and result["alert_id"] == 22
    assert any("INSERT INTO alerts" in s for s in sql)
    assert result["incident_id"] == 5 and result["new_incident"] is True
    assert _run_detect.attach.call_args.args[1:] == (22, 2, "2024-04-29")


def test_an_unflagged_day_raises_no_alert():
    result, sql = _run_detect(0.2)
    assert not result["flagged"] and result["alert_id"] is None
    assert not any("INSERT INTO alerts" in s for s in sql)
    _run_detect.attach.assert_not_called()
