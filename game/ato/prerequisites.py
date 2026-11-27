"""Explicit scenario prerequisites selected in a coalition's ATO."""

from __future__ import annotations

from datetime import datetime, timedelta
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


def dependency_label(flight: Flight, *, package_tot: datetime | None = None) -> str:
    package = flight.package
    task = (
        "Fighter Sweep"
        if flight.flight_type is FlightType.SWEEP
        else str(flight.flight_type)
    )
    number = package.flights.index(flight) + 1
    tot = package.time_over_target if package_tot is None else package_tot
    time = "—" if tot == datetime.min else f"{tot:%H:%M}"
    return f"{task} #{number} {package.target.name} TOT {time}"


def describe(package: Package, key: UUID) -> str:
    flight = package.prerequisite_flight(key)
    return (
        dependency_label(flight)
        if flight is not None
        else f"Removed flight ({str(key)[:8]})"
    )


def depends_on_text(flight: Flight) -> str:
    keys = required_by(flight)
    if not keys:
        return ""
    return package_dependencies(flight.package, keys)


def package_dependencies(package: Package, keys: list[UUID] | None = None) -> str:
    if keys is None:
        keys = package.prerequisite_flights
    return (
        "Depends on: " + ", ".join(describe(package, key) for key in keys)
        if keys
        else ""
    )


class TimingConflict(ValueError):
    def __init__(self, message: str, adjustments: dict[Package, datetime]):
        super().__init__(message)
        self.adjustments = adjustments


def _earliest_tot(package: Package) -> datetime:
    return min(
        [package.time_over_target, *(f.flight_plan.tot for f in package.flights)]
    )


def _prerequisite_tot(flight: Flight) -> datetime:
    # A negative flight offset must not bring the dependent ahead of the
    # published package TOT. A positive offset must still be respected.
    return max(flight.package.time_over_target, flight.flight_plan.tot)


def conflicting_links(
    packages: list[Package], changed: Package, proposed: datetime
) -> list[tuple[Package, Flight]]:
    """Existing external links invalidated by an edit to either endpoint."""
    if proposed == changed.time_over_target:
        return []
    delta = proposed - changed.time_over_target
    conflicts = []
    for dependent in packages:
        for key in dependent.prerequisite_flights:
            flight = dependent.prerequisite_flight(key)
            if flight is None or flight.package is dependent:
                continue
            if dependent is changed:
                if _earliest_tot(dependent) + delta <= _prerequisite_tot(flight):
                    conflicts.append((dependent, flight))
            elif flight.package is changed:
                if _earliest_tot(dependent) <= _prerequisite_tot(flight) + delta:
                    conflicts.append((dependent, flight))
    return conflicts


def validate(
    packages: list[Package], *, adding: tuple[Package, Flight] | None = None
) -> None:
    if adding is None and not any(package.prerequisite_flights for package in packages):
        return
    by_id = {flight.id: flight for package in packages for flight in package.flights}
    graph: TopologicalSorter[Package] = TopologicalSorter()
    sources: dict[Package, list[Flight]] = {}
    for package in packages:
        keys = package.prerequisite_flights
        if adding is not None and package is adding[0]:
            keys = [*keys, adding[1].id]
        for key in keys:
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
                sources.setdefault(package, []).append(flight)
    try:
        ordered = list(graph.static_order())
    except CycleError as ex:
        chain = " → ".join(package_name(package) for package in ex.args[1])
        raise ValueError(f"Circular mission dependency: {chain}") from ex
    adjustments: dict[Package, datetime] = {}
    message = ""
    for package in ordered:
        required = sources.get(package)
        if not required:
            continue
        if package.time_over_target == datetime.min or any(
            f.package.time_over_target == datetime.min for f in required
        ):
            raise ValueError(
                f"Set a TOT for {package_name(package)} and its prerequisite packages."
            )
        deadline = max(
            _prerequisite_tot(f)
            + (
                adjustments.get(f.package, f.package.time_over_target)
                - f.package.time_over_target
            )
            for f in required
        )
        earliest = _earliest_tot(package)
        if earliest <= deadline:
            threshold = package.time_over_target + (deadline - earliest)
            conflict = (
                "To match the pre-requisite flights, this package needs a TOT "
                f"later than {threshold:%H:%M:%S}."
            )
            if (
                adding is not None
                and package is not adding[0]
                and not any(f.package in adjustments for f in required)
            ):
                raise ValueError(conflict)
            if not message:
                message = conflict
            adjustments[package] = threshold.replace(
                second=0, microsecond=0
            ) + timedelta(minutes=1)
    if adjustments:
        raise TimingConflict(message, adjustments)


def add(
    package: Package,
    flight: Flight,
    packages: list[Package],
    *,
    approved_times: dict[Package, datetime] | None = None,
) -> None:
    if flight.id in package.prerequisite_flights:
        raise ValueError("This flight is already a prerequisite.")
    if package not in packages:
        raise ValueError("The dependent package is missing from the ATO.")
    try:
        validate(packages, adding=(package, flight))
    except TimingConflict as conflict:
        if conflict.adjustments != approved_times:
            raise
        if not all(p.all_flights_waiting_for_start() for p in conflict.adjustments):
            raise ValueError("A package has already started and its TOT is locked.")
        for changed, when in conflict.adjustments.items():
            changed.time_over_target = when
            changed.auto_asap = False
    package.prerequisite_flights.append(flight.id)


WAIT_NAME = "Wait for DEAD/Fighter Sweep"
