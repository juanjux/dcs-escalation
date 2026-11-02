"""Tanker edits cannot send non-receivers to fuel or backtrack to stale NAV points."""

from types import SimpleNamespace as NS
from typing import Any

import pytest
from dcs import Mission
from dcs.mapping import Point

from game.ato.flightplans import refueledit
from game.ato.flightplans.afac import AfacFlightPlan
from game.ato.flightplans.patrolling import PatrollingLayout
from game.ato.flightplans.refuelneed import (
    needs_refuelling,
    package_needs_tanker,
    supports_air_refuelling,
)
from game.ato.flightplans.refueledit import RefuelVerdict
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as Kind
from game.ato.flighttype import FlightType
from game.utils import feet


@pytest.fixture
def flight(monkeypatch: pytest.MonkeyPatch) -> Any:
    terrain = Mission().terrain

    def waypoint(name: str, nm: float, kind: Kind = Kind.NAV) -> FlightWaypoint:
        return FlightWaypoint(
            name, kind, Point(nm * 1852, 0, terrain), feet(17000), "RADIO"
        )

    departure = waypoint("TAKEOFF", 0, Kind.TAKEOFF)
    start, end = waypoint("SEARCH START", 60, Kind.PATROL_TRACK), waypoint(
        "SEARCH END", 50, Kind.PATROL
    )
    align = waypoint("ALIGN", 3)
    align.alt = feet(2000)
    layout = PatrollingLayout(
        departure=departure,
        nav_to=[waypoint("OUTBOUND EDIT", 40)],
        patrol_start=start,
        patrol_end=end,
        nav_from=[waypoint("STALE RETURN", 35), align],
        arrival=waypoint("LANDING", 0, Kind.LANDING_POINT),
        divert=None,
        bullseye=waypoint("BULLSEYE", 80, Kind.BULLSEYE),
        custom_waypoints=[waypoint("CUSTOM", 90)],
    )
    instance: Any = NS(
        unit_type=NS(dcs_id="A-10C_2"),
        is_helo=False,
        flight_type=FlightType.AFAC_FRONTLINE,
        package=NS(refuel_point=Point(10 * 1852, 0, terrain), flights=[]),
    )
    instance.flight_plan = AfacFlightPlan(instance, layout)
    calls = []

    class Builder:
        def __init__(self, selected: Any) -> None:
            assert selected is instance

        def refuel(self, point: Point) -> FlightWaypoint:
            return FlightWaypoint("REFUEL", Kind.REFUEL, point, feet(23000))

        def nav_path(
            self, a: Point, b: Point, altitude: Any, agl: bool
        ) -> list[FlightWaypoint]:
            calls.append((a, b, altitude, agl))
            return [
                FlightWaypoint(
                    "NAV",
                    Kind.NAV,
                    a.lerp(b, 0.5),
                    altitude,
                    "RADIO" if agl else "BARO",
                )
            ]

    monkeypatch.setattr(refueledit, "WaypointBuilder", Builder)
    instance.path_calls = calls
    return instance


@pytest.mark.parametrize("aircraft", ["MQ-9 Reaper", "AJS37", "L-39ZA"])
def test_known_non_receivers_never_get_tanker_offer_or_waypoint(
    flight: Any, aircraft: str
) -> None:
    flight.unit_type.dcs_id = aircraft
    assert not supports_air_refuelling(flight)
    assert refueledit.refuel_verdict(flight) is RefuelVerdict.NOTHING_TO_DO
    assert not refueledit.add_refuel_waypoint(flight)
    assert refueledit.can_offer_a_tanker(flight) == []
    assert not flight.path_calls
    # The planning-time guard runs before any fuel or air-wing access, too.
    assert not needs_refuelling(flight, flight.package, NS(), feet(20000), feet(20000))


def test_existing_mq9_stop_can_be_removed_without_recreating_patrol(
    flight: Any,
) -> None:
    assert refueledit.add_refuel_waypoint(flight)
    flight.unit_type.dcs_id = "MQ-9 Reaper"
    old_start = flight.flight_plan.layout.patrol_start
    assert refueledit.refuel_verdict(flight) is RefuelVerdict.REMOVE_UNSUPPORTED
    flight.package.flights = [flight]
    assert not package_needs_tanker(flight.package, NS())
    assert refueledit.remove_refuel_waypoint(flight)
    assert flight.flight_plan.layout.refuel is None
    assert flight.flight_plan.layout.patrol_start is old_start


def test_unknown_aircraft_keeps_legacy_behavior(flight: Any) -> None:
    flight.unit_type.dcs_id = "Unknown mod receiver"
    assert supports_air_refuelling(flight)


def test_add_stop_rebuilds_return_from_tanker_without_touching_mission(
    flight: Any,
) -> None:
    layout = flight.flight_plan.layout
    outbound = layout.nav_to[:]
    custom = layout.custom_waypoints[:]
    start, end, align = layout.patrol_start, layout.patrol_end, layout.nav_from[-1]
    assert refueledit.add_refuel_waypoint(flight)
    origin, destination, altitude, agl = flight.path_calls[-1]
    assert origin is layout.refuel.position
    assert destination is align.position
    assert altitude == feet(17000) and agl
    assert layout.nav_from[-1] is align
    assert layout.nav_to == outbound and layout.custom_waypoints == custom
    assert layout.patrol_start is start and layout.patrol_end is end
    assert start.alt == feet(17000) and end.alt == feet(17000)
    # All return legs continue toward home, rather than refuel -> old front NAV.
    route = [layout.refuel, *layout.nav_from, layout.arrival]
    assert [w.position.x for w in route] == sorted(
        (w.position.x for w in route), reverse=True
    )


def test_delete_through_flight_plan_also_repairs_return_navigation(flight: Any) -> None:
    layout = flight.flight_plan.layout
    assert refueledit.add_refuel_waypoint(flight)
    refuel = layout.refuel
    assert flight.flight_plan.can_delete_waypoint(refuel)
    assert flight.flight_plan.delete_waypoint(refuel)
    assert layout.refuel is None
    assert flight.path_calls[-1][0] is layout.patrol_end.position
    assert layout.nav_from[0].position.x > 10 * 1852


def test_return_altitude_does_not_use_low_align_altitude(flight: Any) -> None:
    layout = flight.flight_plan.layout
    layout.nav_from = [layout.nav_from[-1]]
    assert refueledit.add_refuel_waypoint(flight)
    assert flight.path_calls[-1][2] == feet(23000)
    assert not flight.path_calls[-1][3]
    assert layout.nav_from[-1].alt == feet(2000)


def test_return_without_alignment_routes_to_arrival(flight: Any) -> None:
    layout = flight.flight_plan.layout
    layout.nav_from = []
    assert refueledit.add_refuel_waypoint(flight)
    assert flight.path_calls[-1][1] is layout.arrival.position
    assert refueledit.remove_refuel_waypoint(flight)
    assert flight.path_calls[-1][0] is layout.patrol_end.position


def test_formation_return_routes_from_split_after_removal(flight: Any) -> None:
    from game.ato.flightplans.formationattack import FormationAttackLayout
    from game.ato.flightplans.strike import StrikeFlightPlan

    patrol = flight.flight_plan.layout
    layout = FormationAttackLayout(
        departure=patrol.departure,
        arrival=patrol.arrival,
        divert=patrol.divert,
        bullseye=patrol.bullseye,
        nav_to=patrol.nav_to,
        nav_from=patrol.nav_from,
        custom_waypoints=patrol.custom_waypoints,
        hold=None,
        join=patrol.patrol_start,
        split=patrol.patrol_end,
        refuel=None,
        ingress=patrol.patrol_start,
        targets=[patrol.patrol_end],
    )
    flight.flight_plan = StrikeFlightPlan(flight, layout)
    assert refueledit.add_refuel_waypoint(flight)
    assert layout.refuel is not None
    assert flight.path_calls[-1][0] is layout.refuel.position
    assert flight.flight_plan.delete_waypoint(layout.refuel)
    assert flight.path_calls[-1][0] is layout.split.position
    assert layout.targets == [patrol.patrol_end]


def test_failed_return_rebuild_leaves_route_unchanged(
    flight: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = flight.flight_plan.layout
    previous = layout.nav_from[:]

    def fail(*args: Any) -> Any:
        raise RuntimeError("cannot route")

    monkeypatch.setattr(refueledit, "_return_navigation", fail)
    with pytest.raises(RuntimeError, match="cannot route"):
        refueledit.add_refuel_waypoint(flight)
    assert layout.refuel is None and layout.nav_from == previous
