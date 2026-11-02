"""Relocation ferries must reach the map before they can be selected."""

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from game.ato import FlightType
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.squadrons.squadron import Squadron

NOW = datetime(2026, 11, 1, 12)


class Flight:
    def __init__(self, squadron: Any, size: int, task: FlightType) -> None:
        self.id = uuid4()
        self.squadron = squadron
        self.count = size
        self.flight_type = task


class Package:
    def __init__(self, target: Any, db: Any) -> None:
        self.target = target
        self.flights: list[Any] = []
        self.time_over_target = datetime.min

    def remove_flight(self, flight: Any) -> None:
        self.flights.remove(flight)
        flight.squadron.untasked_aircraft += flight.count

    def set_tot_asap(self, now: datetime) -> None:
        self.time_over_target = now


class RelocatingSquadron(SimpleNamespace):
    plan_ferry_flights = Squadron.plan_ferry_flights
    cancel_ferry_flights = Squadron.cancel_ferry_flights
    replan_ferry_flights = Squadron.replan_ferry_flights

    def plan_ferry_flight(self, package: Any, size: int) -> None:
        package.flights.append(Flight(self, size, FlightType.FERRY))
        self.untasked_aircraft -= size


@pytest.fixture
def world(monkeypatch: Any) -> Any:
    published: list[GameUpdateEvents] = []
    monkeypatch.setattr(EventStream, "put_nowait", published.append)
    monkeypatch.setattr("game.squadrons.squadron.Package", Package)
    packages: list[Any] = []
    squadron = RelocatingSquadron(
        destination=object(),
        untasked_aircraft=9,
        aircraft=SimpleNamespace(max_group_size=4),
        flight_db=object(),
        coalition=SimpleNamespace(
            ato=SimpleNamespace(
                packages=packages,
                add_package=packages.append,
                remove_package=packages.remove,
            )
        ),
    )
    return SimpleNamespace(squadron=squadron, events=published, packages=packages)


def test_new_ferries_are_registered_with_the_map_after_planning(world: Any) -> None:
    world.squadron.plan_ferry_flights(NOW)

    package = world.packages[0]
    assert [flight.count for flight in package.flights] == [4, 4, 1]
    assert package.time_over_target == NOW
    assert len(world.events) == 1
    assert world.events[0].new_flights == set(package.flights)
    assert not world.events[0].deleted_flights


def test_cancellation_deletes_only_this_squadrons_ferries(world: Any) -> None:
    squadron = world.squadron
    other = RelocatingSquadron(untasked_aircraft=0)
    removed = [Flight(squadron, 2, FlightType.FERRY) for _ in range(2)]
    patrol = Flight(squadron, 2, FlightType.BARCAP)
    unrelated = Flight(other, 2, FlightType.FERRY)
    for flights in ([removed[0]], [removed[1]], [patrol, unrelated]):
        package = Package(None, None)
        package.flights.extend(flights)
        world.packages.append(package)

    squadron.cancel_ferry_flights()

    assert [p.flights for p in world.packages] == [[patrol, unrelated]]
    assert len(world.events) == 1
    assert world.events[0].deleted_flights == {f.id for f in removed}
    assert not world.events[0].new_flights


def test_replanning_removes_old_routes_and_registers_replacements(world: Any) -> None:
    squadron = world.squadron
    squadron.plan_ferry_flights(NOW)
    old_ids = {flight.id for flight in world.packages[0].flights}
    world.events.clear()
    squadron.destination = object()

    squadron.replan_ferry_flights(NOW)

    assert len(world.packages) == 1
    replacement = world.packages[0]
    assert replacement.target is squadron.destination
    assert len(world.events) == 2
    assert world.events[0].deleted_flights == old_ids
    assert world.events[1].new_flights == set(replacement.flights)
    assert old_ids.isdisjoint(f.id for f in replacement.flights)


def test_no_aircraft_or_no_ferries_does_not_publish_empty_events(world: Any) -> None:
    world.squadron.untasked_aircraft = 0
    world.squadron.plan_ferry_flights(NOW)
    world.squadron.cancel_ferry_flights()

    assert not world.packages
    assert not world.events


def test_failed_planning_does_not_register_an_incomplete_package(
    world: Any, monkeypatch: Any
) -> None:
    def fail(package: Any, now: datetime) -> None:
        raise RuntimeError("Cannot plan route")

    monkeypatch.setattr(Package, "set_tot_asap", fail)
    with pytest.raises(RuntimeError, match="Cannot plan route"):
        world.squadron.plan_ferry_flights(NOW)

    assert not world.packages
    assert not world.events
