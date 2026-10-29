"""Early tanker selection and timing without changing package/station times."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from dcs.mapping import Point
from dcs.terrain import Caucasus

from game.ato import prerefuel
from game.ato.flightplans.barcap import BarCapFlightPlan
from game.ato.flightplans.flightplan import FlightPlan
from game.ato.flightplans.formationattack import FormationAttackLayout
from game.ato.flightplans.patrolling import PatrollingLayout
from game.ato.flightplans.strike import StrikeFlightPlan
from game.ato.flightplans.theaterrefueling import TheaterRefuelingFlightPlan
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as W
from game.dcs.aircrafttype import AircraftType
from game.utils import feet

TERRAIN = Caucasus()
NOW = datetime(2026, 10, 29, 12)


def wp(name: str, kind: W = W.NAV, x: float = 0) -> FlightWaypoint:
    return FlightWaypoint(name, kind, Point(x, 0, TERRAIN), feet(25_000))


def attack() -> Any:
    flight: Any = SimpleNamespace(count=2, tanking_minutes=None)
    flight.package = SimpleNamespace(
        flights=[flight, object()],
        time_over_target=NOW,
        target=SimpleNamespace(position=Point(0, 0, TERRAIN)),
    )
    layout = FormationAttackLayout(
        departure=wp("Takeoff", W.TAKEOFF),
        custom_waypoints=[],
        arrival=wp("Landing", W.LANDING_POINT),
        divert=None,
        bullseye=wp("Bullseye", W.BULLSEYE),
        nav_to=[wp("Nav")],
        nav_from=[],
        hold=wp("Hold", W.LOITER),
        join=wp("Join", W.JOIN),
        split=wp("Split", W.SPLIT),
        refuel=None,
        ingress=wp("Ingress", W.INGRESS_STRIKE),
        targets=[wp("Target", W.TARGET_POINT)],
        pre_push_refuel=wp("Early", W.REFUEL),
    )
    flight.flight_plan = StrikeFlightPlan(flight, layout)
    return flight


@pytest.fixture
def travel(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        FlightPlan, "travel_time_between_waypoints", lambda *_: timedelta(minutes=1)
    )


def test_attack_departure_moves_but_join_and_tot_do_not(travel: Any) -> None:
    flight = attack()
    plan = flight.flight_plan
    join, target = plan.join_time, plan.tot
    earlier_push = plan.push_time
    assert plan.tot_for_waypoint(
        plan.layout.pre_push_refuel
    ) == earlier_push + timedelta(minutes=1)
    flight.tanking_minutes = 30
    assert plan.push_time == earlier_push - timedelta(minutes=21)
    assert (plan.join_time, plan.tot) == (join, target)
    points = plan.waypoints
    assert (
        points.index(plan.layout.hold)
        < points.index(plan.layout.pre_push_refuel)
        < points.index(plan.layout.join)
    )


def test_no_early_stop_keeps_original_push_time(travel: Any) -> None:
    flight = attack()
    flight.flight_plan.layout.pre_push_refuel = None
    assert flight.flight_plan.push_time == flight.flight_plan.join_time - timedelta(
        minutes=1
    )


def test_patrol_tanks_before_station_without_shortening_the_station(
    travel: Any,
) -> None:
    flight: Any = SimpleNamespace(count=2, tanking_minutes=None)
    flight.package = SimpleNamespace(time_over_target=NOW)
    flight.coalition = SimpleNamespace(
        game=SimpleNamespace(
            settings=SimpleNamespace(desired_barcap_mission_duration=timedelta(hours=2))
        )
    )
    layout = PatrollingLayout(
        departure=wp("Takeoff", W.TAKEOFF),
        custom_waypoints=[],
        arrival=wp("Landing", W.LANDING_POINT),
        divert=None,
        bullseye=wp("Bullseye", W.BULLSEYE),
        nav_to=[],
        nav_from=[],
        patrol_start=wp("Station", W.PATROL),
        patrol_end=wp("End", W.PATROL),
        pre_push_refuel=wp("Early", W.REFUEL),
    )
    plan = BarCapFlightPlan(flight, layout)
    before = plan.takeoff_time()
    flight.tanking_minutes = 30
    assert plan.takeoff_time() == before - timedelta(minutes=21)
    assert plan.patrol_start_time == NOW
    assert plan.patrol_end_time == NOW + timedelta(hours=2)


@pytest.mark.parametrize(
    "receiver,tanker,expected",
    [
        ("A-10C_2", "KC-135", True),
        ("A-10C_2", "KC130", False),
        ("FA-18C_hornet", "KC-135", False),
        ("FA-18C_hornet", "KC135MPRS", True),
        ("Su-25T", "IL-78M", False),
        ("unreviewed", "KC-135", False),
    ],
)
def test_authored_receiver_tanker_compatibility(
    receiver: str, tanker: str, expected: bool
) -> None:
    receiver_type: Any = SimpleNamespace(dcs_id=receiver)
    tanker_type: Any = SimpleNamespace(dcs_id=tanker)
    assert prerefuel.compatible(receiver_type, tanker_type) is expected


def test_real_aircraft_profiles_use_the_actual_dcs_ids(tmp_path: Any) -> None:
    from game import persistency

    persistency.setup(str(tmp_path), False, 16897)
    assert prerefuel.compatible(
        AircraftType.named("A-10C Thunderbolt II (Suite 7)"),
        AircraftType.named("KC-135 Stratotanker"),
    )


def test_nearest_compatible_theater_tanker_only() -> None:
    def tanker(identifier: str, x: float, theater: bool = True) -> Any:
        plan: Any = (
            TheaterRefuelingFlightPlan.__new__(TheaterRefuelingFlightPlan)
            if theater
            else SimpleNamespace()
        )
        plan.layout = SimpleNamespace(patrol_start=wp(identifier, W.PATROL, x))
        return SimpleNamespace(
            flight_type=prerefuel.FlightType.REFUELING,
            unit_type=SimpleNamespace(dcs_id=identifier),
            flight_plan=plan,
        )

    own = SimpleNamespace(flights=[tanker("KC-135", 0)])
    incompatible = tanker("KC130", 1)
    package_tanker = tanker("KC-135", 2, theater=False)
    far = tanker("KC-135", 10_000)
    near = tanker("KC-135", 100)
    flight: Any = SimpleNamespace(
        is_helo=False,
        package=own,
        unit_type=SimpleNamespace(dcs_id="A-10C_2"),
        coalition=SimpleNamespace(
            ato=SimpleNamespace(
                packages=[
                    own,
                    SimpleNamespace(flights=[incompatible, package_tanker, far, near]),
                ]
            )
        ),
    )
    assert prerefuel.planned_tanker(flight, Point(0, 0, TERRAIN)) is near


@pytest.mark.parametrize("enough", [True, False])
def test_post_stop_removed_only_when_every_remaining_segment_has_reserve(
    monkeypatch: Any, enough: bool
) -> None:
    flight = attack()
    post = wp("Post", W.REFUEL)
    flight.flight_plan.layout.refuel = post
    monkeypatch.setattr(
        prerefuel,
        "estimate_fuel_segments",
        lambda _: [SimpleNamespace(enough=True), SimpleNamespace(enough=enough)],
    )
    assert prerefuel.remove_unneeded_post_stop(flight) is enough
    assert flight.flight_plan.layout.refuel is (None if enough else post)


def test_failed_estimate_restores_the_post_stop(monkeypatch: Any) -> None:
    flight = attack()
    post = wp("Post", W.REFUEL)
    flight.flight_plan.layout.refuel = post

    def fail(_: Any) -> Any:
        raise ValueError("bad route")

    monkeypatch.setattr(prerefuel, "estimate_fuel_segments", fail)
    with pytest.raises(ValueError, match="bad route"):
        prerefuel.remove_unneeded_post_stop(flight)
    assert flight.flight_plan.layout.refuel is post


def test_pre_feature_layouts_keep_the_early_stop_disabled() -> None:
    layout = attack().flight_plan.layout
    del layout.__dict__["pre_push_refuel"]
    assert layout.pre_push_refuel is None


@pytest.mark.parametrize("early", [True, False])
def test_early_refuel_never_despawns_an_airborne_arrival(
    monkeypatch: Any, early: bool
) -> None:
    from unittest.mock import Mock
    from game.missiongenerator.aircraft.waypoints.pydcswaypointbuilder import (
        PydcsWaypointBuilder,
    )
    from game.missiongenerator.aircraft.waypoints.refuel import RefuelPointBuilder

    point = wp("Refuel", W.REFUEL)
    builder: Any = RefuelPointBuilder.__new__(RefuelPointBuilder)
    builder.flight = SimpleNamespace(
        flight_plan=SimpleNamespace(
            layout=SimpleNamespace(pre_push_refuel=point if early else None)
        )
    )
    builder.waypoint = point
    builder.group = SimpleNamespace(name="Flight")
    builder.ai_despawn = Mock(return_value=True)
    waypoint: Any = SimpleNamespace(add_task=Mock())
    monkeypatch.setattr(PydcsWaypointBuilder, "add_tasks", lambda *_: None)
    builder.add_tasks(waypoint)
    if early:
        builder.ai_despawn.assert_not_called()
        task = waypoint.add_task.call_args.args[0]
        serialized = repr(task.dict())
        assert "0.9" in serialized
        assert "0.2" not in serialized
    else:
        builder.ai_despawn.assert_called_once()
        waypoint.add_task.assert_not_called()
