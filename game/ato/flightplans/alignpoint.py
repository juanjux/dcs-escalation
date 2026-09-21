"""A waypoint on the extended centreline, so the last leg is already lined up.

The route ends at the airfield itself, which is a point and not a direction: the
flight arrives on whatever heading the previous leg happened to leave it on, and
lining up with the runway is the player's problem at the worst moment to have one.

So a waypoint goes in before it, on the approach course and a few miles out. The
course is the active runway's, which the campaign already works out from the wind --
the same answer the kneeboard and the ATC give -- so the point is where the aeroplane
would be if it were already established.

Airfields only. A FARP has no runway, and a carrier is both moving and flown to by a
pattern rather than a straight-in, so neither gets one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.utils import Distance, feet, nautical_miles

if TYPE_CHECKING:
    from game.ato.flight import Flight

#: How far out it sits, and how high. Three degrees of glideslope is about 300 ft a
#: mile, which is the number the altitude is worked out from; the floor and ceiling
#: keep a short or a long setting inside the range a run-in is actually flown at.
DEFAULT_DISTANCE_NM = 10.0
FEET_PER_NAUTICAL_MILE = 300.0
MIN_ALTITUDE_FT = 1500.0
MAX_ALTITUDE_FT = 6000.0


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


def align_waypoint(flight: Flight) -> Optional[FlightWaypoint]:
    """The waypoint, or None when this flight is not one to have one.

    Guarded throughout: a flight plan that cannot be given an approach fix is a flight
    plan that goes without one, never one that fails to build.
    """
    from game.theater.controlpoint import Airfield

    settings = flight.coalition.game.settings
    if not wanted(settings):
        return None
    arrival = flight.arrival
    if not isinstance(arrival, Airfield):
        return None

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


def add_to(flight: Flight, layout: object) -> None:
    """Put one at the end of the way home, if this flight is to have one."""
    nav_from = getattr(layout, "nav_from", None)
    if nav_from is None:
        # Not a layout that flies home along a nav leg -- a custom plan, say.
        return
    waypoint = align_waypoint(flight)
    if waypoint is not None:
        nav_from.append(waypoint)
