"""Reserve units already at a base can join its stock without a journey."""

from __future__ import annotations

import pickle
from typing import Any

import pytest

from game.groundmovement.dispatch import advance_armor, dispatch_armor, stop_armor
from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
    MovementSource,
)
from game.groundmovement.planning import movement_destination, preview_armor_movement
from game.groundmovement.report import movement_reports
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401


def local_destination(world: Any, owner: Player, kind: DestinationKind) -> Any:
    world.a._coalition.player = world.b._coalition.player = owner
    world.enemy._coalition.player = Player.RED if owner is Player.BLUE else Player.BLUE
    world.source.position = world.a.position
    return movement_destination(
        world.game,
        owner,
        kind,
        base_id=world.a.id,
        opposing_base_id=world.enemy.id if kind is DestinationKind.FRONTLINE else None,
    )


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("kind", [DestinationKind.BASE, DestinationKind.FRONTLINE])
def test_local_preview_is_read_only_and_dispatch_commissions_once(
    world: Any, owner: Player, kind: DestinationKind
) -> None:
    prepare(world)
    destination = local_destination(world, owner, kind)
    before = pickle.dumps(world.game)
    preview = preview_armor_movement(
        world.game, world.source.id, owner, (7,), destination
    )
    assert preview.arrival_in_turns == preview.travel_turns == 0
    assert preview.road_distance_m == preview.offroad_distance_m == 0
    assert preview.route.length == 0 and not preview.route.segments
    assert preview.first_turn_stop == destination.position
    assert pickle.dumps(world.game) == before

    events = GameUpdateEvents()
    transit = dispatch_armor(
        world.game, world.source.id, owner, (7,), destination, events
    )
    delivered = world.game.db.tgos.get(transit.detachment_id)
    assert transit.finished and transit.journey.completed
    assert world.a.base.armor == {world.units[7]: 1}
    assert {u.id for u in world.source.units} == {1, 2, 3, 4, 5, 6, 8}
    assert not list(delivered.units) and not delivered.in_transit
    assert not world.game.ground_movements.reserved_unit_ids
    report = movement_reports(world.game, world.source.id, owner)[0]
    assert report.status == "arrived" and report.progress == 1
    assert report.total_distance_m == report.remaining_distance_m == 0
    assert report.surviving_units == 1 and report.position == destination.position
    restored = pickle.loads(pickle.dumps(world.game))
    assert movement_reports(restored, world.source.id, owner)[0] == report
    world.game.turn += 1
    advance_armor(world.game, events)
    stop_armor(world.game, transit.order_id, owner, events)
    with pytest.raises(ValueError, match="unavailable"):
        dispatch_armor(world.game, world.source.id, owner, (7,), destination, events)
    assert world.a.base.armor == {world.units[7]: 1}


def test_local_delivery_retains_transport_and_availability_checks(world: Any) -> None:
    prepare(world)
    destination = local_destination(world, Player.BLUE, DestinationKind.BASE)
    with pytest.raises(ValueError, match="tractors"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, (1, 2, 3), destination
        )
    for selected in ((8,), (999,)):
        with pytest.raises(ValueError, match="unavailable"):
            preview_armor_movement(
                world.game, world.source.id, Player.BLUE, selected, destination
            )
    world.game.ground_movements.plan(
        world.game.settings,
        source_id=world.source.id,
        source_kind=MovementSource.ARMOR,
        owner=Player.BLUE,
        origin=destination.position,
        destination=destination,
        units=world.units,
        selected=(7,),
        turn=world.game.turn,
    )
    with pytest.raises(ValueError, match="unavailable"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, (7,), destination
        )
    transit = dispatch_armor(
        world.game,
        world.source.id,
        Player.BLUE,
        (1, 2),
        destination,
        GameUpdateEvents(),
    )
    assert transit.finished and world.a.base.armor == {
        world.units[1]: 2,
        world.units[5]: 2,
    }
    assert {u.id for u in world.source.units} == {3, 4, 7, 8}


def test_stationary_journey_preserves_position_after_reload() -> None:
    position = GroundPosition(10, 20)
    journey = GroundJourney(GroundRoute((), stationary_at=position))
    assert journey.completed and journey.position == position
    assert journey.preview(100, 50) == (position,)
    restored = pickle.loads(pickle.dumps(journey))
    assert restored.advance(1, 100, 50) == (position,)
    assert restored.remaining_distance == restored.travelled_distance == 0


def test_local_reinforcement_does_not_enable_zero_length_gps_moves(world: Any) -> None:
    prepare(world)
    base = local_destination(world, Player.BLUE, DestinationKind.BASE)
    destination = MovementDestination(DestinationKind.POSITION, base.position)
    before = pickle.dumps(world.game)
    with pytest.raises(ValueError, match="already at that position"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, (7,), destination
        )
    assert pickle.dumps(world.game) == before


def test_legacy_route_without_stationary_field_still_loads() -> None:
    start, end = GroundPosition(10, 20), GroundPosition(30, 40)
    route = GroundRoute((GroundSegment(start, end),))
    route.__dict__.pop("stationary_at")
    restored = pickle.loads(pickle.dumps(route))
    journey = GroundJourney(restored)
    assert journey.position == start
    journey.advance(1, 100, 50)
    assert journey.completed and journey.position == end


def test_stationary_route_cannot_also_contain_travel_segments() -> None:
    start, end = GroundPosition(10, 20), GroundPosition(30, 40)
    with pytest.raises(ValueError, match="cannot contain segments"):
        GroundRoute((GroundSegment(start, end),), stationary_at=start)
