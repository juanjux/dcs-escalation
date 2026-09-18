"""Leg distances down the waypoint table, and what the route total leaves out.

Target points and the bullseye are in the list but not on the ground track. They show
0, and the leg after one is measured from the last waypoint actually flown.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from game.ato.flightwaypointtype import FlightWaypointType
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import leg_distances

#: One nautical mile in metres, so the arithmetic below reads in the unit the column
#: is labelled with.
NM = 1852.0


def _waypoint(kind: FlightWaypointType, metres_from_origin: float) -> MagicMock:
    waypoint = MagicMock()
    waypoint.waypoint_type = kind
    waypoint.position.distance_to_point = lambda other: abs(
        other.x - metres_from_origin
    )
    waypoint.position.x = metres_from_origin
    return waypoint


def test_the_first_waypoint_has_no_leg() -> None:
    legs, total = leg_distances([_waypoint(FlightWaypointType.TAKEOFF, 0.0)])
    assert legs == [None]
    assert total == 0.0


def test_each_leg_is_measured_from_the_one_before() -> None:
    legs, total = leg_distances(
        [
            _waypoint(FlightWaypointType.TAKEOFF, 0.0),
            _waypoint(FlightWaypointType.NAV, 10 * NM),
            _waypoint(FlightWaypointType.LANDING_POINT, 25 * NM),
        ]
    )
    assert legs[1] is not None and round(legs[1]) == 10
    assert legs[2] is not None and round(legs[2]) == 15
    assert round(total) == 25


def test_a_target_neither_ends_a_leg_nor_starts_one() -> None:
    legs, total = leg_distances(
        [
            _waypoint(FlightWaypointType.TAKEOFF, 0.0),
            _waypoint(FlightWaypointType.INGRESS_STRIKE, 40 * NM),
            _waypoint(FlightWaypointType.TARGET_POINT, 41 * NM),
            _waypoint(FlightWaypointType.TARGET_POINT, 42 * NM),
            _waypoint(FlightWaypointType.EGRESS, 60 * NM),
        ]
    )
    assert legs[2] is None and legs[3] is None
    # Measured from the ingress, not from the last aimpoint.
    assert legs[4] is not None and round(legs[4]) == 20
    assert round(total) == 60


def test_the_bullseye_is_not_on_the_route() -> None:
    legs, total = leg_distances(
        [
            _waypoint(FlightWaypointType.TAKEOFF, 0.0),
            _waypoint(FlightWaypointType.LANDING_POINT, 30 * NM),
            _waypoint(FlightWaypointType.BULLSEYE, 500 * NM),
        ]
    )
    assert legs[2] is None
    assert round(total) == 30


def _patrol_plan(
    start: MagicMock, end: MagicMock, flown_nm: float, hours: float = 2.0
) -> MagicMock:
    """A plan that charges its patrol leg as the laps actually flown."""
    plan = MagicMock()
    plan.layout.patrol_start = start
    plan.layout.patrol_end = end
    plan.patrol_duration = timedelta(hours=hours)

    def between(a: MagicMock, b: MagicMock) -> MagicMock:
        distance = MagicMock()
        if a is start and b is end:
            distance.nautical_miles = flown_nm
        else:
            distance.nautical_miles = abs(b.position.x - a.position.x) / NM
        return distance

    plan.fuel_burn_distance_between_points = between
    return plan


def test_the_total_counts_the_laps_the_plan_says_it_flies() -> None:
    """The fuel bar beside this figure has always charged them."""
    start = _waypoint(FlightWaypointType.PATROL_TRACK, 0.0)
    end = _waypoint(FlightWaypointType.PATROL, 10 * NM)
    plan = _patrol_plan(start, end, flown_nm=140.0)

    _, total = leg_distances([start, end], plan)

    assert total == 140.0


def test_the_racetrack_says_how_many_times_round() -> None:
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import patrol_note

    start = _waypoint(FlightWaypointType.PATROL_TRACK, 0.0)
    end = _waypoint(FlightWaypointType.PATROL, 10 * NM)
    flight = MagicMock()
    # A 10 nm track is a 20 nm circuit, so 140 nm of flying is seven times round.
    flight.flight_plan = _patrol_plan(start, end, flown_nm=140.0)

    assert patrol_note(flight, end) == "x7 laps, 2 h"
    assert patrol_note(flight, start) is None


def test_one_lap_drops_the_count_but_still_says_how_long() -> None:
    """ "x1 laps" says nothing; how long it holds still does."""
    start = _waypoint(FlightWaypointType.PATROL_TRACK, 0.0)
    end = _waypoint(FlightWaypointType.PATROL, 10 * NM)
    flight = MagicMock()
    flight.flight_plan = _patrol_plan(start, end, flown_nm=20.0)

    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import patrol_note

    assert patrol_note(flight, end) == "2 h"
