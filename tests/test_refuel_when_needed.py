"""A tanker and a refuelling waypoint only for a package that needs the fuel.

Three things were wrong at once.

The refuelling WAYPOINT went onto every non-helicopter flight of any faction that
owned a tanker, whether it could fly the plan twice over or not. The tanker FLIGHT
the auto-planner proposed for Strike, OCA and DEAD was pruned every time, because
check_needed_escorts never set EscortType.Refuel. And when both were fixed, the two
halves asked two DIFFERENT questions: the tanker was bought on estimate_fuel's answer
and the waypoint withheld on a cheaper one, so the usual outcome was a tanker orbiting
alone while the flight that paid for it flew on with nothing to meet.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from game.ato.flightplans import refuelneed
from game.ato.flightplans.refuelneed import (
    has_refuel_waypoint,
    needs_refuelling,
    package_needs_tanker,
    planned_legs,
    planned_route_nm,
)
from game.ato.fuelestimate import Leg, burn_for, fuel_for_route
from game.dcs.aircrafttype import FuelConsumption
from game.utils import feet, meters, nautical_miles

METRES_PER_NM = 1852.0
CRUISE = feet(25000)  # the band the measured cruise figures correspond to
LOW = feet(9000)  # where a strike's ingress actually is, and where it costs most


class _Point:
    def __init__(self, x: float) -> None:
        self.x, self.y = x, 0.0

    def distance_to_point(self, other: Any) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


def _flight(
    *, internal_lb: float = 10000.0, helo: bool = False, tankers: bool = True
) -> Any:
    consumption = FuelConsumption(
        taxi=200, climb=48, cruise=20, combat=36, min_safe=1500
    )
    member = SimpleNamespace(loadout=SimpleNamespace(pylons={}))
    return SimpleNamespace(
        unit_type=SimpleNamespace(fuel_consumption=consumption, helicopter=helo),
        roster=SimpleNamespace(members=[member]),
        fuel=internal_lb / 2.20462,  # kg, the unit Flight.fuel uses
        is_helo=helo,
        departure=SimpleNamespace(position=_Point(0)),
        arrival=SimpleNamespace(position=_Point(0)),
        coalition=SimpleNamespace(
            air_wing=SimpleNamespace(can_auto_plan=lambda _task: tankers),
            game=SimpleNamespace(settings=SimpleNamespace()),
            player=object(),
        ),
    )


def _package(target_nm: float, *, defending: bool = False) -> Any:
    far = _Point(target_nm * METRES_PER_NM)
    return SimpleNamespace(
        target=SimpleNamespace(position=far, is_friendly=lambda _player: defending),
        waypoints=SimpleNamespace(join=_Point(0), ingress=far, split=far),
        flights=[],
    )


def _settings(on: bool = True) -> Any:
    return SimpleNamespace(plan_refuelling_when_needed=on)


def _consumption() -> FuelConsumption:
    return FuelConsumption(taxi=200, climb=48, cruise=20, combat=36, min_safe=1500)


# --- the rate model, which is where the two halves disagreed ----------------


def test_the_same_route_costs_more_down_low() -> None:
    """The correction estimate_fuel applies and the planning-time one did not."""
    high = burn_for(_consumption(), [Leg(100, CRUISE.feet)], helicopter=False)
    low = burn_for(_consumption(), [Leg(100, LOW.feet)], helicopter=False)
    assert low > high * 1.2, f"{high} -> {low}"


def test_the_run_in_is_charged_at_the_combat_rate() -> None:
    plain = burn_for(_consumption(), [Leg(50, LOW.feet)], helicopter=False)
    attacking = burn_for(
        _consumption(), [Leg(50, LOW.feet, attack=True)], helicopter=False
    )
    assert attacking > plain


def test_the_climb_is_not_corrected_twice() -> None:
    """The climb rate already covers the whole climb."""
    assert burn_for(
        _consumption(), [Leg(25, LOW.feet, climb=True)], helicopter=False
    ) == pytest.approx(25 * 48)


def test_a_route_flown_low_can_need_a_tanker_where_one_flown_high_does_not() -> None:
    """The regression itself: a flat cruise rate called this flight comfortable.

    9,130 lb at the reference band, 11,337 lb at 9,000 ft, on the same 150 nm target.
    Carrying 10,500 lb the answer is different at each, and it used to be the high one
    for both.
    """
    flight, package = _flight(internal_lb=10500), _package(150)
    assert not needs_refuelling(flight, package, _settings(), CRUISE, CRUISE)
    assert needs_refuelling(flight, package, _settings(), LOW, LOW)


# --- the geometry ----------------------------------------------------------


def test_the_route_is_out_and_back_not_a_straight_line() -> None:
    """With the slack on top: the real plan holds, joins and routes around threats,
    so the geometry is a floor and is deliberately charged a little long."""
    from game.ato.flightplans.refuelneed import ROUTE_SLACK

    assert planned_route_nm(_flight(), _package(100)) == pytest.approx(
        200 * ROUTE_SLACK, rel=0.01
    )


def test_a_patrol_pays_for_its_laps() -> None:
    """A TARCAP burns most of its fuel on station, and it was not counted at all."""
    flight, package = _flight(), _package(80)
    without = planned_legs(flight, package, CRUISE, CRUISE)
    with_laps = planned_legs(
        flight, package, CRUISE, CRUISE, on_station=nautical_miles(200)
    )
    assert sum(l.nautical_miles for l in with_laps) == pytest.approx(
        sum(l.nautical_miles for l in without) + 200
    ), "the laps are charged once, without the route slack on top of them"
    assert not needs_refuelling(flight, package, _settings(), CRUISE, CRUISE)
    assert needs_refuelling(
        flight, package, _settings(), CRUISE, CRUISE, nautical_miles(600)
    )


# --- the gate --------------------------------------------------------------


def test_a_short_hop_does_not_need_a_tanker() -> None:
    assert fuel_for_route(
        _flight(), planned_legs(_flight(), _package(25), CRUISE, CRUISE)
    ).enough


def test_the_waypoint_is_only_for_a_flight_that_runs_short() -> None:
    assert not needs_refuelling(_flight(), _package(60), _settings(), CRUISE, CRUISE)
    assert needs_refuelling(_flight(), _package(400), _settings(), CRUISE, CRUISE)


def test_the_campaign_can_switch_the_whole_idea_off() -> None:
    assert not needs_refuelling(
        _flight(), _package(400), _settings(on=False), CRUISE, CRUISE
    )


def test_a_helicopter_is_never_given_one() -> None:
    """It cannot use the boom, and the tanker's track is not where it flies."""
    assert not needs_refuelling(
        _flight(helo=True), _package(400), _settings(), CRUISE, CRUISE
    )


def test_a_faction_with_no_tanker_is_not_offered_one() -> None:
    assert not needs_refuelling(
        _flight(tankers=False), _package(400), _settings(), CRUISE, CRUISE
    )


def test_an_attack_package_with_no_waypoints_yet_asks_for_nothing() -> None:
    """Halfway to an enemy target is not a place to send a tanker, and a package that
    has not solved its geometry cannot say where else to."""
    flight = _flight()
    package = _package(400)
    package.waypoints = None
    assert not needs_refuelling(flight, package, _settings(), CRUISE, CRUISE)


def test_a_patrol_over_its_own_base_is_judged_without_package_geometry() -> None:
    """A defensive package never gets package waypoints -- there is no ingress to
    solve -- so judging it on those alone charged it nothing and it was never short."""
    flight = _flight(internal_lb=4000.0)
    package = _package(150, defending=True)
    package.waypoints = None
    assert needs_refuelling(
        flight,
        package,
        _settings(),
        CRUISE,
        CRUISE,
        nautical_miles(400),  # its laps, which are most of what a patrol burns
    )


# --- the tanker half, which now READS the waypoint decision -----------------


def _with_layout(flight: Any, refuel: Any) -> Any:
    flight.flight_plan = SimpleNamespace(layout=SimpleNamespace(refuel=refuel))
    return flight


def test_a_package_asks_for_a_tanker_when_a_flight_was_routed_to_meet_one() -> None:
    """One decision, made once, read twice: it cannot disagree with itself."""
    routed = _with_layout(_flight(), refuel=object())
    not_routed = _with_layout(_flight(), refuel=None)
    package = _package(400)
    package.flights = [not_routed]
    assert not package_needs_tanker(package, _settings())
    package.flights = [not_routed, routed]
    assert package_needs_tanker(package, _settings())


def test_the_setting_still_gates_the_tanker() -> None:
    package = _package(400)
    package.flights = [_with_layout(_flight(), refuel=object())]
    assert not package_needs_tanker(package, _settings(on=False))


def test_a_plan_type_with_nowhere_to_put_one_never_asks_for_a_tanker() -> None:
    """A CAS or BARCAP layout has no refuel slot; buying it a tanker is waste."""
    flight = _flight()
    flight.flight_plan = SimpleNamespace(layout=SimpleNamespace())  # no refuel at all
    package = _package(400)
    package.flights = [flight]
    assert not package_needs_tanker(package, _settings())


def test_a_flight_whose_plan_cannot_answer_is_not_a_reason_to_send_one() -> None:
    """Read before every plan exists, it must not scrub or over-plan."""
    flight = _flight()
    flight.flight_plan = None
    assert not refuelneed.has_refuel_waypoint(flight)


def test_a_patrol_has_somewhere_to_put_a_refuel_waypoint() -> None:
    """A BARCAP is the flight that orbits longest, so it is the one that most wants a
    tanker. The slot used to belong to TARCAP alone, which meant the fuel check was
    never even asked about a BARCAP."""
    from game.ato.flightplans.patrolling import PatrollingLayout
    from game.ato.flightplans.tarcap import TarCapLayout

    assert hasattr(PatrollingLayout, "refuel")
    # TARCAP keeps working through the inherited slot rather than one of its own.
    assert issubclass(TarCapLayout, PatrollingLayout)
    assert "refuel" not in TarCapLayout.__annotations__


def test_a_patrol_yields_and_forgets_its_refuel_waypoint() -> None:
    """The waypoint has to appear on the route after the last lap, and deleting it by
    hand has to actually take it off -- a stale one breaks mission generation."""
    from game.ato.flightplans.patrolling import PatrollingLayout

    def waypoint(name: str) -> Any:
        return SimpleNamespace(name=name)

    start, end = waypoint("start"), waypoint("end")
    refuel = waypoint("refuel")
    layout = PatrollingLayout(
        departure=waypoint("takeoff"),
        arrival=waypoint("land"),
        divert=None,
        bullseye=waypoint("bullseye"),
        nav_to=[],
        nav_from=[],
        custom_waypoints=[],
        patrol_start=start,
        patrol_end=end,
        refuel=refuel,
    )
    names = [wpt.name for wpt in layout.iter_waypoints()]
    assert names.index("refuel") == names.index("end") + 1

    assert layout.delete_waypoint(refuel)
    assert layout.refuel is None
    assert "refuel" not in [wpt.name for wpt in layout.iter_waypoints()]
