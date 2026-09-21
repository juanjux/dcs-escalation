"""A waypoint on the extended centreline, so the last leg is already lined up.

The route ends at the field itself, which is a point and not a direction: the flight
arrives on whatever heading the previous leg happened to leave it on, and lining up
is the player's problem at the worst moment to have one.

So a waypoint goes in before it, on the approach course and a few miles out. The
course is the active runway's, which the campaign already works out from the wind --
the same answer the kneeboard and the ATC give -- so the point is where the aeroplane
would be if it were already established.

A carrier gets one too, further out, because that is what a Case III recovery is. Its
course is the base recovery course, which is simply the reciprocal of the wind, and
its position is where the ship will have steamed to by the time the flight lands: the
carrier holds that course for the whole mission, so a flight that arrives late finds
the point still on the final bearing, only further behind the ship than planned.

DCS gives us the heading of a runway and nothing else about it -- no threshold, no
centreline -- so the point is drawn through the airfield's own reference point. At a
field with one strip that is the strip. At a field with several the course is right
and the line can sit beside the tarmac rather than on it.

A FARP has no runway at all, so it gets nothing.
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

#: How far out it sits, and how high. Three degrees of glideslope is about 300 ft a
#: mile, which is the number the altitude is worked out from; the floor and ceiling
#: keep a short or a long setting inside the range a run-in is actually flown at. The
#: ceiling is also where a Case III marshal sits, which is what fifty miles of slope
#: comes to anyway.
DEFAULT_DISTANCE_NM = 15.0
DEFAULT_CARRIER_DISTANCE_NM = 50.0
FEET_PER_NAUTICAL_MILE = 300.0
MIN_ALTITUDE_FT = 1500.0
MAX_ALTITUDE_FT = 6000.0

#: What the mission generator gives a carrier group: twenty-five knots over the deck,
#: which it makes by steaming at that less whatever the wind is doing for it. Read
#: here as well so the point lands where the ship will actually be.
DECK_SPEED = knots(25)

#: And how far it sends her: one leg of a hundred kilometres, shortened where there is
#: land in the way. She stops at the end of it, so a long mission's marshal is not put
#: any further out than that.
MAX_STEAMED = meters(100000)


def altitude_for(distance: Distance) -> Distance:
    """Height above the field, on a three-degree slope from that far out."""
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
    """Where the ship points: into the wind, which is the reciprocal of it.

    The same reading the mission generator takes when it sets the carrier's course,
    so the point and the ship agree.
    """
    try:
        wind = conditions.weather.wind.at_0m
        return Heading.from_degrees(int(wind.direction)).opposite
    except Exception:
        return None


def steaming_speed(conditions: Any) -> Speed:
    """Twenty-five knots over the deck, less what the wind provides."""
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
        # A stub, which is what a field with no runways in its data answers with.
        return None

    distance = distance_from(settings)
    # The approach course is the runway's heading, so the fix is that far back down it.
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
    """How long after the mission starts this flight comes home.

    Read off the plan as it stands, which is one waypoint short of the finished one:
    the leg this adds is worth a minute or two of the ship's progress, and the point
    stays on the final bearing either way.
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
            f"On {arrival.name}'s final bearing {course.degrees:03}, "
            f"{distance.nautical_miles:.0f} nm astern of where she will be"
        ),
        pretty_name="Align with the recovery course",
    )


def align_waypoint(flight: Flight, plan: Any = None) -> Optional[FlightWaypoint]:
    """The waypoint, or None when this flight is not one to have one.

    Guarded throughout: a flight plan that cannot be given an approach fix is a flight
    plan that goes without one, never one that fails to build.
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
    """Put one at the end of the way home, if this flight is to have one."""
    nav_from = getattr(getattr(plan, "layout", None), "nav_from", None)
    if nav_from is None:
        # Not a layout that flies home along a nav leg -- a custom plan, say.
        return
    waypoint = align_waypoint(flight, plan)
    if waypoint is not None:
        nav_from.append(waypoint)
