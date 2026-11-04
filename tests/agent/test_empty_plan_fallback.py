"""An empty ATO does not mean the external commander has issued no orders."""

from datetime import datetime
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from dcs import Mission
from dcs.lua import loads
from dcs.mapping import Point
from dcs.point import PointAction
from dcs.vehicles import Armor

from game import Game
from game.agent import planner, schemas, service
from game.ground_forces.ai_ground_planner import CombatGroupRole
from game.ground_forces.combat_stance import CombatStance
from game.missiongenerator.flotgenerator import FlotGenerator
from game.theater.player import Player
from game.utils import Heading


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> Any:
    own = SimpleNamespace(stances={"enemy": CombatStance.DEFENSIVE})
    red = SimpleNamespace(ato=SimpleNamespace(packages=[]), plan_missions=Mock())
    game = SimpleNamespace(
        turn=17,
        opfor_ai_orders_turn=None,
        settings=SimpleNamespace(opfor_ai_enabled=True),
        conditions=SimpleNamespace(start_time=datetime(2020, 1, 1)),
        red=red,
        theater=SimpleNamespace(control_points_for=Mock(return_value=[own])),
    )
    monkeypatch.setattr(service, "_require_game", lambda: game)
    return SimpleNamespace(game=game, own=own, red=red)


def test_ground_order_keeps_an_empty_air_plan(state: Any) -> None:
    state.own.id = uuid4()
    state.own.name = "Own base"
    enemy = SimpleNamespace(id=uuid4(), name="Enemy base")
    state.own.stances = {enemy.id: CombatStance.DEFENSIVE}
    state.game.theater.find_control_point_by_id = lambda uid: (
        state.own if uid == state.own.id else enemy
    )
    assert service.set_stance("red", str(state.own.id), str(enemy.id), "defend").ok
    assert state.game.opfor_ai_orders_turn == 17
    assert not service.run_opfor_fallback_if_needed()["ran"]
    state.red.plan_missions.assert_not_called()
    assert state.own.stances[enemy.id] is CombatStance.DEFENSIVE


def test_explicitly_clearing_an_empty_ato_counts_as_an_order(state: Any) -> None:
    state.game.coalition_for = lambda _: state.red
    state.red.ato.clear = state.red.ato.packages.clear
    assert service.clear_packages("red").ok
    assert not service.run_opfor_fallback_if_needed()["ran"]


@pytest.mark.parametrize(
    "result,expected",
    [
        (schemas.OpResult(ok=True), True),
        (schemas.OpResult(ok=False, error="rejected"), False),
        ({"ok": True}, True),
        ({"ok": False}, False),
        ({"error": "rejected"}, False),
        ({"status": "moving"}, True),
        ([], False),
        ([schemas.CreateResult(ok=False, target="target")], False),
        (
            [
                schemas.CreateResult(ok=False, target="first"),
                schemas.CreateResult(ok=True, target="second"),
            ],
            True,
        ),
    ],
)
def test_only_successful_orders_suppress_fallback(
    state: Any, result: Any, expected: bool
) -> None:
    @service.opfor_order
    def order(side: str) -> Any:
        return result

    assert order("red") is result
    assert (state.game.opfor_ai_orders_turn == 17) is expected


def test_exceptions_and_blue_orders_do_not_mark_the_turn(state: Any) -> None:
    @service.opfor_order
    def order(side: str) -> Any:
        raise ValueError("rejected")

    with pytest.raises(service.SideNotAllowedError):
        order("blue")
    with pytest.raises(ValueError):
        order("red")
    assert state.game.opfor_ai_orders_turn is None


def test_reads_and_previews_do_not_mark_the_turn(
    state: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service.views, "build_packages", lambda *_: [])
    monkeypatch.setattr(planner, "validate_plan", lambda *_: schemas.OpResult(ok=True))
    monkeypatch.setattr(
        planner, "evaluate_package", lambda *_: schemas.OpResult(ok=True)
    )
    service.get_packages("red")
    service.validate_plan("red")
    service.evaluate_package("red", {})
    assert state.game.opfor_ai_orders_turn is None
    assert service.run_opfor_fallback_if_needed()["ran"]


def test_marker_expires_at_next_turn_and_fallback_runs_only_once(state: Any) -> None:
    state.game.opfor_ai_orders_turn = 17
    state.game.turn = 18
    assert service.run_opfor_fallback_if_needed()["ran"]
    assert state.game.opfor_ai_orders_turn == 18
    assert not service.run_opfor_fallback_if_needed()["ran"]
    state.red.plan_missions.assert_called_once_with(state.game.conditions.start_time)


def test_existing_packages_and_disabled_opfor_still_skip_fallback(state: Any) -> None:
    state.red.ato.packages.append(object())
    assert not service.run_opfor_fallback_if_needed()["ran"]
    state.red.ato.packages.clear()
    state.game.settings.opfor_ai_enabled = False
    assert not service.run_opfor_fallback_if_needed()["ran"]
    state.red.plan_missions.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_legacy_fallback_restores_ground_orders_even_on_error(
    state: Any, fail: bool
) -> None:
    del state.game.opfor_ai_orders_turn

    def replan(_: datetime) -> None:
        state.own.stances["enemy"] = CombatStance.RETREAT
        state.own.stances["other"] = CombatStance.AGGRESSIVE
        if fail:
            raise ValueError("planning failed")

    state.red.plan_missions.side_effect = replan
    if fail:
        with pytest.raises(ValueError):
            service.run_opfor_fallback_if_needed()
        assert not hasattr(state.game, "opfor_ai_orders_turn")
    else:
        assert service.run_opfor_fallback_if_needed()["ran"]
    assert state.own.stances == {"enemy": CombatStance.DEFENSIVE}
    state.game.theater.control_points_for.assert_called_once_with(Player.RED)


@pytest.mark.parametrize("marker", [None, 0, 17])
def test_order_marker_survives_save_load_and_defaults_for_old_saves(
    monkeypatch: pytest.MonkeyPatch, marker: int | None
) -> None:
    monkeypatch.setattr(Game, "on_load", lambda self: None)
    game = Game.__new__(Game)
    state: dict[str, Any] = {"theater": SimpleNamespace(conflicts=list)}
    if marker is not None:
        state["opfor_ai_orders_turn"] = marker
    game.__setstate__(state)
    assert game.opfor_ai_orders_turn == marker
    assert pickle.loads(pickle.dumps(game)).opfor_ai_orders_turn == marker


def test_fallback_generates_defensive_tank_route_not_a_20km_retreat(
    state: Any, tmp_path: Path
) -> None:
    del state.game.opfor_ai_orders_turn
    state.red.plan_missions.side_effect = lambda _: state.own.stances.update(
        enemy=CombatStance.RETREAT
    )
    assert service.run_opfor_fallback_if_needed()["ran"]

    mission = Mission()
    state.own.position = Point(-50000, 0, mission.terrain)
    group = mission.vehicle_group(
        mission.country("Russia"),
        "Defenders",
        Armor.T_90,
        position=Point(0, 0, mission.terrain),
        group_size=2,
    )
    generator: Any = FlotGenerator.__new__(FlotGenerator)
    generator.mission = mission
    generator.game = SimpleNamespace(settings=SimpleNamespace(perf_moving_units=True))
    generator.conflict = SimpleNamespace(
        theater=SimpleNamespace(is_on_land=lambda _: True)
    )
    generator.wpt_pointaction = PointAction.OffRoad
    generator.plan_action_for_groups(
        state.own.stances["enemy"],
        [(group, SimpleNamespace(role=CombatGroupRole.TANK))],
        [],
        Heading.from_degrees(90),
        state.own,
        SimpleNamespace(),
    )
    output = tmp_path / "defensive-front.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        native = loads(archive.read("mission").decode("utf-8"))["mission"]
    country = next(
        country
        for country in native["coalition"]["red"]["country"].values()
        if "vehicle" in country
    )
    native_group = next(iter(country["vehicle"]["group"].values()))
    assert len(native_group["units"]) == 2
    points = native_group["route"]["points"]
    assert len(points) == 3  # Spawn, defensive hold, triggered morale fallback.
    assert points[2]["x"] == pytest.approx(0, abs=1e-6)
    assert points[2]["y"] == pytest.approx(50)
    tasks = points[2]["task"]["params"]["tasks"].values()
    assert any(task["id"] == "Hold" for task in tasks)
    assert max(abs(point["y"]) for point in points.values()) == pytest.approx(2500)
