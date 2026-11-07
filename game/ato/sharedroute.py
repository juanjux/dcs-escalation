"""Package route sharing without sharing per-flight timing or airfield procedures."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, TYPE_CHECKING

from game.utils import feet, meters

from .flightplans.standard import StandardLayout
from .flighttype import FlightType
from .flightwaypointtype import FlightWaypointType as Wpt

if TYPE_CHECKING:
    from .flight import Flight
    from .flightwaypoint import FlightWaypoint
    from .package import Package

DEFAULT_TASKS = {FlightType.BARCAP, FlightType.TARCAP, FlightType.REFUELING}
INDIVIDUAL = {
    Wpt.TAKEOFF,
    Wpt.LANDING_POINT,
    Wpt.DIVERT,
    Wpt.BULLSEYE,
    Wpt.ASCEND_POINT,
    Wpt.DESCENT_POINT,
}
GROUND_POINTS = {
    Wpt.TARGET_POINT,
    Wpt.TARGET_SHIP,
    Wpt.PICKUP_ZONE,
    Wpt.DROPOFF_ZONE,
    Wpt.CARGO_STOP,
}


def _flying(waypoint: FlightWaypoint) -> bool:
    return (
        not _individual(waypoint)
        and not waypoint.only_for_player
        and waypoint.waypoint_type not in GROUND_POINTS
        and waypoint.alt.meters > 0
    )


def _navigation(source: FlightWaypoint, own: list[FlightWaypoint]) -> FlightWaypoint:
    waypoint = deepcopy(source)
    waypoint.altitude_is_manual = False
    if _flying(waypoint) and own:
        matching = [w for w in own if w.waypoint_type == waypoint.waypoint_type]
        nearest = min(
            matching or own,
            key=lambda w: w.position.distance_to_point(waypoint.position),
        )
        waypoint.alt = nearest.alt
        waypoint.alt_type = nearest.alt_type
        waypoint.altitude_is_manual = nearest.altitude_is_manual
    waypoint.tot = waypoint.departure_time = None
    waypoint.min_fuel = None
    return waypoint


def _separate(flight: Flight, previous: list[Flight]) -> None:
    """Shift a whole flight profile only when it overlaps an allocated profile.

    A fixed vertical order at all shared points also prevents the profiles from
    crossing between them. Different altitude references cannot be compared here.
    """
    route = [w for w in _plan(flight).waypoints if not _individual(w)]
    if _manual_profile(flight):
        return
    forbidden = []
    for other in previous:
        separation = feet(
            200
            if getattr(flight, "is_helo", False) and getattr(other, "is_helo", False)
            else 1000
        ).meters
        other_route = [w for w in _plan(other).waypoints if not _individual(w)]
        differences = [
            b.alt.meters - a.alt.meters
            for a, b in zip(route, other_route)
            if _flying(a) and _flying(b) and a.alt_type == b.alt_type
        ]
        if differences:
            forbidden.append(
                (min(differences) - separation, max(differences) + separation)
            )
    offset = 0.0
    for low, high in sorted(forbidden):
        if low + 1e-6 < offset < high - 1e-6:
            offset = high
    if offset:
        flying = [w for w in route if _flying(w)]
        doctrine = getattr(getattr(flight, "coalition", None), "doctrine", None)
        baro = [w.alt.meters for w in flying if w.alt_type == "BARO"]
        if doctrine is not None and baro:
            ceiling = max(max(baro), doctrine.max_combat_altitude.meters)
            if max(baro) + offset > ceiling + 1e-6:
                # Try below instead of exceeding the planning ceiling. Do not
                # lower AGL legs, where the existing height is terrain clearance.
                offset = 0.0
                for low, high in sorted(forbidden, reverse=True):
                    if low + 1e-6 < offset < high - 1e-6:
                        offset = low
                floor = min(min(baro), doctrine.min_combat_altitude.meters)
                if len(baro) != len(flying) or min(baro) + offset < floor - 1e-6:
                    logging.warning(
                        "Cannot vertically separate shared route for %s within altitude limits",
                        flight,
                    )
                    return
        for waypoint in route:
            if _flying(waypoint):
                waypoint.alt += meters(offset)


def _manual_profile(flight: Flight) -> bool:
    return any(w.altitude_is_manual for w in _plan(flight).waypoints if _flying(w))


def requested(package: Package) -> bool:
    override = getattr(package, "single_route_for_all_flights", None)
    if override is not None:
        return bool(override)
    flights = getattr(package, "flights", [])
    task = getattr(package, "primary_task", None)
    return bool(
        flights and (task or getattr(flights[0], "flight_type", None)) in DEFAULT_TASKS
    )


def _plan(flight: Flight) -> Any:
    builder = getattr(flight, "_flight_plan_builder", None)
    return (
        builder.existing_flight_plan
        if builder is not None
        else getattr(flight, "flight_plan", None)
    )


def _individual(waypoint: FlightWaypoint) -> bool:
    return waypoint.waypoint_type in INDIVIDUAL or waypoint.name == "ALIGN"


def _core(plan: Any) -> list[FlightWaypoint]:
    layout = plan.layout
    navigation = {
        id(w)
        for name in ("nav_to", "nav_from", "custom_waypoints")
        for w in getattr(layout, name, [])
    }
    return [w for w in plan.waypoints if id(w) not in navigation and not _individual(w)]


def unavailable_reason(package: Package) -> str | None:
    flights = getattr(package, "flights", [])
    if not flights:
        return "Add a flight before selecting a shared route."
    if any(
        getattr(f, "flight_type", None) in {FlightType.ESCORT, FlightType.SEAD_ESCORT}
        for f in flights
    ):
        return "Escort and SEAD Escort flights require their own dedicated waypoints."
    if any(
        not getattr(getattr(f, "state", None), "is_waiting_for_start", True)
        for f in flights
    ):
        return "Routes cannot be shared while flights are active."
    plans = [_plan(f) for f in flights]
    if any(p is None for p in plans):
        return "Flight plans must be generated before sharing their routes."
    if any(not isinstance(getattr(p, "layout", None), StandardLayout) for p in plans):
        return (
            "These custom or special flight plans do not have compatible route layouts."
        )
    signatures = [tuple(w.waypoint_type for w in _core(p)) for p in plans]
    if any(s != signatures[0] for s in signatures[1:]):
        return (
            "Flights have different mission waypoints and cannot share a single route."
        )
    return None


def enabled(package: Package) -> bool:
    return requested(package) and unavailable_reason(package) is None


def synchronize(package: Package, source: Flight | None = None) -> list[Flight]:
    """Use the edited flight as the route authority; regeneration uses the first flight.

    Only already-built plans are inspected, so this cannot recursively build another
    flight. Each flight keeps its own altitude profile, waypoint objects, targets,
    fuel and TOT data. Manual profiles keep their heights; automatic profiles are
    separated around them only when needed.
    """
    if not enabled(package):
        return []
    source = source or package.flights[0]
    if not any(f is source for f in package.flights):
        return []
    plan = _plan(source)
    core = _core(plan)
    changed = []
    for flight in package.flights:
        if flight is source:
            continue
        other = _plan(flight)
        own_route = [w for w in other.waypoints if _flying(w)]
        for name in ("nav_to", "nav_from", "custom_waypoints"):
            old = getattr(other.layout, name)
            own = [w for w in old if _individual(w)]
            existing = [w for w in old if not _individual(w)]
            altitudes = [w for w in old if _flying(w)] or own_route
            incoming = [w for w in getattr(plan.layout, name) if not _individual(w)]
            shared = [
                _navigation(
                    w,
                    (
                        [existing[index]]
                        if len(existing) == len(incoming) and _flying(existing[index])
                        else altitudes
                    ),
                )
                for index, w in enumerate(incoming)
            ]
            setattr(other.layout, name, shared + own)
        for original, counterpart in zip(core, _core(other)):
            counterpart.position = original.position.new_in_same_map(
                original.position.x, original.position.y
            )
            counterpart.custom_name = original.custom_name
        changed.append(flight)
    allocated = [f for f in package.flights if _manual_profile(f)]
    for flight in [source, *changed]:
        if any(flight is other for other in allocated):
            continue
        _separate(flight, allocated)
        allocated.append(flight)
    return changed


def set_enabled(package: Package, value: bool) -> list[Flight]:
    if value:
        reason = unavailable_reason(package)
        if reason:
            raise ValueError(reason)
    package.single_route_for_all_flights = value
    return synchronize(package) if value else []
