"""Altitude, the attack rate, and counting the drop tanks.

A flat fuel rate meant raising a flight's cruise band changed nothing, and the plan's
combat_speed_waypoints also flags the join and the split -- package-speed cruise, not
combat -- which put a strike's eighty-mile egress at over twice the right figure.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.fuelestimate import (
    ATTACK_WAYPOINTS,
    MAX_ALTITUDE_FACTOR,
    MIN_ALTITUDE_FACTOR,
    REFERENCE_ALTITUDE_FT,
    altitude_factor,
    estimate_fuel,
)
from game.dcs.aircrafttype import FuelConsumption

NM = 1852.0


def test_the_reference_altitude_costs_what_was_measured() -> None:
    assert altitude_factor(REFERENCE_ALTITUDE_FT) == pytest.approx(1.0)


def test_thirstier_low_and_leaner_high() -> None:
    factors = [altitude_factor(ft) for ft in (0, 10000, 20000, 30000, 40000)]
    assert factors == sorted(factors, reverse=True)
    assert factors[0] > 1.3, "on the deck a jet should be well over its cruise figure"


def test_the_correction_is_bounded() -> None:
    assert altitude_factor(-5000) <= MAX_ALTITUDE_FACTOR
    assert altitude_factor(70000) >= MIN_ALTITUDE_FACTOR


def test_a_helicopter_is_left_alone() -> None:
    assert altitude_factor(0, helicopter=True) == 1.0
    assert altitude_factor(20000, helicopter=True) == 1.0


def _waypoint(kind: FlightWaypointType, x: float, altitude_ft: float) -> MagicMock:
    waypoint = MagicMock()
    waypoint.waypoint_type = kind
    waypoint.alt.feet = altitude_ft
    waypoint.position.x = x
    return waypoint


def _flight(altitude_ft: float, tank_kgs: float = 0.0) -> MagicMock:
    flight = MagicMock()
    flight.unit_type.helicopter = False
    flight.unit_type.fuel_consumption = FuelConsumption(
        taxi=200, climb=30.0, cruise=10.0, combat=25.0, min_safe=1000
    )
    waypoints = [
        _waypoint(FlightWaypointType.TAKEOFF, 0.0, 0.0),
        _waypoint(FlightWaypointType.INGRESS_STRIKE, 50 * NM, altitude_ft),
        _waypoint(FlightWaypointType.TARGET_POINT, 60 * NM, altitude_ft),
        _waypoint(FlightWaypointType.SPLIT, 120 * NM, altitude_ft),
        _waypoint(FlightWaypointType.LANDING_POINT, 200 * NM, 0.0),
    ]
    plan = MagicMock()
    plan.waypoints = waypoints
    plan.combat_speed_waypoints = {waypoints[2], waypoints[3]}  # target AND split
    plan.fuel_burn_distance_between_points = lambda a, b: MagicMock(
        nautical_miles=abs(b.position.x - a.position.x) / NM
    )
    flight.flight_plan = plan
    flight.fuel = 3000.0
    loadout = MagicMock()
    loadout.pylons = {}
    flight.roster.members = [MagicMock(loadout=loadout)]
    return flight


def test_flying_higher_costs_less() -> None:
    low = estimate_fuel(_flight(10000))
    high = estimate_fuel(_flight(35000))
    assert low is not None and high is not None
    assert high.required.pounds < low.required.pounds * 0.9


def test_only_the_attack_pays_the_combat_rate() -> None:
    """The split is flagged combat by the plan and must not be charged as such."""
    assert FlightWaypointType.SPLIT not in ATTACK_WAYPOINTS
    assert FlightWaypointType.TARGET_POINT in ATTACK_WAYPOINTS


def test_what_it_carries_includes_the_drop_tanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.utils import kgs

    flight = _flight(25000)
    without = estimate_fuel(flight)
    monkeypatch.setattr(
        "game.ato.fuelestimate.loadout_fuel", lambda loadout: kgs(1000.0)
    )
    with_tanks = estimate_fuel(flight)
    assert without is not None and with_tanks is not None
    assert with_tanks.carried.kgs == pytest.approx(without.carried.kgs + 1000.0)
