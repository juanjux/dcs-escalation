"""Explicit scenario prerequisites selected in a coalition's ATO."""

from __future__ import annotations

from datetime import datetime
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING
from uuid import UUID

from .flighttype import FlightType

if TYPE_CHECKING:
    from game.theater.theatergroup import TheaterUnit
    from .flight import Flight
    from .package import Package


OBJECTIVE_FLIGHTS = {FlightType.DEAD, FlightType.SEAD}
ELIGIBLE = OBJECTIVE_FLIGHTS | {FlightType.SWEEP}


def objective_units(target: object) -> list[TheaterUnit]:
    from game.data.units import TRACKING_RADAR_CLASSES
    from game.theater import TheaterGroundObject

    if not isinstance(target, TheaterGroundObject):
        return []
    tagged = []
    for unit in target.units:
        try:
            kind = unit.unit_type
        except (KeyError, StopIteration):
            continue
        if kind is not None and kind.unit_class in TRACKING_RADAR_CLASSES:
            tagged.append(unit)
    return tagged


def outcome_flag(key: UUID) -> str:
    return f"scenario-outcome-{key}"


def package_name(package: Package) -> str:
    return package.custom_name or package.target.name


def flight_name(flight: Flight) -> str:
    package = flight.package
    number = package.flights.index(flight) + 1
    name = flight.custom_name or flight.squadron.name
    return f"{package_name(package)} · #{number} {flight.flight_type} · {name}"


def required_by(flight: Flight) -> list[UUID]:
    package = getattr(flight, "package", None)
    if package is None:
        return []
    ids = getattr(package, "prerequisite_flights", [])
    if not ids or flight.id not in ids:
        return ids.copy()
    # All selected flights within this package can go first, in parallel.
    internal = {member.id for member in package.flights}
    return [key for key in ids if key not in internal]


def describe(package: Package, key: UUID) -> str:
    flight = package.prerequisite_flight(key)
    return (
        flight_name(flight)
        if flight is not None
        else f"Removed flight ({str(key)[:8]})"
    )


def depends_on_text(flight: Flight) -> str:
    keys = required_by(flight)
    if not keys:
        return ""
    return "Depends on: " + ", ".join(describe(flight.package, key) for key in keys)


def validate(packages: list[Package]) -> None:
    if not any(package.prerequisite_flights for package in packages):
        return
    by_id = {flight.id: flight for package in packages for flight in package.flights}
    graph: TopologicalSorter[Package] = TopologicalSorter()
    pairs = []
    for package in packages:
        for key in package.prerequisite_flights:
            flight = by_id.get(key)
            if flight is None:
                raise ValueError(
                    f"{package_name(package)} depends on a flight missing from this ATO."
                )
            if flight.flight_type not in ELIGIBLE:
                raise ValueError(
                    f"{flight_name(flight)} is no longer an eligible prerequisite."
                )
            if flight.flight_type in OBJECTIVE_FLIGHTS and not objective_units(
                flight.package.target
            ):
                raise ValueError(
                    f"{flight_name(flight)} needs an assigned objective with a tracking "
                    "radar in the campaign catalogue to serve as a prerequisite."
                )
            if package is not flight.package:
                graph.add(package, flight.package)
                pairs.append((package, flight))
    try:
        graph.prepare()
    except CycleError as ex:
        chain = " → ".join(package_name(package) for package in ex.args[1])
        raise ValueError(f"Circular mission dependency: {chain}") from ex
    for package, flight in pairs:
        if datetime.min in (package.time_over_target, flight.package.time_over_target):
            raise ValueError(
                f"Set a TOT for {package_name(package)} and {flight_name(flight)}."
            )
        deadline = flight.flight_plan.tot
        for member in package.flights:
            if member.flight_plan.tot <= deadline:
                raise ValueError(
                    f"{flight_name(member)} needs a TOT later than {flight_name(flight)} "
                    f"({deadline:%H:%M:%S})."
                )
        if package.time_over_target <= deadline:
            raise ValueError(
                f"{package_name(package)} needs a package TOT later than "
                f"{flight_name(flight)} ({deadline:%H:%M:%S})."
            )


def add(package: Package, flight: Flight, packages: list[Package]) -> None:
    if flight.id in package.prerequisite_flights:
        raise ValueError("This flight is already a prerequisite.")
    if package not in packages:
        raise ValueError("The dependent package is missing from the ATO.")
    package.prerequisite_flights.append(flight.id)
    try:
        validate(packages)
    except Exception:
        package.prerequisite_flights.remove(flight.id)
        raise


WAIT_NAME = "Wait for DEAD/Fighter Sweep"
