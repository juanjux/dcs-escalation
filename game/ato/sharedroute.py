"""Package route sharing without sharing per-flight timing or airfield procedures."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING

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
    flight. Each flight keeps its own waypoint objects, targets, fuel and TOT data.
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
        for name in ("nav_to", "nav_from", "custom_waypoints"):
            own = [w for w in getattr(other.layout, name) if _individual(w)]
            shared = [
                deepcopy(w) for w in getattr(plan.layout, name) if not _individual(w)
            ]
            for waypoint in shared:
                waypoint.tot = waypoint.departure_time = None
                waypoint.min_fuel = None
            setattr(other.layout, name, shared + own)
        for original, counterpart in zip(core, _core(other)):
            counterpart.position = original.position.new_in_same_map(
                original.position.x, original.position.y
            )
            counterpart.alt = original.alt
            counterpart.alt_type = original.alt_type
            counterpart.custom_name = original.custom_name
        changed.append(flight)
    return changed


def set_enabled(package: Package, value: bool) -> list[Flight]:
    if value:
        reason = unavailable_reason(package)
        if reason:
            raise ValueError(reason)
    package.single_route_for_all_flights = value
    return synchronize(package) if value else []
