"""
Sanity checks for db/update_catchment_coords.py, the one-off script
that moves an already-seeded database's catchment_areas.geom onto
whatever seed.py's CATCHMENT_COORDS currently says (see
db/COORDS_SOURCES.md for why this script exists alongside seed.py,
which deliberately never touches an existing row).

db.query_one/db.execute are monkeypatched with canned data, same style
as tests/test_dashboard_api.py and tests/test_change_password.py, so
this checks the comparison and update logic, not real SQL against a
live database.
"""

import sys
from pathlib import Path
from unittest.mock import patch

DB_DIR = Path(__file__).resolve().parent.parent / "db"
sys.path.insert(0, str(DB_DIR))

import update_catchment_coords  # noqa: E402
from seed import CATCHMENT_COORDS  # noqa: E402


def _row_for(name, offset):
    """A canned catchment_areas row, offset from its real
    CATCHMENT_COORDS value by `offset` degrees (0 means "already
    current"), keyed to whichever catchment name the SQL asks for."""
    lon, lat = CATCHMENT_COORDS[name]
    return {"id": 1, "lon": lon + offset, "lat": lat + offset}


def test_updates_every_catchment_whose_coordinates_moved():
    def fake_query_one(_sql, params):
        (name,) = params
        return _row_for(name, offset=1.0)  # clearly different from current

    with patch("update_catchment_coords.db.query_one", side_effect=fake_query_one) as query_one, \
         patch("update_catchment_coords.db.execute") as execute:
        update_catchment_coords.update_catchment_coords()

    # One SELECT and one UPDATE per catchment in CATCHMENT_COORDS.
    assert query_one.call_count == len(CATCHMENT_COORDS)
    assert execute.call_count == len(CATCHMENT_COORDS)

    updated_names = {call.args[1][2] for call in execute.call_args_list}
    assert updated_names == set(CATCHMENT_COORDS)
    sql = execute.call_args_list[0].args[0]
    assert "UPDATE catchment_areas SET geom" in sql


def test_skips_a_catchment_already_at_the_current_coordinates():
    def fake_query_one(_sql, params):
        (name,) = params
        return _row_for(name, offset=0.0)  # already current for every catchment

    with patch("update_catchment_coords.db.query_one", side_effect=fake_query_one), \
         patch("update_catchment_coords.db.execute") as execute:
        update_catchment_coords.update_catchment_coords()

    execute.assert_not_called()


def test_updates_only_the_catchments_that_moved():
    def fake_query_one(_sql, params):
        (name,) = params
        # Only Mathare is stale; everything else is already current.
        return _row_for(name, offset=1.0 if name == "Mathare" else 0.0)

    with patch("update_catchment_coords.db.query_one", side_effect=fake_query_one), \
         patch("update_catchment_coords.db.execute") as execute:
        update_catchment_coords.update_catchment_coords()

    execute.assert_called_once()
    assert execute.call_args.args[1][2] == "Mathare"


def test_skips_a_catchment_not_found_in_the_database():
    with patch("update_catchment_coords.db.query_one", return_value=None), \
         patch("update_catchment_coords.db.execute") as execute:
        update_catchment_coords.update_catchment_coords()

    execute.assert_not_called()


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"all {len(tests)} tests passed")
