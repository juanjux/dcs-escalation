"""Optional tanker stops before an attack or CAP station.

Adapted from RetLab #1153, #1156 and #1171. Authored boom/probe profiles in
resources/air_refuelling.json are adapted from RetLab's aircraft definitions.
Unknown receivers and tankers are not guessed compatible for this new option.
"""

from __future__ import annotations

import json
from datetime import timedelta
from functools import cache
from pathlib import Path
from typing import Any, TYPE_CHECKING

from game.ato.flighttype import FlightType
from game.ato.fuelestimate import estimate_fuel_segments

if TYPE_CHECKING:
    from dcs import Point

    from game.ato.flight import Flight
    from game.ato.flightwaypoint import FlightWaypoint
    from game.dcs.aircrafttype import AircraftType


@cache
def profiles() -> dict[str, dict[str, Any]]:
    with Path("resources/air_refuelling.json").open(encoding="utf-8") as stream:
        return dict(json.load(stream))


def compatible(receiver: AircraftType, tanker: AircraftType) -> bool:
    method = profiles().get(receiver.dcs_id, {}).get("air_refuel_type")
    offered = profiles().get(tanker.dcs_id, {}).get("tanker_refuel_types", [])
    return method in {"boom", "probe"} and method in offered


def planned_tanker(flight: Flight, near: Point) -> Flight | None:
    """Nearest compatible theater tanker, never a post-strike package tanker."""
    from game.ato.flightplans.theaterrefueling import TheaterRefuelingFlightPlan

    if flight.is_helo:
        return None
    candidates = []
    for package in flight.coalition.ato.packages:
        if package is flight.package:
            continue
        for other in package.flights:
            if other.flight_type is not FlightType.REFUELING:
                continue
            if not compatible(flight.unit_type, other.unit_type):
                continue
            plan = other.flight_plan
            if isinstance(plan, TheaterRefuelingFlightPlan):
                candidates.append(other)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda other: other.flight_plan.layout.patrol_start.position.distance_to_point(
            near
        ),
    )


def build_stop(flight: Flight, near: Point) -> FlightWaypoint | None:
    from game.ato.flightplans.waypointbuilder import WaypointBuilder

    if not getattr(flight, "refuel_before_push", False):
        return None
    tanker = planned_tanker(flight, near)
    if tanker is None:
        return None
    station = tanker.flight_plan.layout.patrol_start
    point = WaypointBuilder(flight).refuel(
        station.position.new_in_same_map(station.position.x, station.position.y)
    )
    point.alt = station.alt
    point.alt_type = station.alt_type
    point.pretty_name = (
        "Refuel (before station)"
        if flight.flight_type in {FlightType.BARCAP, FlightType.TARCAP}
        else "Refuel (before push)"
    )
    point.description = "Refuel from the theater tanker before the mission"
    return point


def tanking_time(flight: Flight) -> timedelta:
    minutes = getattr(flight, "tanking_minutes", None)
    if minutes is None:
        minutes = 4 * flight.count + 1
    return timedelta(minutes=minutes)


def remove_unneeded_post_stop(flight: Flight) -> bool:
    """Keep the second stop unless the actual route gets home on the first top-off."""
    layout = flight.flight_plan.layout
    post = getattr(layout, "refuel", None)
    if post is None or getattr(layout, "pre_push_refuel", None) is None:
        return False
    layout.refuel = None
    try:
        segments = estimate_fuel_segments(flight)
        unneeded = len(segments) >= 2 and all(segment.enough for segment in segments)
    except Exception:
        layout.refuel = post
        raise
    if not unneeded:
        layout.refuel = post
    return unneeded
