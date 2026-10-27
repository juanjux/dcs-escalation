"""Reached reserves reinforce their own front exactly once, including active moves."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
import pickle
from typing import Any

from dcs import Point
import pytest
from shapely.geometry import MultiPolygon, box

from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import deployable_armor, reserve_armor_for
from game.groundmovement.dispatch import advance_armor, _relocate
from game.groundmovement.frontline import integrate_reached_reserves, snapshot_fronts
from game.groundmovement.orders import GroundPosition
from game.groundmovement.report import movement_reports
from game.groundmovement.settings import set_enabled
from game.lasercodes.lasercoderegistry import LaserCodeRegistry
from game.sim.gameupdateevents import GameUpdateEvents
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.theater.frontline import FrontLine, FrontLineSegment
from game.theater.player import Player
from game.theater.theatergroundobject import MotorpoolGroundObject, SamGroundObject
from game.theater.presetlocation import PresetLocation
from tests.test_armor_movement_dispatch import dispatch, detachment
from tests.test_armor_movement_planning import world  # noqa: F401


def record_message(messages: list[Any], *args: str) -> None:
    messages.append(args)


@pytest.fixture
def front(world: Any) -> Any:
    w = world
    w.enemy.position = Point(100000, 0, w.game.theater.terrain)
    w.a.convoy_routes[w.enemy] = (w.a.position, w.enemy.position)
    w.a.connected_points.append(w.enemy)
    w.enemy.connected_points.append(w.a)
    w.game.theater.landmap = replace(
        w.game.theater.landmap,
        inclusion_zones=MultiPolygon([box(-10000, -10000, 110000, 10000)]),
    )
    w.game.settings.max_frontline_width = 2
    for cp in (w.a, w.b, w.enemy):
        cp.coalition.game = w.game
    w.line = FrontLine(w.a, w.enemy, LaserCodeRegistry().alloc_laser_code())
    w.a.front_lines[w.enemy] = w.line
    w.enemy.front_lines[w.a] = w.line
    w.game.db.front_lines.add(w.line.id, w.line)
    _relocate(w.source, GroundPosition(45000, 0))
    w.messages = []
    w.game.messages = w.messages
    w.game.message = partial(record_message, w.messages)
    return w


def shift(w: Any, blue: float, red: float) -> None:
    w.a.base.strength, w.enemy.base.strength = blue, red
    w.line.update_position()


def test_stationary_survivors_integrate_once_and_disappear(front: Any) -> None:
    w = front
    before = snapshot_fronts(w.game)
    assert len(before) == 1
    shift(w, 0.4, 0.6)
    events = GameUpdateEvents().update_tgo(w.source)
    integrate_reached_reserves(w.game, before, events)
    assert w.a.base.armor == {w.units[1]: 4, w.units[5]: 2, w.units[7]: 1}
    assert not list(w.source.units) and not w.source.purchasable
    assert w.source not in w.a.connected_objectives
    assert w.game.db.tgos.get(w.source.id) is w.source  # Historical references.
    assert events.deleted_tgos == {w.source.id}
    assert w.source not in events.updated_tgos
    assert w.a in events.updated_control_points
    assert len(w.messages) == 1
    before_reload = pickle.dumps(w.a.base.armor)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert pickle.dumps(w.a.base.armor) == before_reload
    assert len(w.messages) == 1


@pytest.mark.parametrize("x,y", [(39000, 0), (51000, 0), (45000, 1002)])
def test_groups_not_reached_or_outside_front_width_are_untouched(
    front: Any, x: float, y: float
) -> None:
    w = front
    _relocate(w.source, GroundPosition(x, y))
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.a.base.total_armor == 0 and w.source in w.a.connected_objectives
    assert w.source.alive_unit_count == 7


@pytest.mark.parametrize("x", [40000, 50000])
def test_front_reaches_inclusive_sweep_boundaries(front: Any, x: float) -> None:
    _relocate(front.source, GroundPosition(x, 0))
    before = snapshot_fronts(front.game)
    shift(front, 0.4, 0.6)
    integrate_reached_reserves(front.game, before, GameUpdateEvents())
    assert front.a.base.total_armor == 7


def test_a_front_moving_away_does_not_absorb_friendly_reserves(front: Any) -> None:
    before = snapshot_fronts(front.game)
    shift(front, 0.6, 0.4)
    integrate_reached_reserves(front.game, before, GameUpdateEvents())
    assert front.a.base.total_armor == 0 and front.source.unit_count == 8


def test_red_reserves_join_red_stock_when_blue_advances(front: Any) -> None:
    w = front
    w.a.connected_objectives.remove(w.source)
    w.source.control_point = w.enemy
    w.enemy.connected_objectives.append(w.source)
    _relocate(w.source, GroundPosition(55000, 300))
    before = snapshot_fronts(w.game)
    shift(w, 0.6, 0.4)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.enemy.base.total_armor == 7 and w.a.base.total_armor == 0
    assert w.source.absorbed_into_frontline == w.enemy.id


def test_receiving_front_base_need_not_be_the_administrative_origin(front: Any) -> None:
    w = front
    w.a.connected_objectives.remove(w.source)
    w.source.control_point = w.b
    w.b.connected_objectives.append(w.source)
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.a.base.total_armor == 7 and w.b.base.total_armor == 0
    assert w.source not in w.b.connected_objectives


def test_capped_front_keeps_all_additional_units_in_reserve(front: Any) -> None:
    w = front
    w.a.base.commission_units({w.units[7]: w.a.frontline_unit_count_limit})
    initial = w.a.base.total_armor
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    deployed = deployable_armor(w.a)
    reserve = reserve_armor_for(w.a)
    assert w.a.base.total_armor == initial + 7
    assert sum(deployed.values()) == w.a.frontline_unit_count_limit
    assert sum(reserve.values()) == 7
    assert all(
        deployed.get(u, 0) + reserve.get(u, 0) == n for u, n in w.a.base.armor.items()
    )


def test_active_order_is_completed_without_a_further_move_or_cargo_resurrection(
    front: Any,
) -> None:
    w = front
    transit = dispatch(w)
    moving = detachment(w, transit)
    # Exclude the untouched parent from this particular reach comparison.
    _relocate(w.source, GroundPosition(10000, 0))
    next(u for u in moving.units if u.id == 5).alive = False
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    events = GameUpdateEvents()
    integrate_reached_reserves(w.game, before, events)
    assert transit.finished and transit.final_unit_count == 2
    assert w.game.ground_movements.orders[transit.order_id].completed
    assert not w.game.ground_movements.orders[transit.order_id].cancelled
    assert w.a.base.armor == {w.units[1]: 1, w.units[5]: 1}
    assert not list(moving.units) and not w.game.ground_movements.reserved_unit_ids
    report = movement_reports(w.game, moving.id, Player.BLUE)[0]
    assert report.status == "integrated" and report.surviving_units == 2
    start = transit.journey.position
    w.game.turn += 1
    advance_armor(w.game, GameUpdateEvents())
    assert transit.journey.position == start and w.b.base.total_armor == 0


@pytest.mark.parametrize("option", ["plugin", "motorpool"])
def test_disabled_dependency_keeps_groups_and_orders_unchanged(
    front: Any, option: str
) -> None:
    if option == "plugin":
        set_enabled(front.game.settings, False)
    else:
        front.game.settings.motorpool_enabled = False
    before = snapshot_fronts(front.game)
    shift(front, 0.4, 0.6)
    integrate_reached_reserves(front.game, before, GameUpdateEvents())
    assert not before and front.a.base.total_armor == 0
    assert front.source in front.a.connected_objectives


@pytest.mark.parametrize("kind", ["sam", "motorpool", "neutral", "dead"])
def test_non_reserves_neutral_and_destroyed_groups_are_not_absorbed(
    front: Any, kind: str
) -> None:
    w = front
    if kind in ("sam", "motorpool"):
        cls = SamGroundObject if kind == "sam" else MotorpoolGroundObject
        excluded = cls(
            "Excluded", PresetLocation("Excluded", w.source.position), w.a, None
        )
        excluded.groups, w.source.groups = w.source.groups, []
        w.a.connected_objectives.append(excluded)
    elif kind == "neutral":
        w.b.coalition.player = Player.NEUTRAL
        w.source.control_point = w.b
    else:
        for unit in w.source.units:
            unit.alive = False
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    events = GameUpdateEvents()
    integrate_reached_reserves(w.game, before, events)
    assert w.a.base.total_armor == 0 and not events.deleted_tgos


def test_exclusion_zone_limits_the_lateral_front(front: Any) -> None:
    w = front
    _relocate(w.source, GroundPosition(45000, 800))
    w.game.theater.landmap = replace(
        w.game.theater.landmap,
        exclusion_zones=MultiPolygon([box(44000, 400, 46000, 600)]),
    )
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.a.base.total_armor == 0


def test_curved_campaign_route_uses_its_progress_not_straight_base_distance(
    front: Any,
) -> None:
    w = front
    a, b, c = (
        Point(x, z, w.game.theater.terrain)
        for x, z in ((0, 0), (30000, 0), (30000, 70000))
    )
    w.line.segments = [FrontLineSegment(a, b), FrontLineSegment(b, c)]
    w.enemy.position = c
    w.game.theater.landmap = replace(
        w.game.theater.landmap,
        inclusion_zones=MultiPolygon([box(-10000, -10000, 110000, 110000)]),
    )
    w.line.update_position()
    _relocate(w.source, GroundPosition(30500, 15000))
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.a.base.total_armor == 7


def test_exact_variants_survive_integration(
    front: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    variant = replace(front.units[7], variant_id="Integration variant")
    monkeypatch.setitem(GroundUnitType._by_name, variant.variant_id, variant)
    next(u for u in front.source.units if u.id == 7).ground_unit_variant = (
        variant.variant_id
    )
    before = snapshot_fronts(front.game)
    shift(front, 0.4, 0.6)
    integrate_reached_reserves(front.game, before, GameUpdateEvents())
    assert front.a.base.armor[variant] == 1 and front.units[7] not in front.a.base.armor


def test_oblique_road_accepts_a_group_within_the_displayed_front_width(
    front: Any,
) -> None:
    w = front
    end = Point(80000, 60000, w.game.theater.terrain)
    w.line.segments = [FrontLineSegment(w.a.position, end)]
    w.enemy.position = end
    w.game.theater.landmap = replace(
        w.game.theater.landmap,
        inclusion_zones=MultiPolygon([box(-10000, -10000, 110000, 110000)]),
    )
    w.line.update_position()
    # 45 km along the road, 800 m off its axis, inside the 2 km front width.
    _relocate(w.source, GroundPosition(36000 - 480, 27000 + 640))
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    assert w.a.base.total_armor == 7


def test_serialized_deletion_wins_over_an_earlier_unit_loss_update(front: Any) -> None:
    from game.server.eventstream.models import GameUpdateEventsJs

    events = GameUpdateEvents().update_tgo(front.source).delete_tgo(front.source)
    events.update_tgo(front.source)
    payload = GameUpdateEventsJs.from_events(events, None)
    assert payload.deleted_tgos == {front.source.id} and not payload.updated_tgos


def test_result_processor_refreshes_the_front_and_integrates_before_capture(
    front: Any,
) -> None:
    w = front
    before = snapshot_fronts(w.game)
    w.a.base.strength, w.enemy.base.strength = 0.4, 0.6
    assert w.line.position.x == 50000
    processor = MissionResultsProcessor(w.game)
    processor.commit_frontline_reserves(before, GameUpdateEvents())
    assert w.line.position.x == 40000 and w.a.base.total_armor == 7


def test_reload_after_active_absorption_cannot_deliver_or_repair_units_twice(
    front: Any,
) -> None:
    w = front
    transit = dispatch(w)
    moving = detachment(w, transit)
    _relocate(w.source, GroundPosition(10000, 0))
    before = snapshot_fronts(w.game)
    shift(w, 0.4, 0.6)
    integrate_reached_reserves(w.game, before, GameUpdateEvents())
    game = pickle.loads(pickle.dumps(w.game))
    base = next(cp for cp in game.theater.controlpoints if cp.id == w.a.id)
    old_group = game.db.tgos.get(moving.id)
    assert old_group.absorbed_into_frontline == base.id and not old_group.purchasable
    assert old_group not in base.connected_objectives and old_group.unit_count == 0
    initial = dict(base.base.armor)
    integrate_reached_reserves(game, snapshot_fronts(game), GameUpdateEvents())
    game.turn += 1
    advance_armor(game, GameUpdateEvents())
    assert base.base.armor == initial and len(game.messages) == 1
    assert movement_reports(game, moving.id, Player.BLUE)[0].status == "integrated"


def test_newly_created_front_does_not_absorb_distant_reserves(front: Any) -> None:
    integrate_reached_reserves(front.game, (), GameUpdateEvents())
    assert front.a.base.total_armor == 0 and front.source.unit_count == 8


def test_a_late_update_in_another_batch_cannot_restore_an_absorbed_marker(
    front: Any,
) -> None:
    before = snapshot_fronts(front.game)
    shift(front, 0.4, 0.6)
    integrate_reached_reserves(front.game, before, GameUpdateEvents())
    later = GameUpdateEvents().update_tgo(front.source)
    assert not later.updated_tgos and later.deleted_tgos == {front.source.id}


def test_front_at_stationary_reserve_position_absorbs_without_an_extra_radius(
    front: Any,
) -> None:
    _relocate(front.source, GroundPosition(50000, 400))
    integrate_reached_reserves(
        front.game, snapshot_fronts(front.game), GameUpdateEvents()
    )
    assert front.a.base.total_armor == 7
