"""Dragging the package's join or split moves every flight's, whatever it is called.

A lone AI ship's join and split read as NAV -- it has no formation to form -- so matching
those two waypoints by their label stopped working the day that landed. Matching by label
would not merely have missed them: for the primary flight it would have dragged the
first nav point of every other flight in the package instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs import Point

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.server.waypoints.routes import formation_waypoint
from game.utils import feet

_NOWHERE = Point(0, 0, None)  # type: ignore[arg-type]


def _waypoint(name: str, kind: FlightWaypointType) -> FlightWaypoint:
    return FlightWaypoint(name, kind, _NOWHERE, feet(20000))


def _flight(layout: Any) -> Any:
    return SimpleNamespace(flight_plan=SimpleNamespace(layout=layout))


def _formation_layout(join: FlightWaypoint, split: FlightWaypoint) -> Any:
    from game.ato.flightplans.formation import FormationLayout

    layout = FormationLayout.__new__(FormationLayout)
    layout.join = join
    layout.split = split
    return layout


def test_a_lone_ships_join_is_found_though_it_reads_NAV() -> None:
    join = _waypoint("NAV", FlightWaypointType.NAV)
    split = _waypoint("NAV", FlightWaypointType.NAV)
    flight = _flight(_formation_layout(join, split))

    assert formation_waypoint(flight, FlightWaypointType.JOIN) is join
    assert formation_waypoint(flight, FlightWaypointType.SPLIT) is split


def test_a_formation_flight_is_found_the_same_way() -> None:
    join = _waypoint("JOIN", FlightWaypointType.JOIN)
    split = _waypoint("SPLIT", FlightWaypointType.SPLIT)
    flight = _flight(_formation_layout(join, split))

    assert formation_waypoint(flight, FlightWaypointType.JOIN) is join


def test_a_custom_flight_plan_falls_back_to_the_label() -> None:
    """Degrading to a custom plan keeps the waypoints and their types but loses the
    layout that knew which was which."""
    join = _waypoint("JOIN", FlightWaypointType.JOIN)
    nav = _waypoint("NAV", FlightWaypointType.NAV)
    flight = SimpleNamespace(
        flight_plan=SimpleNamespace(
            layout=object(), iter_waypoints=lambda: iter([nav, join])
        )
    )

    assert formation_waypoint(flight, FlightWaypointType.JOIN) is join  # type: ignore[arg-type]


def test_a_flight_with_neither_reports_nothing() -> None:
    nav = _waypoint("NAV", FlightWaypointType.NAV)
    flight = SimpleNamespace(
        flight_plan=SimpleNamespace(layout=object(), iter_waypoints=lambda: iter([nav]))
    )

    assert formation_waypoint(flight, FlightWaypointType.JOIN) is None  # type: ignore[arg-type]
