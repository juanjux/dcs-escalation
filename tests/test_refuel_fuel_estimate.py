"""Refuel resets the available fuel without hiding an unreachable rendezvous."""

from types import SimpleNamespace
from typing import Any

import pytest

from game.ato.flightwaypointtype import FlightWaypointType as W
from game.ato.fuelestimate import MARGIN, estimate_fuel, estimate_fuel_segments
from game.dcs.aircrafttype import FuelConsumption
from game.utils import feet, kgs, nautical_miles


def flight_for(points: list[tuple[W, float]], fuel: float = 1000) -> Any:
    waypoints = [
        SimpleNamespace(waypoint_type=kind, x=distance, alt=feet(25000))
        for kind, distance in points
    ]
    return SimpleNamespace(
        fuel=fuel,
        unit_type=SimpleNamespace(
            helicopter=False,
            fuel_consumption=FuelConsumption(
                taxi=100, climb=20, cruise=10, combat=30, min_safe=200
            ),
            dcs_unit_type=SimpleNamespace(fuel_max=2000),
        ),
        roster=SimpleNamespace(
            members=[SimpleNamespace(loadout=SimpleNamespace(pylons={}))]
        ),
        flight_plan=SimpleNamespace(
            waypoints=waypoints,
            fuel_burn_distance_between_points=lambda a, b: nautical_miles(
                abs(b.x - a.x)
            ),
        ),
    )


def test_no_refuel_matches_existing_estimate() -> None:
    flight = flight_for([(W.TAKEOFF, 0), (W.CUSTOM, 50), (W.LANDING_POINT, 100)])
    assert estimate_fuel_segments(flight) == [estimate_fuel(flight)]


def test_refuel_splits_incoming_leg_and_fills_to_capacity() -> None:
    flight = flight_for([(W.TAKEOFF, 0), (W.REFUEL, 100), (W.LANDING_POINT, 200)])
    before, after = estimate_fuel_segments(flight)
    assert before.required.pounds == pytest.approx((100 + 2000 + 200) * MARGIN)
    assert after.required.pounds == pytest.approx((1000 + 200) * MARGIN)
    assert before.carried.kgs == pytest.approx(1000)
    assert after.carried.kgs == pytest.approx(2000)
    assert not before.enough
    assert after.enough


def test_tanker_planning_still_sees_the_whole_route() -> None:
    flight = flight_for(
        [(W.TAKEOFF, 0), (W.REFUEL, 80), (W.LANDING_POINT, 300)], fuel=1200
    )
    assert all(segment.enough for segment in estimate_fuel_segments(flight))
    aggregate = estimate_fuel(flight)
    assert aggregate is not None and not aggregate.enough
    assert aggregate.required.pounds == pytest.approx(
        (100 + 1600 + 2200 + 200) * MARGIN
    )


def test_long_post_refuel_leg_is_still_short() -> None:
    before, after = estimate_fuel_segments(
        flight_for([(W.TAKEOFF, 0), (W.REFUEL, 20), (W.LANDING_POINT, 1000)])
    )
    assert before.enough
    assert not after.enough


def test_multiple_refuels_and_auxiliary_points() -> None:
    estimates = estimate_fuel_segments(
        flight_for(
            [
                (W.TAKEOFF, 0),
                (W.REFUEL, 50),
                (W.REFUEL, 150),
                (W.LANDING_POINT, 200),
                (W.REFUEL, 1000),
                (W.BULLSEYE, 2000),
            ]
        )
    )
    assert len(estimates) == 3
    assert [e.required.pounds for e in estimates] == pytest.approx(
        [1300 * MARGIN, 1200 * MARGIN, 700 * MARGIN]
    )


def test_external_tanks_are_refilled_and_removing_them_updates_both_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight = flight_for([(W.TAKEOFF, 0), (W.REFUEL, 50), (W.LANDING_POINT, 100)])
    without = estimate_fuel_segments(flight)
    monkeypatch.setattr("game.ato.fuelestimate.loadout_fuel", lambda loadout: kgs(500))
    with_tanks = estimate_fuel_segments(flight)
    assert [e.carried.kgs for e in with_tanks] == pytest.approx([1500, 2500])
    for before, after in zip(without, with_tanks):
        assert after.required == before.required
        assert after.carried.kgs - before.carried.kgs == pytest.approx(500)


def test_standoff_filter_is_shared_by_both_estimators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flight = flight_for(
        [
            (W.TAKEOFF, 0),
            (W.INGRESS_STRIKE, 20),
            (W.TARGET_POINT, 200),
            (W.SPLIT, 30),
            (W.REFUEL, 40),
            (W.LANDING_POINT, 60),
        ]
    )
    monkeypatch.setattr("game.ato.fuelestimate.releases_at_ingress", lambda _: True)
    before, after = estimate_fuel_segments(flight)
    assert before.required.pounds == pytest.approx((100 + 400 + 200 + 200) * MARGIN)
    assert after.required.pounds == pytest.approx((200 + 200) * MARGIN)


def test_empty_route_keeps_reserve() -> None:
    estimate = estimate_fuel_segments(flight_for([]))
    assert len(estimate) == 1
    assert estimate[0].required.pounds == pytest.approx(300 * MARGIN)
