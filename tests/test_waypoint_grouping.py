"""Folding a target set into one row must not move anything else.

A DEAD run on a Patriot site is sixteen consecutive target waypoints, and the route
table drew sixteen near-identical rows for them. They fold into one row you can open --
which means the display row and the index into ``flight_plan.waypoints`` no longer line
up, and everything that acted on "the selected row" was indexing the waypoint list with
it. Deleting row 5 would have deleted the wrong waypoint.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.ato.flightwaypointtype import FlightWaypointType
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
    QFlightWaypointList,
    TARGET_TYPES,
)

_group_at = QFlightWaypointList._group_at


def _waypoint(kind: FlightWaypointType, name: str = "") -> Any:
    return SimpleNamespace(waypoint_type=kind, name=name)


NAV = FlightWaypointType.NAV
TARGET = FlightWaypointType.TARGET_POINT


def test_the_target_types_are_the_ones_that_fold() -> None:
    """Named rather than inferred: folding a NAV point would hide a leg you fly."""
    assert FlightWaypointType.TARGET_POINT in TARGET_TYPES
    assert FlightWaypointType.TARGET_GROUP_LOC in TARGET_TYPES
    assert FlightWaypointType.TARGET_SHIP in TARGET_TYPES
    assert FlightWaypointType.NAV not in TARGET_TYPES
    assert FlightWaypointType.INGRESS_STRIKE not in TARGET_TYPES


def test_a_run_of_targets_is_counted_from_where_it_starts() -> None:
    route = [_waypoint(NAV)] + [_waypoint(TARGET) for _ in range(16)] + [_waypoint(NAV)]
    assert _group_at(route, 1) == 16
    # From the middle of the run, only what is left of it.
    assert _group_at(route, 10) == 7


def test_something_that_is_not_a_target_is_not_a_group() -> None:
    route = [_waypoint(NAV), _waypoint(TARGET)]
    assert _group_at(route, 0) == 0


def test_a_single_target_is_a_group_of_one() -> None:
    """Counted, but the table draws it as an ordinary row: folding one row into one
    row would only cost a click."""
    route = [_waypoint(NAV), _waypoint(TARGET), _waypoint(NAV)]
    assert _group_at(route, 1) == 1


def test_a_run_that_ends_the_route_does_not_run_off_the_end() -> None:
    route = [_waypoint(NAV), _waypoint(TARGET), _waypoint(TARGET)]
    assert _group_at(route, 1) == 2


def _list_with_rows(rows: list[Any], waypoints: list[Any]) -> Any:
    """A bare list object with just the mapping filled in -- no Qt widget needed."""
    view: Any = QFlightWaypointList.__new__(QFlightWaypointList)
    view._row_waypoints = rows
    view.flight = SimpleNamespace(flight_plan=SimpleNamespace(waypoints=waypoints))
    return view


def test_a_row_resolves_to_the_waypoint_it_stands_for() -> None:
    waypoints = [_waypoint(NAV, "takeoff"), _waypoint(NAV, "join"), _waypoint(TARGET)]
    view = _list_with_rows([0, 1, None], waypoints)
    assert view.waypoint_at_row(0).name == "takeoff"
    assert view.waypoint_at_row(1).name == "join"


def test_a_group_header_stands_for_no_single_waypoint() -> None:
    """So deleting it deletes nothing rather than something at random."""
    view = _list_with_rows([0, None], [_waypoint(NAV), _waypoint(TARGET)])
    assert view.waypoint_at_row(1) is None


def test_a_row_that_is_not_there_resolves_to_nothing() -> None:
    view = _list_with_rows([0], [_waypoint(NAV)])
    assert view.waypoint_at_row(-1) is None
    assert view.waypoint_at_row(9) is None


def test_the_mapping_survives_a_route_that_shrank_under_it() -> None:
    """The table is rebuilt from the plan, but a stale row must not raise."""
    view = _list_with_rows([0, 1, 2], [_waypoint(NAV)])
    assert view.waypoint_at_row(0) is not None
    assert view.waypoint_at_row(2) is None
