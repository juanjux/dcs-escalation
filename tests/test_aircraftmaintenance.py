"""Aircraft inventory, workshop capacity, recovery and turn-boundary regressions."""

from __future__ import annotations

import pickle
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from game import aircraftmaintenance as maintenance
from game.agent import service
from game.settings import Settings
from game.squadrons.experience import PilotOutcomes
from game.squadrons.squadron import Squadron
from game.theater import Player


class _Squadron(SimpleNamespace):
    def __str__(self) -> str:
        return "Test Squadron"


@pytest.fixture
def world() -> Any:
    settings = Settings()
    settings.aircraft_maintenance_enabled = True
    messages: list[Any] = []
    squadrons: list[Any] = []
    blue: Any = SimpleNamespace(budget=10.0)
    blue.air_wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    blue.adjust_budget = lambda value: setattr(blue, "budget", blue.budget + value)
    red = SimpleNamespace(air_wing=SimpleNamespace(iter_squadrons=lambda: iter(())))
    base = SimpleNamespace(
        id="base",
        name="Home",
        captured=Player.BLUE,
        sunk=False,
        position=SimpleNamespace(x=0, y=0),
        total_aircraft_parking=lambda parking: 10,
    )
    enemy = SimpleNamespace(
        id="enemy",
        name="Enemy",
        captured=Player.RED,
        sunk=False,
        position=SimpleNamespace(x=10000, y=0),
        total_aircraft_parking=lambda parking: 0,
    )
    game: Any = SimpleNamespace(
        settings=settings,
        turn=10,
        coalitions=[blue, red],
        blue=blue,
        red=red,
        theater=SimpleNamespace(controlpoints=[base, enemy]),
        message=lambda *args: messages.append(args),
        coalition_for=lambda side: blue if side == Player.BLUE else red,
    )
    sq: Any = _Squadron(
        id="sq",
        settings=settings,
        player=Player.BLUE,
        coalition=blue,
        location=base,
        owned_aircraft=6,
        untasked_aircraft=6,
        pending_deliveries=0,
        aircraft_repairs=[],
        aircraft=SimpleNamespace(price=20, display_name="Test aircraft"),
    )
    squadrons.append(sq)
    blue.game = game
    return SimpleNamespace(
        game=game,
        base=base,
        enemy=enemy,
        sq=sq,
        blue=blue,
        squadrons=squadrons,
        messages=messages,
    )


def test_minimum_and_total_physical_parking_capacity(world: Any) -> None:
    assert maintenance.mechanics(world.game, world.base) == 2
    world.base.total_aircraft_parking = lambda parking: 51
    assert maintenance.mechanics(world.game, world.base) == 6
    world.game.settings.aircraft_slots_per_mechanic = 20
    assert maintenance.mechanics(world.game, world.base) == 3
    world.base.extra_aircraft_mechanics = 2
    assert maintenance.mechanics(world.game, world.base) == 5


def test_new_damage_blocks_a_complete_turn_and_advances_only_once(world: Any) -> None:
    assert maintenance.admit(world.game, world.sq, "mission:unit", 0.95)
    assert world.sq.owned_aircraft == 6
    assert world.sq.untasked_aircraft == 5
    world.game.turn = 11
    maintenance.advance(world.game)
    assert maintenance.damaged_count(world.sq) == 1
    world.game.turn = 12
    maintenance.advance(world.game)
    assert maintenance.damaged_count(world.sq) == 0
    maintenance.advance(world.game)
    assert len([m for m in world.messages if "one aircraft repaired" in m[1]]) == 1


def test_default_half_health_and_two_mechanics_finish_in_one_working_turn(
    world: Any,
) -> None:
    assert world.game.settings.aircraft_repair_percent == 50
    maintenance.admit(world.game, world.sq, "severe", 0.001)
    view = maintenance.workshop_view(world.game, world.base)
    assert view["aircraft"][0]["assigned_mechanics"] == 2
    assert view["aircraft"][0]["working_turns_remaining"] == 1
    assert view["aircraft"][0]["turns_until_ready"] == 2
    for turn, remaining in ((11, 1), (12, 0)):
        world.game.turn = turn
        maintenance.advance(world.game)
        assert maintenance.damaged_count(world.sq) == remaining


def test_shared_fifo_queue_does_not_reuse_a_mechanic_in_same_turn(world: Any) -> None:
    other: Any = SimpleNamespace(**vars(world.sq))
    other.id, other.aircraft_repairs = "other", []
    world.squadrons.append(other)
    maintenance.admit(world.game, world.sq, "first", 0.9)
    maintenance.admit(world.game, other, "second", 0.2)
    maintenance.admit(world.game, world.sq, "third", 0.9)
    view = maintenance.workshop_view(world.game, world.base)
    assert (view["mechanics"], view["busy"], view["free"]) == (2, 2, 0)
    assert [a["status"] for a in view["aircraft"]] == [
        "repairing",
        "repairing",
        "queued",
    ]
    assert view["aircraft"][2]["queue_turns"] == 2
    world.game.turn = 12
    maintenance.advance(world.game)
    assert [j.source for j in maintenance.repairs(world.sq)] == ["third"]
    assert maintenance.repairs(other)[0].health == pytest.approx(0.7)
    world.game.turn = 13
    maintenance.advance(world.game)
    assert not maintenance.repairs(world.sq)


def test_binary_damage_one_turn_and_idempotent_admission(world: Any) -> None:
    assert maintenance.admit(world.game, world.sq, "binary", None)
    assert not maintenance.admit(world.game, world.sq, "binary", None)
    assert maintenance.repairs(world.sq)[0].health is None
    world.game.turn = 12
    maintenance.advance(world.game)
    assert not maintenance.repairs(world.sq)


def test_spare_mechanics_help_without_wasting_staff_on_small_or_binary_jobs(
    world: Any,
) -> None:
    world.base.extra_aircraft_mechanics = 3
    world.game.settings.aircraft_repair_percent = 20
    maintenance.admit(world.game, world.sq, "minor", 0.95)
    maintenance.admit(world.game, world.sq, "binary", None)
    maintenance.admit(world.game, world.sq, "severe", 0.05)
    view = maintenance.workshop_view(world.game, world.base)
    assert [job["assigned_mechanics"] for job in view["aircraft"]] == [1, 1, 3]
    assert [job["working_turns_remaining"] for job in view["aircraft"]] == [1, 1, 2]
    assert view["busy"] == 5 and view["free"] == 0
    world.game.turn = 12
    maintenance.advance(world.game)
    assert len(maintenance.repairs(world.sq)) == 1
    assert maintenance.repairs(world.sq)[0].health == pytest.approx(0.65)
    view = maintenance.workshop_view(world.game, world.base)
    assert view["aircraft"][0]["assigned_mechanics"] == 2
    assert view["busy"] == 2 and view["free"] == 3
    world.game.turn = 13
    maintenance.advance(world.game)
    assert not maintenance.repairs(world.sq)


@pytest.mark.parametrize("staff", [2, 3, 5, 10])
@pytest.mark.parametrize("rate", [1, 20, 34, 50, 100])
def test_cooperative_forecast_matches_real_boundaries(
    world: Any, staff: int, rate: int
) -> None:
    world.base.extra_aircraft_mechanics = staff - 2
    world.game.settings.aircraft_repair_percent = rate
    for i, health in enumerate([0.01, 0.25, 0.8, None, 0.1]):
        maintenance.admit(world.game, world.sq, f"job-{i}", health)
    # A later admission overlaps the existing FIFO queue.
    world.game.turn = 11
    maintenance.admit(world.game, world.sq, "later", 0.4)
    view = maintenance.workshop_view(world.game, world.base)
    expected = {
        job["id"]: world.game.turn + job["turns_until_ready"]
        for job in view["aircraft"]
    }
    original_damage = [job.damage for job in maintenance.repairs(world.sq)]
    maintenance.workshop_view(world.game, world.base)
    assert [job.damage for job in maintenance.repairs(world.sq)] == original_damage
    for turn in range(12, max(expected.values()) + 1):
        world.game.turn = turn
        maintenance.advance(world.game)
        actual = {job.id for job in maintenance.repairs(world.sq)}
        assert actual == {job_id for job_id, ready in expected.items() if ready > turn}


def test_custom_mechanic_cost_is_dollars_and_api_keeps_million_budget_units(
    world: Any,
) -> None:
    world.game.settings.aircraft_mechanic_cost = 125_000
    maintenance.hire_mechanic(world.game, world.base)
    assert world.blue.budget == pytest.approx(9.875)
    view = maintenance.workshop_view(world.game, world.base)
    assert view["mechanic_cost_dollars"] == 125_000
    assert view["mechanic_price_m"] == 0.125


def test_new_admission_does_not_reserve_a_helper_needed_by_an_eligible_aircraft(
    world: Any,
) -> None:
    maintenance.admit(world.game, world.sq, "old", 0.01)
    world.game.turn = 11
    maintenance.admit(world.game, world.sq, "new", 0.5)
    view = maintenance.workshop_view(world.game, world.base)
    assert view["next_working_turn"] == 12
    assert [job["assigned_mechanics"] for job in view["aircraft"]] == [2, 0]
    assert [job["turns_until_ready"] for job in view["aircraft"]] == [1, 2]
    world.game.turn = 12
    maintenance.advance(world.game)
    assert [job.source for job in maintenance.repairs(world.sq)] == ["new"]


@pytest.mark.parametrize("health", [1, 0, -1, 2, float("nan"), float("inf")])
def test_invalid_or_healthy_aircraft_do_not_enter_workshop(
    world: Any, health: float
) -> None:
    assert not maintenance.admit(world.game, world.sq, "bad", health)


def test_hiring_keeps_fractional_million_price_and_checks_budget(world: Any) -> None:
    maintenance.hire_mechanic(world.game, world.base)
    assert world.blue.budget == pytest.approx(9.95)
    assert maintenance.mechanics(world.game, world.base) == 3
    world.blue.budget = 0.049
    with pytest.raises(ValueError, match="funds"):
        maintenance.hire_mechanic(world.game, world.base)
    assert world.base.extra_aircraft_mechanics == 1


def test_explicit_damaged_sale_never_adds_healthy_inventory(world: Any) -> None:
    maintenance.admit(world.game, world.sq, "sale", 0.4)
    job = maintenance.repairs(world.sq)[0]
    value = maintenance.sell_damaged(world.game, world.sq, job.id)
    assert value == 10
    assert world.sq.owned_aircraft == 5 and world.sq.untasked_aircraft == 5
    assert world.blue.budget == 20
    with pytest.raises(ValueError, match="no longer"):
        maintenance.sell_damaged(world.game, world.sq, job.id)
    assert world.blue.budget == 20


@pytest.mark.parametrize("cause", ["sunk", "captured"])
def test_base_loss_does_not_repair_or_refund_aircraft(world: Any, cause: str) -> None:
    maintenance.admit(world.game, world.sq, "loss", 0.5)
    if cause == "sunk":
        world.base.sunk = True
    else:
        world.base.captured = Player.RED
    world.game.turn = 12
    maintenance.advance(world.game)
    assert world.sq.owned_aircraft == 5
    assert not maintenance.repairs(world.sq)
    assert world.blue.budget == 10


def test_inventory_reset_preserves_damage_and_pending_healthy_sales(world: Any) -> None:
    maintenance.admit(world.game, world.sq, "reset", 0.5)
    world.sq.pending_deliveries = -2
    world.sq.morale_in_play = False
    world.sq.active_pilots = []
    Squadron.return_all_pilots_and_aircraft(world.sq)
    assert world.sq.untasked_aircraft == 3
    Squadron.return_all_pilots_and_aircraft(world.sq)
    assert world.sq.untasked_aircraft == 3


def test_repair_pickle_and_old_squadron_migration() -> None:
    job = maintenance.AircraftRepair("test", 1, 1, 0.5)
    restored = pickle.loads(pickle.dumps(job))
    assert restored == job
    squadron = Squadron.__new__(Squadron)
    squadron.__setstate__({"owned_aircraft": 2})
    assert maintenance.repairs(squadron) == []


def _debrief(world: Any, entry: dict[str, Any], *, lost: bool = False) -> Any:
    flying = SimpleNamespace(flight=SimpleNamespace(squadron=world.sq))
    return SimpleNamespace(
        state_data=SimpleNamespace(
            aircraft_damage=maintenance.parse_reports([dict(unit="unit", **entry)]),
            aircraft_damage_mission_id="mission",
        ),
        unit_map=SimpleNamespace(flight=lambda name: flying),
        air_losses=SimpleNamespace(losses=[flying] if lost else []),
        is_non_combat_loss=lambda unit: True,
    )


def test_confirmed_off_field_return_uses_actual_position_and_deduplicates(
    world: Any,
) -> None:
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 10, "z": 5})
    maintenance.commit_reports(world.game, debrief)
    maintenance.commit_reports(world.game, debrief)
    assert maintenance.damaged_count(world.sq) == 1


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("ignore_crashes", [False, True])
@pytest.mark.parametrize("pilot_alive", [False, True])
@pytest.mark.parametrize("live_pilots", [False, True])
def test_hostile_damaged_return_is_written_off_once_without_harming_pilot(
    world: Any, side: Player, ignore_crashes: bool, pilot_alive: bool, live_pilots: bool
) -> None:
    world.game.settings.ignore_non_combat_air_losses = ignore_crashes
    world.game.settings.live_pilots_enabled = live_pilots
    if side == Player.RED:
        world.sq.player = Player.RED
        world.base.captured = Player.RED
        world.enemy.captured = Player.BLUE
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0})
    pilot = SimpleNamespace(alive=pilot_alive, wounded=False)
    debrief.unit_map.flight("unit").pilot = pilot
    debrief.pilot_outcomes = PilotOutcomes()
    maintenance.commit_reports(world.game, debrief)
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == 5 and world.sq.destroyed_aircraft == 1
    assert world.sq.untasked_aircraft == 5
    assert world.blue.budget == 10
    assert len(debrief.aircraft_writeoffs) == 1
    assert debrief.aircraft_writeoffs[0].player == side
    assert not maintenance.repairs(world.sq)
    assert vars(pilot) == {"alive": pilot_alive, "wounded": False}
    assert debrief.pilot_outcomes == PilotOutcomes()
    assert debrief.air_losses.losses == []
    world.game.turn += 1
    world.sq.morale_in_play = False
    world.sq.active_pilots = []
    Squadron.return_all_pilots_and_aircraft(world.sq)
    assert world.sq.untasked_aircraft == 5


@pytest.mark.parametrize(
    "entry",
    [
        {"health": 1, "recovered": True, "x": 9990, "z": 0},
        {"health": 0.5, "recovered": False, "x": 9990, "z": 0},
        {"health": 0.5, "recovered": True},
        {"health": 0, "recovered": True, "x": 9990, "z": 0},
        {"health": 0.5, "recovered": True, "x": 9990, "z": 0, "killed": True},
        {"health": 0.5, "recovered": True, "x": 9990, "z": 0, "ejected": True},
    ],
)
def test_unknown_healthy_or_terminal_reports_do_not_add_a_writeoff(
    world: Any, entry: dict[str, Any]
) -> None:
    debrief = _debrief(world, entry)
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == 6
    assert not getattr(debrief, "aircraft_writeoffs", [])


def test_actual_dcs_loss_is_not_debited_again_as_a_writeoff(world: Any) -> None:
    debrief = _debrief(
        world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0}, lost=True
    )
    maintenance.commit_reports(world.game, debrief)
    assert (
        world.sq.owned_aircraft == 6
    )  # The existing physical-loss path owns this debit.
    assert not getattr(debrief, "aircraft_writeoffs", [])


def test_writeoff_never_removes_aircraft_already_in_the_workshop(world: Any) -> None:
    maintenance.admit(world.game, world.sq, "old", 0.5)
    world.sq.owned_aircraft = 1
    world.sq.untasked_aircraft = 0
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0})
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == maintenance.damaged_count(world.sq) == 1
    assert world.sq.untasked_aircraft == 0
    assert not getattr(debrief, "aircraft_writeoffs", [])


def test_disabled_maintenance_does_not_write_off_damaged_landings(world: Any) -> None:
    world.game.settings.aircraft_maintenance_enabled = False
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0})
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == world.sq.untasked_aircraft == 6
    assert not getattr(debrief, "aircraft_writeoffs", [])


def test_same_distance_is_unrecoverable_but_no_enemy_base_allows_recovery(
    world: Any,
) -> None:
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 5000, "z": 0})
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == 5
    world.game._aircraft_maintenance_applied.clear()
    world.enemy.captured = Player.NEUTRAL
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 5000, "z": 0})
    maintenance.commit_reports(world.game, debrief)
    assert maintenance.damaged_count(world.sq) == 1 and world.sq.owned_aircraft == 5


def test_remain_air_assault_is_not_debited_twice(world: Any) -> None:
    debrief = _debrief(world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0})
    flight = debrief.unit_map.flight("unit").flight
    flight.remain_at_destination = flight.is_helo = True
    world.sq.owned_aircraft = 5
    maintenance.commit_reports(world.game, debrief)
    assert world.sq.owned_aircraft == 5
    assert not getattr(debrief, "aircraft_writeoffs", [])


def test_writeoff_is_in_debrief_counts_rows_costs_and_saved_report(world: Any) -> None:
    from game.debriefing import Debriefing, GroundLosses
    from game.debriefingreport import DebriefingReport
    from tests.test_debriefing_report import _debriefing

    damaged = _debrief(world, {"health": 0.5, "recovered": True, "x": 9990, "z": 0})
    damaged.state_data.mission_ended = True
    debrief = _debriefing(
        game=world.game,
        state_data=damaged.state_data,
        unit_map=damaged.unit_map,
        ground_losses=GroundLosses(),
        base_captures=[],
        air_losses=SimpleNamespace(
            losses=[], player=[], enemy=[], by_type=lambda _: {}
        ),
    )
    debrief.loss_counts = lambda side: Debriefing.loss_counts(debrief, side)
    maintenance.commit_reports(world.game, debrief)
    report = DebriefingReport.from_debriefing(debrief, world.game.turn)
    assert report.loss_counts(Player.BLUE).aircraft == 1
    assert report.air_rows(Player.BLUE) == [
        ("Test aircraft", 1, "Unrecoverable damage — written off")
    ]
    costs = report.loss_costs(Player.BLUE)
    assert costs is not None and costs.aircraft == 20
    assert report.damage_rows(Player.BLUE) == []
    assert pickle.loads(pickle.dumps(report)).air_rows(Player.BLUE) == report.air_rows(
        Player.BLUE
    )


@pytest.mark.parametrize(
    "entry",
    [
        {"health": 0.5, "recovered": False, "x": 10, "z": 0},
        {"health": 0.5, "recovered": True, "x": 9990, "z": 0},
        {"health": 0.5, "recovered": True, "x": 10, "z": 0, "ejected": True},
        {"health": 0.5, "recovered": True, "x": 10, "z": 0, "killed": True},
        {"health": 0.5, "recovered": True},
    ],
)
def test_no_recovery_from_survival_alone_or_hostile_landing(
    world: Any, entry: dict[str, Any]
) -> None:
    maintenance.commit_reports(world.game, _debrief(world, entry))
    assert not maintenance.repairs(world.sq)


@pytest.mark.parametrize(
    "ignore,prior,expected", [(True, 5, 1), (True, 9.5, 0), (False, 5, 0)]
)
def test_crash_recovery_requires_doctrine_and_damage_before_impact(
    world: Any,
    ignore: bool,
    prior: float,
    expected: int,
) -> None:
    world.game.settings.ignore_non_combat_air_losses = ignore
    debrief = _debrief(
        world,
        {
            "health": 0,
            "crash_time": 10,
            "first_damage_time": prior,
            "pre_crash_health": 0.4,
        },
        lost=True,
    )
    maintenance.commit_reports(world.game, debrief)
    assert maintenance.damaged_count(world.sq) == expected


def test_malformed_telemetry_cannot_invent_damage() -> None:
    assert maintenance.parse_reports({"unit": "x"}) == {}
    reports = maintenance.parse_reports(
        [
            None,
            {},
            {"unit": ""},
            {"unit": "x", "health": True, "recovered": "true", "x": float("inf")},
        ]
    )
    assert reports["x"].health is None
    assert reports["x"].recovered is False
    assert reports["x"].x is None


def test_legacy_debrief_state_loads_without_aircraft_telemetry() -> None:
    from game.debriefing import StateData

    state = StateData(False, [], [], [], [])
    state.__dict__.pop("aircraft_damage")
    state.__dict__.pop("aircraft_damage_mission_id")
    restored = pickle.loads(pickle.dumps(state))
    assert restored.aircraft_damage == {}
    assert restored.aircraft_damage_mission_id is None


def test_ejection_is_a_loss_even_without_a_separate_dead_event(world: Any) -> None:
    from game.debriefing import StateData, Debriefing

    flying: Any = object()
    mapping: Any = SimpleNamespace(
        flight=lambda name: flying if name == "unit" else None
    )
    state = StateData.from_json(
        {
            "aircraft_damage_state": [{"unit": "unit", "ejected": True, "health": 0.5}],
        },
        mapping,
    )
    assert state.killed_aircraft == ["unit"]
    debrief = Debriefing.__new__(Debriefing)
    debrief.state_data = state
    debrief._loss_name_by_id = {id(flying): "unit"}
    assert not debrief.is_non_combat_loss(flying)


def test_relocation_refuses_sale_without_confirmation_and_checks_capacity_first(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game.theater import ParkingType

    maintenance.admit(world.game, world.sq, "relocating", 0.2)
    world.sq.destination = None
    world.sq.expected_size_next_turn = 6
    world.sq.location.runway_is_operational = lambda: True
    destination: Any = SimpleNamespace(
        name="Other",
        can_operate=lambda aircraft: True,
        unclaimed_parking=lambda parking: 0,
    )
    with pytest.raises(RuntimeError, match="Confirm"):
        Squadron.plan_relocation(world.sq, destination, datetime(2026, 1, 1))
    # Use the actual parking selection method without requiring a complete aircraft.
    monkeypatch.setattr(ParkingType, "from_squadron", lambda self, squadron: self)
    with pytest.raises(RuntimeError, match="parking"):
        Squadron.plan_relocation(
            world.sq, destination, datetime(2026, 1, 1), confirm_damaged_sale=True
        )
    assert world.sq.owned_aircraft == 6
    assert len(maintenance.repairs(world.sq)) == 1
    assert world.blue.budget == 10


def test_validated_relocation_sells_only_damaged_aircraft(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game.theater import ParkingType

    maintenance.admit(world.game, world.sq, "relocating", 0.2)
    world.sq.destination = None
    world.sq.expected_size_next_turn = 6
    world.sq.location.runway_is_operational = lambda: True
    destination: Any = SimpleNamespace(
        name="Other",
        can_operate=lambda aircraft: True,
        unclaimed_parking=lambda parking: 5,
    )
    monkeypatch.setattr(ParkingType, "from_squadron", lambda self, squadron: self)
    world.sq.replan_ferry_flights = lambda now: None
    Squadron.plan_relocation(
        world.sq, destination, datetime(2026, 1, 1), confirm_damaged_sale=True
    )
    assert world.sq.destination is destination
    assert world.sq.owned_aircraft == 5
    assert world.sq.untasked_aircraft == 5
    assert not maintenance.repairs(world.sq)
    assert world.blue.budget == 20


def test_failed_ferry_planning_does_not_sell_damaged_aircraft(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game.theater import ParkingType

    maintenance.admit(world.game, world.sq, "relocating", 0.2)
    world.sq.destination = None
    world.sq.expected_size_next_turn = 6
    world.sq.location.runway_is_operational = lambda: True
    destination: Any = SimpleNamespace(
        name="Other",
        can_operate=lambda aircraft: True,
        unclaimed_parking=lambda parking: 5,
    )
    monkeypatch.setattr(ParkingType, "from_squadron", lambda self, squadron: self)

    def fail(now: datetime) -> None:
        raise RuntimeError("Cannot plan ferry")

    world.sq.replan_ferry_flights = fail
    world.sq.cancel_ferry_flights = lambda: None
    with pytest.raises(RuntimeError, match="ferry"):
        Squadron.plan_relocation(
            world.sq, destination, datetime(2026, 1, 1), confirm_damaged_sale=True
        )
    assert world.sq.destination is None
    assert world.sq.owned_aircraft == 6
    assert len(maintenance.repairs(world.sq)) == 1
    assert world.blue.budget == 10


@pytest.mark.parametrize(
    "call",
    [
        lambda: service.workshops("blue"),
        lambda: service.hire_aircraft_mechanic("blue", "base"),
        lambda: service.sell_damaged_aircraft("blue", "sq", "job"),
        lambda: service.relocation_workshop_quote("blue", "sq"),
    ],
)
def test_workshop_api_never_exposes_or_mutates_the_human_side(call: Any) -> None:
    from game.agent.service import SideNotAllowedError

    with pytest.raises(SideNotAllowedError):
        call()


def test_disabled_feature_preserves_legacy_inventory_and_releases_jobs_next_boundary(
    world: Any,
) -> None:
    maintenance.admit(world.game, world.sq, "old", 0.2)
    world.game.settings.aircraft_maintenance_enabled = False
    world.game.turn = 11
    maintenance.advance(world.game)
    assert not maintenance.repairs(world.sq)
    assert world.sq.owned_aircraft == 6


def test_editor_discard_restores_damaged_airframes_without_creating_money(
    world: Any,
) -> None:
    from qt_ui.windows.airwingconfig.dialog import SquadronState

    world.sq.max_size = 6
    world.sq.pilot_limit_override = None
    maintenance.admit(world.game, world.sq, "editor", 0.4)
    snapshot = SquadronState.of(world.sq)
    maintenance.remove_damaged(world.game, world.sq, refund=True)
    world.sq.location = world.enemy
    # An unrelated budget movement must survive the discard.
    world.blue.adjust_budget(5)
    snapshot.restore()
    assert world.sq.location is world.base
    assert world.sq.owned_aircraft == 6
    assert len(maintenance.repairs(world.sq)) == 1
    assert world.blue.budget == 15


def test_native_return_to_friendly_carrier_does_not_use_static_nearest_land_base(
    world: Any,
) -> None:
    world.sq.location.is_fleet = True
    world.sq.location.airdrome_id_for_landing = 777
    debrief = _debrief(
        world,
        {"health": 0.6, "recovered": True, "x": 9900, "z": 0, "landing_place": 777},
    )
    debrief.unit_map.flight("unit").flight.arrival = world.sq.location
    maintenance.commit_reports(world.game, debrief)
    assert maintenance.damaged_count(world.sq) == 1


@pytest.mark.parametrize("invalid", [False, "not-an-id", "501.5", "-501", "9" * 30])
def test_invalid_landing_ids_are_not_interpreted_as_carrier_ids(invalid: Any) -> None:
    report = maintenance.parse_reports([{"unit": "one", "landing_place": invalid}])[
        "one"
    ]
    assert report.landing_place is None


def test_numeric_string_landing_ids_are_preserved() -> None:
    report = maintenance.parse_reports([{"unit": "one", "landing_place": "501"}])["one"]
    assert report.landing_place == 501


@pytest.mark.parametrize("disqualifier", [None, "sunk", "enemy", "dead"])
def test_carrier_runtime_id_resolves_by_native_name_not_editor_id(
    world: Any, disqualifier: str | None
) -> None:
    world.base.is_fleet = True
    world.base.airdrome_id_for_landing = 493
    ship = SimpleNamespace(
        is_ship=True,
        alive=True,
        ground_object=SimpleNamespace(control_point=world.base),
    )
    debrief = _debrief(
        world,
        {
            "health": 0.928571,
            "recovered": True,
            "x": 9900,
            "z": 0,
            "landing_place": "501",
            "landing_name": "CVN native name",
        },
    )
    debrief.unit_map.flight("unit").flight.arrival = world.base
    debrief.unit_map.theater_units = lambda name: (
        SimpleNamespace(theater_unit=ship) if name == "CVN native name" else None
    )
    if disqualifier == "sunk":
        world.base.sunk = True
    elif disqualifier == "enemy":
        world.base.captured = Player.RED
    elif disqualifier == "dead":
        ship.alive = False
    maintenance.commit_reports(world.game, debrief)
    assert maintenance.damaged_count(world.sq) == (1 if disqualifier is None else 0)


def test_debrief_counts_match_admission_and_group_by_airframe(world: Any) -> None:
    from game.debriefingreport import DebriefingReport
    from tests.test_debriefing_report import _debriefing

    raw = [
        dict(unit=name, health=health, recovered=True, x=10, z=0)
        for name, health in (("first", 0.5), ("second", 0.928571), ("healthy", 1.0))
    ]
    state = SimpleNamespace(
        mission_ended=True,
        aircraft_damage=maintenance.parse_reports(raw),
        aircraft_damage_mission_id="report",
    )
    flying = SimpleNamespace(flight=SimpleNamespace(squadron=world.sq))
    debrief = _debriefing(
        game=world.game,
        state_data=state,
        unit_map=SimpleNamespace(flight=lambda name: flying),
        air_losses=SimpleNamespace(
            losses=[], player=[], enemy=[], by_type=lambda _: {}
        ),
    )
    preview = DebriefingReport.from_debriefing(debrief, world.game.turn)
    assert preview.damage_rows(Player.BLUE) == [
        ("Test aircraft", 2, "Recovered for repair")
    ]
    maintenance.commit_reports(world.game, debrief)
    committed = DebriefingReport.from_debriefing(debrief, world.game.turn)
    assert committed.damage_rows(Player.BLUE) == preview.damage_rows(Player.BLUE)
    assert maintenance.damaged_count(world.sq) == 2
    assert pickle.loads(pickle.dumps(committed)).damage_rows(
        Player.BLUE
    ) == committed.damage_rows(Player.BLUE)


def test_debrief_does_not_count_damaged_kills_or_enemy_territory_returns(
    world: Any,
) -> None:
    from game.debriefingreport import DebriefingReport
    from tests.test_debriefing_report import _debriefing

    raw = [
        dict(unit="lost", health=0.4, recovered=True, killed=True, x=0, z=0),
        dict(unit="enemy landing", health=0.4, recovered=True, x=9990, z=0),
    ]
    state = SimpleNamespace(
        mission_ended=True, aircraft_damage=maintenance.parse_reports(raw)
    )
    flying = SimpleNamespace(flight=SimpleNamespace(squadron=world.sq))
    debrief = _debriefing(
        game=world.game,
        state_data=state,
        unit_map=SimpleNamespace(flight=lambda name: flying),
        air_losses=SimpleNamespace(
            losses=[], player=[], enemy=[], by_type=lambda _: {}
        ),
    )
    report = DebriefingReport.from_debriefing(debrief, world.game.turn)
    assert report.damage_rows(Player.BLUE) == []


def test_workshop_reads_only_the_commanded_coalition(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "_require_game", lambda: world.game)
    result = service.workshops("red")
    assert [entry["base_id"] for entry in result] == [world.enemy.id]
    assert not result[0]["aircraft"]


def test_readiness_forecast_overlaps_admission_delay_with_existing_queue(
    world: Any,
) -> None:
    maintenance.admit(world.game, world.sq, "long-1", 0.2)
    maintenance.admit(world.game, world.sq, "long-2", 0.2)
    world.game.turn = 11
    maintenance.advance(world.game)
    maintenance.admit(world.game, world.sq, "later", 0.8)
    job = maintenance.repairs(world.sq)[-1]
    view = maintenance.workshop_view(world.game, world.base)
    prediction = next(item for item in view["aircraft"] if item["id"] == job.id)
    assert prediction["turns_until_ready"] == 3
    for turn in range(12, 14):
        world.game.turn = turn
        maintenance.advance(world.game)
        assert job in maintenance.repairs(world.sq)
    world.game.turn = 14
    maintenance.advance(world.game)
    assert job not in maintenance.repairs(world.sq)


def test_workshop_widget_shows_health_queue_and_fractional_price(
    world: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QProgressBar
    from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
    from qt_ui.windows.basemenu.QAircraftWorkshop import QAircraftWorkshop

    app = QApplication.instance() or QApplication([])

    class Signals(QObject):
        budgetupdated = Signal(object)
        gameupdated = Signal(object)

        def updateBudget(self, game: Any) -> None:
            self.budgetupdated.emit(game)

    signals = Signals()
    monkeypatch.setattr(GameUpdateSignal, "get_instance", lambda: signals)
    for i in range(3):
        maintenance.admit(world.game, world.sq, f"job-{i}", 0.4)
    model: Any = SimpleNamespace(game=world.game)
    widget = QAircraftWorkshop(world.base, model)
    font_id = QFontDatabase.addApplicationFont("resources/fonts/Inconsolata.otf")
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        widget.setFont(QFont(families[0], 11))
    assert widget.table.rowCount() == 3
    status = widget.table.item(2, 2)
    assert status is not None and status.text() == "Queued"
    bar = widget.table.cellWidget(0, 1)
    assert isinstance(bar, QProgressBar) and bar.value() == 400
    assert "$50,000" in widget.hire.text()
    widget.hire.click()
    app.processEvents()
    assert world.blue.budget == pytest.approx(9.95)
    status = widget.table.item(2, 2)
    assert status is not None and status.text() == "Repairing (1 mechanic)"
    widget.resize(1250, 450)
    widget.show()
    app.processEvents()
    assert widget.grab().save(str(tmp_path / "workshop.png"))
    widget.close()
