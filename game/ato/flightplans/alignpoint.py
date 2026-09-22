"""Adds an approach waypoint ahead of the landing waypoint.

The route ends at the airfield, which is a position and not a direction, so the final
leg arrives on whatever heading the previous leg left. This module adds a waypoint on
the approach course of the active runway, a configurable distance out, so the flight
is lined up before it gets there.

The active runway is the campaign's own wind-based choice, the same one used by the
kneeboard and the ATC.

Carriers get the same thing on their base recovery course, which is the reciprocal of
the wind, positioned where the ship will be when the flight lands. The ship holds that
course for the whole mission, so a late arrival still finds the waypoint on the final
bearing, only further from the ship than planned.

DCS exposes a runway's heading but no coordinates, so the waypoint is placed relative
to the airfield's reference point. At a field with one runway that is the runway; at a
field with several the course is correct but the waypoint can be laterally offset.

FARPs have no runway and get nothing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.utils import (
    Distance,
    Heading,
    Speed,
    feet,
    knots,
    meters,
    mps,
    nautical_miles,
)

if TYPE_CHECKING:
    from game.ato.flight import Flight

#: Default distance from the field. The altitude follows from it: a three-degree
#: glideslope is about 300 ft per nautical mile, and the floor and ceiling keep the
#: result within the range an approach is flown at. The ceiling also matches a Case III
#: marshal altitude, which is what 50 nm on the slope works out to.
DEFAULT_DISTANCE_NM = 15.0
DEFAULT_CARRIER_DISTANCE_NM = 50.0
FEET_PER_NAUTICAL_MILE = 300.0
MIN_ALTITUDE_FT = 1500.0
MAX_ALTITUDE_FT = 6000.0

#: What the mission generator gives a carrier group: 25 knots over the deck, made by
#: steaming at 25 knots less whatever the wind provides. Read here as well so the
#: waypoint matches where the ship will actually be.
DECK_SPEED = knots(25)

#: The generator gives the ship a single leg of 100 km, shortened where there is land
#: in the way. It stops at the end of it, so the assumed progress is capped there.
MAX_STEAMED = meters(100000)


def altitude_for(distance: Distance) -> Distance:
    """Height above the field on a three-degree slope from that distance."""
    on_the_slope = distance.nautical_miles * FEET_PER_NAUTICAL_MILE
    return feet(min(MAX_ALTITUDE_FT, max(MIN_ALTITUDE_FT, on_the_slope)))


def wanted(settings: object) -> bool:
    return bool(getattr(settings, "align_before_landing", False))


def distance_from(settings: object) -> Distance:
    return nautical_miles(
        float(getattr(settings, "align_distance_nm", DEFAULT_DISTANCE_NM))
    )


def carrier_distance_from(settings: object) -> Distance:
    return nautical_miles(
        float(
            getattr(settings, "align_carrier_distance_nm", DEFAULT_CARRIER_DISTANCE_NM)
        )
    )


def base_recovery_course(conditions: Any) -> Optional[Heading]:
    """The ship's course: into the wind, so the reciprocal of the wind vector.

    Takes the same reading as the mission generator when it sets the ship's course,
    so the waypoint and the ship agree.
    """
    try:
        wind = conditions.weather.wind.at_0m
        return Heading.from_degrees(int(wind.direction)).opposite
    except Exception:
        return None


def steaming_speed(conditions: Any) -> Speed:
    """25 knots over the deck, less whatever the wind provides."""
    try:
        made_good = DECK_SPEED - mps(conditions.weather.wind.at_0m.speed)
    except Exception:
        return DECK_SPEED
    return made_good if made_good.meters_per_second > 0 else knots(0)


def _airfield_waypoint(
    flight: Flight, arrival: Any, settings: Any
) -> Optional[FlightWaypoint]:
    try:
        runway = arrival.active_runway(
            arrival.theater, flight.coalition.game.conditions, {}
        )
    except Exception:
        return None
    if not runway.runway_name:
        # A stub, which is what a field with no runways in its data returns.
        return None

    distance = distance_from(settings)
    # The approach course is the runway heading, so the waypoint goes that distance
    # back along its reciprocal.
    position = arrival.position.point_from_heading(
        runway.runway_heading.opposite.degrees, distance.meters
    )
    return FlightWaypoint(
        "ALIGN",
        FlightWaypointType.NAV,
        position,
        altitude_for(distance),
        alt_type="RADIO",
        description=f"Established on {arrival.name} runway {runway.runway_name}",
        pretty_name="Align with the runway",
    )


def _recovery_delay(plan: Any, conditions: Any) -> Optional[timedelta]:
    """Time from mission start to this flight's landing.

    Read off the plan as built, which is one waypoint short of the finished one. The
    leg this adds is worth a minute or two of the ship's progress and does not move
    the waypoint off the final bearing.
    """
    try:
        return plan.landing_time - conditions.start_time
    except Exception:
        return None


def _carrier_waypoint(
    flight: Flight, arrival: Any, settings: Any, plan: Any
) -> Optional[FlightWaypoint]:
    conditions = flight.coalition.game.conditions
    course = base_recovery_course(conditions)
    delay = _recovery_delay(plan, conditions)
    if course is None or delay is None or delay.total_seconds() < 0:
        return None

    steamed = min(
        meters(steaming_speed(conditions).meters_per_second * delay.total_seconds()),
        MAX_STEAMED,
    )
    recovery = arrival.position.point_from_heading(course.degrees, steamed.meters)

    distance = carrier_distance_from(settings)
    position = recovery.point_from_heading(course.opposite.degrees, distance.meters)
    return FlightWaypoint(
        "ALIGN",
        FlightWaypointType.NAV,
        position,
        altitude_for(distance),
        alt_type="RADIO",
        description=(
            f"{arrival.name} final bearing {course.degrees:03}, "
            f"{distance.nautical_miles:.0f} nm astern of its projected position"
        ),
        pretty_name="Align with the recovery course",
    )


def align_waypoint(flight: Flight, plan: Any = None) -> Optional[FlightWaypoint]:
    """The waypoint, or None if this flight does not get one.

    Fully guarded: a flight plan that cannot be given an approach waypoint goes
    without one rather than failing to build.
    """
    from game.theater.controlpoint import Airfield, NavalControlPoint

    settings = flight.coalition.game.settings
    if not wanted(settings):
        return None
    arrival = flight.arrival
    if isinstance(arrival, Airfield):
        return _airfield_waypoint(flight, arrival, settings)
    if isinstance(arrival, NavalControlPoint) and plan is not None:
        return _carrier_waypoint(flight, arrival, settings, plan)
    return None


def add_to(flight: Flight, plan: Any) -> None:
    """Append the waypoint to the end of the return leg, if this flight gets one."""
    nav_from = getattr(getattr(plan, "layout", None), "nav_from", None)
    if nav_from is None:
        # Not a layout with a nav leg home, e.g. a custom plan.
        return
    waypoint = align_waypoint(flight, plan)
    if waypoint is not None:
        nav_from.append(waypoint)
