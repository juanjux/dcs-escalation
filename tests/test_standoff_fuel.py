"""A stand-off attack is flown by the weapon, and charged to the aeroplane.

The package puts its ingress at the range its weapons are fired from -- a hundred and
fifty miles out for a SLAM-ER -- and leaves the target points where they are, because
that is what the mission file has to say. The fuel estimate walked those points, so a
Hornet that flies out to the launch point and turns was charged for flying to the
target and back out to the split as well: three hundred and eighty-six miles of a five
hundred and seventy-five mile bill, half of it at the combat rate.

Every flight in the campaign then read as too short of fuel to reach its own target, so
every one was given a refuelling waypoint -- which is what the fuel estimate was added
to stop happening.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.fuelestimate import _route_actually_flown, releases_at_ingress
from game.utils import nautical_miles


class _Point:
    """A position on a line, in metres, which is all a distance needs."""

    def __init__(self, nm_from_target: float) -> None:
        self.x = nautical_miles(nm_from_target).meters

    def distance_to_point(self, other: "_Point") -> float:
        return abs(self.x - other.x)


def _waypoint(kind: FlightWaypointType) -> Any:
    return SimpleNamespace(waypoint_type=kind)


def _flight(standoff_nm: float | None, ingress_nm: float) -> Any:
    target = _Point(0)
    waypoints = (
        None
        if standoff_nm is None
        else SimpleNamespace(
            ingress=_Point(ingress_nm),
            standoff_range=nautical_miles(standoff_nm),
        )
    )
    return SimpleNamespace(
        package=SimpleNamespace(
            waypoints=waypoints, target=SimpleNamespace(position=target)
        )
    )


STRIKE = [
    _waypoint(FlightWaypointType.TAKEOFF),
    _waypoint(FlightWaypointType.JOIN),
    _waypoint(FlightWaypointType.INGRESS_STRIKE),
    _waypoint(FlightWaypointType.TARGET_POINT),
    _waypoint(FlightWaypointType.TARGET_POINT),
    _waypoint(FlightWaypointType.SPLIT),
    _waypoint(FlightWaypointType.LANDING_POINT),
]

#: The escort aims at the same place, with a point of its own on the way in.
ESCORT = [
    _waypoint(FlightWaypointType.TAKEOFF),
    _waypoint(FlightWaypointType.JOIN),
    _waypoint(FlightWaypointType.INGRESS_ESCORT),
    _waypoint(FlightWaypointType.CUSTOM),
    _waypoint(FlightWaypointType.TARGET_GROUP_LOC),
    _waypoint(FlightWaypointType.SPLIT),
    _waypoint(FlightWaypointType.LANDING_POINT),
]


def _types(waypoints: list[Any]) -> list[str]:
    return [point.waypoint_type.name for point in waypoints]


def test_the_aeroplane_stops_at_the_launch_point() -> None:
    flight = _flight(standoff_nm=150, ingress_nm=150)

    assert releases_at_ingress(flight)
    assert _types(_route_actually_flown(STRIKE, flight)) == [
        "TAKEOFF",
        "JOIN",
        "INGRESS_STRIKE",
        "SPLIT",
        "LANDING_POINT",
    ]


def test_the_escort_turns_with_it_and_keeps_its_own_point() -> None:
    flight = _flight(standoff_nm=150, ingress_nm=150)

    assert _types(_route_actually_flown(ESCORT, flight)) == [
        "TAKEOFF",
        "JOIN",
        "INGRESS_ESCORT",
        "CUSTOM",
        "SPLIT",
        "LANDING_POINT",
    ]


def test_the_solver_does_not_land_exactly_on_the_range() -> None:
    """148.2 out of a 150 nm weapon is the launch point, not a run in."""
    assert releases_at_ingress(_flight(standoff_nm=150, ingress_nm=148.2))


def test_an_ingress_the_weapon_did_not_place_is_left_alone() -> None:
    """A 15 nm weapon and a 45 nm ingress: that flight really does fly in."""
    flight = _flight(standoff_nm=15, ingress_nm=45)

    assert not releases_at_ingress(flight)
    assert _route_actually_flown(STRIKE, flight) is STRIKE


def test_a_dumb_bomb_flies_all_the_way_to_the_target() -> None:
    flight = _flight(standoff_nm=None, ingress_nm=45)

    assert not releases_at_ingress(flight)
    assert _route_actually_flown(STRIKE, flight) is STRIKE
