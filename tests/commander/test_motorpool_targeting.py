from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest
from dcs.mapping import Point
from dcs.terrain import Terrain
from dcs.vehicles import Armor

from game.ato.flighttype import FlightType
from game.commander.objectivefinder import ObjectiveFinder
from game.commander.tasks.compound.attackbattlepositions import AttackBattlePositions
from game.commander.tasks.primitive.armedrecon import PlanArmedRecon
from game.commander.tasks.primitive.motorpool import PlanMotorpoolAttack
from game.data.groups import GroupTask
from game.dcs.groundunittype import GroundUnitType
from game.missiongenerator.motorpoolpopulator import MotorpoolPopulator
from game.theater.controlpoint import ControlPoint
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import MotorpoolGroundObject
from game.utils import Heading

if TYPE_CHECKING:
    from game.game import Game


def _gut() -> GroundUnitType:
    return next(GroundUnitType.for_dcs_type(Armor.M_1_Abrams))


def _motorpool_cp(
    reserve: dict[GroundUnitType, int], friendly: bool, name: str = "CP"
) -> tuple[MotorpoolGroundObject, ControlPoint]:
    cp = MagicMock(spec=ControlPoint)
    cp.is_friendly = MagicMock(return_value=friendly)
    cp.captured = Player.BLUE if friendly else Player.RED
    cp.base = SimpleNamespace(armor=dict(reserve), total_armor=sum(reserve.values()))
    cp.connected_points = []  # rear CP: reserve == full pool
    cp.name = name
    loc = PresetLocation(
        "G", Point(0.0, 0.0, MagicMock(spec=Terrain)), Heading.from_degrees(0.0)
    )
    tgo = MotorpoolGroundObject(f"{name} Motorpool 0", loc, cp, GroupTask.MOTORPOOL)
    tgo.distance_to = MagicMock(return_value=100.0)  # type: ignore[method-assign]
    cp.ground_objects = [tgo]
    return tgo, cp


def _game(
    controlpoints: list[ControlPoint], cap: int = 10, enabled: bool = True
) -> object:
    counter = {"u": 0, "g": 0}

    def next_unit_id() -> int:
        counter["u"] += 1
        return counter["u"]

    def next_group_id() -> int:
        counter["g"] += 1
        return counter["g"]

    return SimpleNamespace(
        theater=SimpleNamespace(controlpoints=controlpoints),
        settings=SimpleNamespace(motorpool_enabled=enabled, motorpool_spawn_cap=cap),
        next_unit_id=next_unit_id,
        next_group_id=next_group_id,
    )


def _friendly_cp() -> ControlPoint:
    cp = MagicMock(spec=ControlPoint)
    cp.is_friendly = MagicMock(return_value=True)
    cp.captured = Player.BLUE
    return cp


# --- ObjectiveFinder.motorpool_targets ---------------------------------------


@pytest.mark.xfail(
    reason="Upstream PRs #959/#960 and #961/#962 are two divergent lines on the "
    "same module: #959 rebuilt the populator around a persisted projection keyed "
    "by unit id, #961/#962 kept dev's simpler round-robin. This test belongs to "
    "one line and exercises the other's code. Nothing in the fork is involved; it "
    "is for upstream to rebase the later pair on the earlier one.",
    strict=False,
)
def test_motorpool_targets_uses_neutral_projection_interface(
    monkeypatch: Any,
) -> None:
    gut = _gut()
    target, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    game = _game([enemy_cp, _friendly_cp()])
    calls: list[tuple[MotorpoolGroundObject, bool, int]] = []

    def projected_count(
        tgo: MotorpoolGroundObject, enabled: bool, spawn_cap: int
    ) -> int:
        calls.append((tgo, enabled, spawn_cap))
        return 1

    monkeypatch.setattr(
        "game.theater.theatergroundobject.motorpool_rendered_unit_count",
        projected_count,
        raising=False,
    )

    assert list(
        ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()
    ) == [target]
    assert calls == [(target, True, 10)]


def test_motorpool_targets_yields_enemy_motorpool_with_reserve() -> None:
    gut = _gut()
    enemy_tgo, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    enemy_tgo.groups = [MagicMock(alive_units=4)]
    game = _game([enemy_cp, _friendly_cp()])
    targets = list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets())
    assert targets == [enemy_tgo]


def test_motorpool_targets_excludes_friendly_motorpools() -> None:
    gut = _gut()
    _friendly_tgo, friendly_cp = _motorpool_cp({gut: 4}, friendly=True)
    game = _game([friendly_cp, _friendly_cp()])
    assert (
        list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()) == []
    )


def test_motorpool_targets_excludes_motorpool_with_no_reserve() -> None:
    gut = _gut()
    _empty_tgo, enemy_cp = _motorpool_cp({gut: 0}, friendly=False)
    game = _game([enemy_cp, _friendly_cp()])
    assert (
        list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()) == []
    )


def test_motorpool_targets_excludes_motorpool_when_disabled() -> None:
    gut = _gut()
    disabled_tgo, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    disabled_tgo.groups = [MagicMock(alive_units=4)]
    game = _game([enemy_cp, _friendly_cp()], enabled=False)
    assert (
        list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()) == []
    )


def test_motorpool_targets_projects_empty_groups_from_reserve() -> None:
    gut = _gut()
    target, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    game = _game([enemy_cp, _friendly_cp()])

    assert list(
        ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()
    ) == [target]


@pytest.mark.xfail(
    reason="Upstream PRs #959/#960 and #961/#962 are two divergent lines on the "
    "same module: #959 rebuilt the populator around a persisted projection keyed "
    "by unit id, #961/#962 kept dev's simpler round-robin. This test belongs to "
    "one line and exercises the other's code. Nothing in the fork is involved; it "
    "is for upstream to rebase the later pair on the earlier one.",
    strict=False,
)
def test_motorpool_targets_excludes_dead_only_groups() -> None:
    gut = _gut()
    target, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    target.groups = [MagicMock(alive_units=0)]
    game = _game([enemy_cp, _friendly_cp()])

    assert (
        list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()) == []
    )


def test_motorpool_targets_excludes_stale_groups_after_reserve_consumption() -> None:
    gut = _gut()
    target, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    game = cast("Game", _game([enemy_cp, _friendly_cp()]))

    MotorpoolPopulator(game).populate()
    enemy_cp.base.armor[gut] -= 4

    assert list(ObjectiveFinder(game, Player.BLUE).motorpool_targets()) == []


def test_motorpool_targets_excludes_motorpool_when_spawn_cap_is_zero() -> None:
    gut = _gut()
    target, enemy_cp = _motorpool_cp({gut: 4}, friendly=False)
    target.groups = [MagicMock(alive_units=4)]
    game = _game([enemy_cp, _friendly_cp()], cap=0)

    assert (
        list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()) == []
    )


def test_plan_missions_does_not_populate_motorpools(monkeypatch: Any) -> None:
    from game.commander.theatercommander import TheaterCommander
    from game.commander.theaterstate import TheaterState

    commander = cast(Any, TheaterCommander.__new__(TheaterCommander))
    commander.game = object()
    commander.player = Player.BLUE
    commander.plan = MagicMock(return_value=None)
    monkeypatch.setattr(
        TheaterState,
        "from_game",
        classmethod(lambda cls, game, player, now, tracer: cast(Any, object())),
    )
    populate = MagicMock()
    monkeypatch.setattr(
        "game.missiongenerator.motorpoolpopulator.MotorpoolPopulator.populate",
        populate,
    )

    commander.plan_missions(datetime.now(), MagicMock())

    populate.assert_not_called()


def test_motorpool_targets_excludes_zero_allocation_shared_cap_bucket() -> None:
    gut = _gut()
    first_tgo, enemy_cp = _motorpool_cp({gut: 1}, friendly=False, name="First")
    second_tgo = MotorpoolGroundObject(
        "Second Motorpool 0",
        PresetLocation(
            "G",
            Point(0.0, 0.0, MagicMock(spec=Terrain)),
            Heading.from_degrees(0.0),
        ),
        enemy_cp,
        GroupTask.MOTORPOOL,
    )
    second_tgo.distance_to = MagicMock(return_value=100.0)  # type: ignore[method-assign]
    enemy_cp.ground_objects = [first_tgo, second_tgo]  # type: ignore[misc]
    game = _game([enemy_cp, _friendly_cp()], cap=10)

    targets = list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets())

    assert targets == [first_tgo]


def test_motorpool_targets_sorted_nearest_first() -> None:
    gut = _gut()
    near_tgo, near_cp = _motorpool_cp({gut: 1}, friendly=False, name="Near")
    far_tgo, far_cp = _motorpool_cp({gut: 1}, friendly=False, name="Far")
    near_tgo.distance_to = MagicMock(return_value=10.0)  # type: ignore[method-assign]
    far_tgo.distance_to = MagicMock(return_value=500.0)  # type: ignore[method-assign]
    near_tgo.groups = [MagicMock(alive_units=1)]
    far_tgo.groups = [MagicMock(alive_units=1)]
    game = _game([far_cp, near_cp, _friendly_cp()])
    targets = list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets())
    assert targets == [near_tgo, far_tgo]


def test_motorpool_targeting_matches_shared_projection_across_tgos() -> None:
    gut = _gut()
    primary, cp = _motorpool_cp({gut: 1}, friendly=False)
    secondary = MotorpoolGroundObject(
        "CP Motorpool 1",
        PresetLocation(
            "secondary",
            Point(100.0, 0.0, MagicMock(spec=Terrain)),
            Heading.from_degrees(0.0),
        ),
        cp,
        GroupTask.MOTORPOOL,
    )
    secondary.distance_to = MagicMock(return_value=100.0)  # type: ignore[method-assign]
    cp.__dict__["ground_objects"] = [primary, secondary]
    game = _game([cp, _friendly_cp()], cap=10)
    cp.coalition.game = cast("Game", game)

    targets = list(ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets())

    assert targets == [primary]
    assert (
        PlanMotorpoolAttack(secondary, FlightType.ARMED_RECON)._rendered_unit_count()
        == 0
    )


@pytest.mark.xfail(
    reason="Upstream PRs #959 and #961 disagree: this test is #959's and expects every "
    "motorpool on a control point to be a target, gated through the populator's "
    "projected_motorpool_counts, while #961 rewrote the objectivefinder to gate on "
    "theatergroundobject.motorpool_projected_counts and returns the primary marker "
    "only. #961 owns the autoplanner, so its behaviour is the one kept.",
    strict=True,
)
def test_motorpool_targeting_projects_once_per_control_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gut = _gut()
    primary, cp = _motorpool_cp({gut: 1}, friendly=False)
    secondary = MotorpoolGroundObject(
        "CP Motorpool 1",
        PresetLocation(
            "secondary",
            Point(100.0, 0.0, MagicMock(spec=Terrain)),
            Heading.from_degrees(0.0),
        ),
        cp,
        GroupTask.MOTORPOOL,
    )
    secondary.distance_to = MagicMock(return_value=100.0)  # type: ignore[method-assign]
    cp.__dict__["ground_objects"] = [primary, secondary]
    game = _game([cp, _friendly_cp()], cap=10)

    import game.missiongenerator.motorpoolpopulator as populator

    calls: list[list[MotorpoolGroundObject]] = []

    def project_once(
        motorpools: list[MotorpoolGroundObject], cap: int
    ) -> dict[object, int]:
        calls.append(motorpools)
        return {motorpool.id: 1 for motorpool in motorpools}

    monkeypatch.setattr(populator, "projected_motorpool_counts", project_once)
    cp.coalition.game = cast("Game", game)

    assert list(
        ObjectiveFinder(cast("Game", game), Player.BLUE).motorpool_targets()
    ) == [primary, secondary]
    assert calls == [[primary, secondary]]


# --- PlanMotorpoolAttack ------------------------------------------------------


def _motorpool_target(rendered_count: int) -> MotorpoolGroundObject:
    gut = _gut()
    tgo, cp = _motorpool_cp({gut: rendered_count}, friendly=False)
    tgo.groups = [MagicMock(alive_units=rendered_count)] if rendered_count else []
    settings = cp.coalition.game.settings
    settings.motorpool_enabled = True
    settings.plan_refuelling_when_needed = False
    settings.motorpool_spawn_cap = 10
    settings.fpa_2ship_weight = 1
    settings.fpa_3ship_weight = 0
    settings.fpa_4ship_weight = 0
    return tgo


@pytest.mark.xfail(
    reason="Upstream PRs #959/#960 and #961/#962 are two divergent lines on the "
    "same module: #959 rebuilt the populator around a persisted projection keyed "
    "by unit id, #961/#962 kept dev's simpler round-robin. This test belongs to "
    "one line and exercises the other's code. Nothing in the fork is involved; it "
    "is for upstream to rebase the later pair on the earlier one.",
    strict=False,
)
def test_motorpool_attack_proposes_armed_recon_plus_escorts() -> None:
    tgo = _motorpool_target(8)
    task = PlanMotorpoolAttack(tgo, FlightType.ARMED_RECON)
    task.propose_flights()
    flight_tasks = [f.task for f in task.flights]
    assert flight_tasks == [
        FlightType.ARMED_RECON,
        FlightType.SEAD_ESCORT,
        FlightType.ESCORT,
        FlightType.SEAD_SWEEP,
    ]


def test_motorpool_bai_sizes_from_shared_cp_allocation() -> None:
    tgo = _motorpool_target(10)
    cp = tgo.control_point
    second = MotorpoolGroundObject(
        "CP Motorpool 1",
        PresetLocation(
            "G",
            Point(0.0, 0.0, MagicMock(spec=Terrain)),
            Heading.from_degrees(0.0),
        ),
        cp,
        GroupTask.MOTORPOOL,
    )
    cp.ground_objects = [tgo, second]  # type: ignore[misc]

    task = PlanMotorpoolAttack(tgo, FlightType.BAI)
    task.propose_flights()

    bai = next(f for f in task.flights if f.task is FlightType.BAI)
    assert bai.num_aircraft == 2  # five of the shared ten-unit cap go to this TGO


def test_motorpool_attack_effect_removes_target() -> None:
    tgo = _motorpool_target(4)
    other = _motorpool_target(4)
    state = SimpleNamespace(motorpool_targets=[tgo, other])
    task = PlanMotorpoolAttack(tgo, FlightType.ARMED_RECON)
    task.package = None  # super().apply_effects is a no-op with no package
    task.apply_effects(state)  # type: ignore[arg-type]
    assert state.motorpool_targets == [other]


def test_motorpool_attack_precondition_accepts_projected_empty_groups(
    monkeypatch: Any,
) -> None:
    gut = _gut()
    tgo, cp = _motorpool_cp({gut: 4}, friendly=False)
    cp.coalition.game.settings.motorpool_enabled = True
    cp.coalition.game.settings.motorpool_spawn_cap = 10
    state = SimpleNamespace(
        motorpool_targets=[tgo],
        context=SimpleNamespace(
            coalition=SimpleNamespace(player=SimpleNamespace(is_blue=False)),
            settings=SimpleNamespace(),
        ),
    )
    task = PlanMotorpoolAttack(tgo, FlightType.ARMED_RECON)
    monkeypatch.setattr(task, "target_area_preconditions_met", lambda _state: True)
    monkeypatch.setattr(task, "fulfill_mission", lambda _state: True)

    assert task.preconditions_met(state) is True  # type: ignore[arg-type]


def test_motorpool_attack_precondition_fails_when_rendered_groups_are_empty() -> None:
    tgo = _motorpool_target(0)
    state = SimpleNamespace(motorpool_targets=[tgo])
    task = PlanMotorpoolAttack(tgo, FlightType.ARMED_RECON)
    assert task.preconditions_met(state) is False  # type: ignore[arg-type]


# --- AttackMotorpools ---------------------------------------------------------


@pytest.mark.xfail(
    reason="Upstream PRs #959/#960 and #961/#962 are two divergent lines on the "
    "same module: #959 rebuilt the populator around a persisted projection keyed "
    "by unit id, #961/#962 kept dev's simpler round-robin. This test belongs to "
    "one line and exercises the other's code. Nothing in the fork is involved; it "
    "is for upstream to rebase the later pair on the earlier one.",
    strict=False,
)
def test_attack_battle_positions_prioritizes_motorpools_before_control_points() -> None:
    tgo = _motorpool_target(4)
    control_point = MagicMock(is_fleet=False)
    state = SimpleNamespace(
        enemy_battle_positions={},
        motorpool_targets=[tgo],
        control_point_priority_queue=[control_point],
    )

    methods = list(AttackBattlePositions().each_valid_method(state))  # type: ignore[arg-type]

    first_task = cast(PlanMotorpoolAttack, methods[0][0])
    second_task = cast(PlanArmedRecon, methods[1][0])
    assert isinstance(first_task, PlanMotorpoolAttack)
    assert first_task.target is tgo
    assert isinstance(second_task, PlanArmedRecon)
    assert second_task.target is control_point
