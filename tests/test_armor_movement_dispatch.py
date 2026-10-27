"""Dispatched units keep their identities through travel, casualties and delivery."""

from __future__ import annotations

from itertools import count
from dataclasses import replace
import pickle
from typing import Any
from unittest.mock import patch

from dcs import Mission
from dcs.point import PointAction
from dcs.task import OptAlarmState, OptROE
import pytest

from game.debriefing import Debriefing
from game.groundmovement.dispatch import (
    advance_armor,
    dispatch_armor,
    rehome_before_capture,
    stop_armor,
)
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
)
from game.groundmovement.settings import set_enabled
from game.missiongenerator.tgogenerator import GroundObjectGenerator
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from game.unitmap import UnitMap
from tests.test_armor_movement_planning import world  # noqa: F401


def prepare(world: Any) -> Any:
    world.game.turn = 1
    world.game.next_group_id = count(100).__next__
    return world


def dispatch(world: Any, selected: tuple[int, ...] = (1, 2)) -> Any:
    prepare(world)
    return dispatch_armor(
        world.game,
        world.source.id,
        Player.BLUE,
        selected,
        world.destination,
        GameUpdateEvents(),
    )


def detachment(world: Any, transit: Any) -> Any:
    return world.game.db.tgos.get(transit.detachment_id)


def test_partial_detachment_moves_existing_objects_and_reserves_tractors(
    world: Any,
) -> None:
    identities = {u.id: u for u in world.source.units}
    transit = dispatch(world)
    moving = detachment(world, transit)
    assert {u.id for u in moving.units} == {1, 2, 5, 6}
    assert all(
        u is identities[u.id] and u.ground_object is moving for u in moving.units
    )
    assert {u.id for u in world.source.units} == {3, 4, 7, 8}
    assert {u.id: u.transported_by_id for u in moving.units if u.transported_by_id} == {
        1: 5,
        2: 6,
    }
    assert not moving.purchasable and not identities[1].repairable
    assert identities[1].threat_range.meters == 0
    with pytest.raises(ValueError, match="Stop this detachment"):
        dispatch_armor(
            world.game,
            moving.id,
            Player.BLUE,
            (5,),
            world.destination,
            GameUpdateEvents(),
        )


def test_stale_or_invalid_dispatch_does_not_remove_source_inventory(world: Any) -> None:
    prepare(world)
    before = list(world.source.units)
    with pytest.raises(ValueError, match="tractors"):
        dispatch_armor(
            world.game,
            world.source.id,
            Player.BLUE,
            (1, 2, 3),
            world.destination,
            GameUpdateEvents(),
        )
    assert list(world.source.units) == before
    assert (
        not world.game.ground_movements.orders
        and not world.game.ground_movements.transits
    )


def test_base_delivery_applies_losses_before_commissioning_and_is_idempotent(
    world: Any,
) -> None:
    transit = dispatch(world)
    moving = detachment(world, transit)
    next(u for u in moving.units if u.id == 5).kill(GameUpdateEvents())
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and not list(moving.units)
    assert world.b.base.armor[world.units[1]] == 1
    assert world.b.base.armor[world.units[5]] == 1
    advance_armor(world.game, GameUpdateEvents())
    assert sum(world.b.base.armor.values()) == 2
    assert not world.game.ground_movements.reserved_unit_ids


def test_position_arrival_unloads_and_retains_surviving_identities(world: Any) -> None:
    prepare(world)
    point = MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10))
    transit = dispatch_armor(
        world.game, world.source.id, Player.BLUE, (1,), point, GameUpdateEvents()
    )
    moving = detachment(world, transit)
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and {u.id for u in moving.units} == {1, 5}
    assert moving.position.x == 90 and moving.position.y == 10
    assert moving.purchasable and all(u.transported_by_id is None for u in moving.units)
    assert not world.b.base.armor


def test_disabled_orders_and_captured_destinations_pause_without_delivery(
    world: Any,
) -> None:
    transit = dispatch(world)
    set_enabled(world.game.settings, False)
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.pause_reason and transit.journey.travelled_distance == 0
    set_enabled(world.game.settings, True)
    world.b._coalition = world.enemy.coalition
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert not transit.finished and "another side" in transit.pause_reason
    assert not world.b.base.armor
    world.b._coalition = world.a.coalition
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished


def test_reload_multiturn_progress_and_stop_keep_current_position(world: Any) -> None:
    transit = dispatch(world, (7,))
    # Use a deliberately long route, without changing the configured speed rules.
    from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment

    transit.journey = GroundJourney(
        GroundRoute(
            (GroundSegment(GroundPosition(10, 10), GroundPosition(500000, 10), False),)
        ),
        last_advanced_turn=1,
    )
    # Large synthetic land map for this fixture only.
    from shapely.geometry import MultiPolygon, box

    world.game.theater.landmap = replace(
        world.game.theater.landmap,
        inclusion_zones=MultiPolygon([box(-1000, -1000, 600000, 1000)]),
    )
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    first = transit.journey.position
    assert first.x > 10 and not transit.finished
    advance_armor(world.game, GameUpdateEvents())
    assert transit.journey.position == first
    # The saved order store has no runtime callbacks or native DCS objects.
    loaded = pickle.loads(pickle.dumps(world.game.ground_movements))
    assert loaded.transits[transit.order_id].journey.position == first
    world.game.ground_movements = loaded
    stop_armor(world.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    moving = detachment(world, transit)
    assert moving.position.x == first.x and not moving.in_transit
    assert loaded.orders[transit.order_id].cancelled


def test_origin_capture_rehomes_departed_detachment_without_losing_units(
    world: Any,
) -> None:
    transit = dispatch(world)
    moving = detachment(world, transit)
    rehome_before_capture(world.game, world.a, GameUpdateEvents())
    assert (
        moving.control_point is world.b and moving not in world.a.connected_objectives
    )
    assert moving in world.b.connected_objectives and len(list(moving.units)) == 4


def native(world: Any, transit: Any) -> tuple[Any, UnitMap]:
    from types import SimpleNamespace as NS

    mission = Mission()
    # The fixture uses local metric positions; use its terrain for native coordinates.
    mission.terrain = world.game.theater.terrain
    country = mission.country("USA")
    moving = detachment(world, transit)
    world.game.iads_considerate_culling = lambda _: False
    world.game.settings.set_plugin_option("skynetiads", False)
    world.a.coalition.faction = NS(country=country)
    unit_map = UnitMap()
    generator = GroundObjectGenerator(moving, country, world.game, mission, unit_map)
    with patch("game.missiongenerator.tgogenerator.GroundForcePainter"), patch(
        "game.missiongenerator.tgogenerator.shows_on_mfd", return_value=True
    ):
        generator.generate()
    return country.vehicle_group[0], unit_map


def test_native_loaded_guns_are_omitted_and_tractor_deaths_report_both_losses(
    world: Any,
) -> None:
    from types import SimpleNamespace as NS

    transit = dispatch(world)
    group, unit_map = native(world, transit)
    assert len(group.units) == 2 and all(u.type == "Ural-375" for u in group.units)
    assert len(group.points) >= 2 and group.points[0].speed > 0
    assert group.points[0].ETA_locked and group.points[0].ETA == 0
    assert all(
        not point.ETA_locked and point.speed_locked for point in group.points[1:]
    )
    exported = group.dict()["route"]["points"]
    assert exported[1]["ETA_locked"] and exported[1]["ETA"] == 0
    assert all(not point["ETA_locked"] for i, point in exported.items() if i > 1)
    assert group.points[0].action == PointAction.OffRoad
    assert group.points[1].position != group.points[0].position
    truck = group.units[0]
    fake: Any = NS(
        unit_map=unit_map,
        state_data=NS(killed_ground_units=[str(truck.name)], killed_aircraft=[]),
    )
    losses = Debriefing.dead_ground_units(fake)
    assert {m.theater_unit.id for m in losses.player_ground_objects} == {1, 5}


def test_paused_detachment_stays_attackable_with_loaded_cargo(world: Any) -> None:
    transit = dispatch(world)
    set_enabled(world.game.settings, False)
    group, unit_map = native(world, transit)
    assert len(group.points) == 1 and group.points[0].speed == 0
    assert len(unit_map.ground_transport_cargo) == 2
    assert any(isinstance(task, OptAlarmState) for task in group.points[0].tasks)


def test_convoy_corridor_in_exclusion_keeps_moving_across_turns(world: Any) -> None:
    from shapely.geometry import MultiPolygon, box

    world.b.position.x = 2000
    world.destination = replace(world.destination, position=GroundPosition(2000, 0))
    world.game.theater.landmap = replace(
        world.game.theater.landmap,
        exclusion_zones=MultiPolygon([box(1000, -100, 1800, 100)]),
    )
    world.game.settings.set_plugin_option("groundmovement.roadMilesPerTurn", 1)
    transit = dispatch(world, (7,))
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert 1000 < transit.journey.position.x < 1800
    assert not transit.finished and not transit.pause_reason
    world.game.ground_movements = pickle.loads(
        pickle.dumps(world.game.ground_movements)
    )
    transit = world.game.ground_movements.transits[transit.order_id]
    group, _ = native(world, transit)
    assert len(group.points) >= 2 and group.points[0].speed > 0
    assert all(p.action == PointAction.OnRoad for p in group.points)
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and world.b.base.armor[world.units[7]] == 1


@pytest.mark.parametrize("red_alert", [False, True])
def test_moving_detachments_drop_only_the_stationary_alarm_override(
    world: Any, red_alert: bool
) -> None:
    world.game.settings.perf_red_alert_state = red_alert
    transit = dispatch(world)
    with patch.object(
        GroundObjectGenerator,
        "set_coastal_engagement",
        side_effect=lambda group: group.points[0].tasks.append(
            OptROE(OptROE.Values.WeaponFree)
        ),
    ):
        group, _ = native(world, transit)
    tasks = group.points[0].tasks
    assert not any(isinstance(task, OptAlarmState) for task in tasks)
    assert any(isinstance(task, OptROE) for task in tasks)
    initial = group.dict()["route"]["points"][1]["task"]["params"]["tasks"]
    assert all(
        task["params"]["action"]["params"].get("name") != 9 for task in initial.values()
    )


def test_frontline_arrivals_enter_supporting_base_stock(world: Any) -> None:
    from game.groundmovement.planning import movement_destination

    prepare(world)
    destination = movement_destination(
        world.game,
        Player.BLUE,
        DestinationKind.FRONTLINE,
        base_id=world.a.id,
        opposing_base_id=world.enemy.id,
    )
    transit = dispatch_armor(
        world.game, world.source.id, Player.BLUE, (7,), destination, GameUpdateEvents()
    )
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and world.a.base.armor[world.units[7]] == 1
    assert not list(detachment(world, transit).units)


def test_old_saved_orders_gain_an_empty_transit_store(world: Any) -> None:
    orders = world.game.ground_movements
    del orders.transits
    restored = pickle.loads(pickle.dumps(orders))
    assert restored.transits == {}


def test_dispatch_rejects_wrong_owner_without_mutation(world: Any) -> None:
    prepare(world)
    before = list(world.source.units)
    with pytest.raises(PermissionError):
        dispatch_armor(
            world.game,
            world.source.id,
            Player.RED,
            (7,),
            world.destination,
            GameUpdateEvents(),
        )
    assert list(world.source.units) == before and not world.game.ground_movements.orders
