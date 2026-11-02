"""GPS movement permissions use current land sectors, not road reachability."""

from __future__ import annotations

import pickle
from types import SimpleNamespace
from typing import Any, cast

from dcs import Point
import pytest

from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition as P,
    MovementDestination,
)
from game.groundmovement.planning import movement_destination, preview_armor_movement
from game.groundmovement.journey import GroundSegment
from game.groundmovement.territory import (
    position_owner,
    require_friendly_position,
    segment_is_friendly,
)
from game.theater.frontline import FrontLine
from game.theater.player import Player
from tests.test_armor_movement_planning import world  # noqa: F401


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_gps_destinations_require_the_moving_side(world: Any, owner: Player) -> None:
    world.a._coalition.player = owner
    world.b._coalition.player = owner
    world.enemy._coalition.player = owner.opponent
    before = pickle.dumps(world.game)
    destination = movement_destination(
        world.game, owner, DestinationKind.POSITION, position=P(50, 10)
    )
    assert destination.position == P(50, 10)
    with pytest.raises(PermissionError, match="friendly territory"):
        movement_destination(
            world.game, owner, DestinationKind.POSITION, position=P(195, 10)
        )
    # A caller constructing its own destination cannot bypass the shared check.
    with pytest.raises(PermissionError, match="friendly territory"):
        preview_armor_movement(
            world.game,
            world.source.id,
            owner,
            [7],
            MovementDestination(DestinationKind.POSITION, P(195, 10)),
        )
    assert pickle.dumps(world.game) == before


def make_front(world: Any, curved: bool = False) -> FrontLine:
    terrain = world.game.theater.terrain
    world.b.position = Point(100000, 100000, terrain)
    world.enemy.position = Point(20000, 0, terrain)
    points = (
        (
            world.a.position,
            Point(0, 10000, terrain),
            Point(20000, 10000, terrain),
            world.enemy.position,
        )
        if curved
        else (world.a.position, world.enemy.position)
    )
    world.a.convoy_routes = {world.enemy: points}
    world.b.convoy_routes.clear()
    world.enemy.convoy_routes = {world.a: tuple(reversed(points))}
    world.a.base.strength = 1
    world.enemy.base.strength = 0.25
    front = FrontLine(world.a, world.enemy, cast(Any, None))
    world.a.front_lines = {world.enemy: front}
    world.enemy.front_lines = {world.a: front}
    return front


def test_current_front_not_nearest_base_divides_the_road(world: Any) -> None:
    front = make_front(world)
    assert front.position.x == pytest.approx(15000)
    assert position_owner(world.game, P(14000, 20)) is Player.BLUE
    assert position_owner(world.game, P(18000, 20)) is Player.RED
    assert position_owner(world.game, P(15000, 20)) is None
    world.a.base.strength = 0.25
    world.enemy.base.strength = 1
    front.update_position()
    assert front.position.x == pytest.approx(5000)
    # Closer to the BLUE base, but already beyond the actual front.
    assert position_owner(world.game, P(8000, 20)) is Player.RED


def test_curved_road_uses_progress_along_the_front_route(world: Any) -> None:
    front = make_front(world, curved=True)
    assert front.position.x == pytest.approx(20000)
    assert front.position.y == pytest.approx(8000)
    assert position_owner(world.game, P(16000, 10010)) is Player.BLUE
    assert position_owner(world.game, P(20010, 4000)) is Player.RED
    assert position_owner(world.game, P(20010, 8000)) is None
    world.game.theater.controlpoints.reverse()
    assert position_owner(world.game, P(16000, 10010)) is Player.BLUE
    assert position_owner(world.game, P(20010, 4000)) is Player.RED


def test_enemy_to_enemy_road_is_not_claimed_by_friendly_access(world: Any) -> None:
    world.enemy.convoy_routes[world.b] = (world.enemy.position, world.b.position)
    world.b._coalition.player = Player.RED
    assert position_owner(world.game, P(160, 20)) is Player.RED
    with pytest.raises(PermissionError):
        require_friendly_position(world.game, Player.BLUE, P(160, 20))


def test_neutral_tied_and_unmapped_control_are_rejected(world: Any) -> None:
    world.enemy._coalition.player = Player.NEUTRAL
    assert position_owner(world.game, P(195, 0)) is Player.NEUTRAL
    with pytest.raises(PermissionError):
        require_friendly_position(world.game, Player.BLUE, P(195, 0))
    assert position_owner(world.game, P(150, 0)) is None
    with pytest.raises(PermissionError):
        require_friendly_position(world.game, Player.BLUE, P(150, 0))
    world.game.theater.controlpoints.clear()
    assert position_owner(world.game, P(0, 0)) is None
    with pytest.raises(PermissionError):
        require_friendly_position(world.game, Player.BLUE, P(0, 0))


def test_a_friendly_fleet_cannot_claim_enemy_land(world: Any) -> None:
    fleet = SimpleNamespace(
        is_fleet=True, position=world.enemy.position, captured=Player.BLUE
    )
    world.game.theater.controlpoints.insert(0, fleet)
    assert position_owner(world.game, P(200, 0)) is Player.RED


def test_gps_control_tracks_capture_without_cached_permissions(world: Any) -> None:
    assert position_owner(world.game, P(110, 0)) is Player.BLUE
    world.b._coalition.player = Player.RED
    assert position_owner(world.game, P(110, 0)) is Player.RED
    with pytest.raises(PermissionError):
        require_friendly_position(world.game, Player.BLUE, P(110, 0))


def test_offroad_leg_cannot_cross_enemy_land_between_friendly_endpoints(
    world: Any,
) -> None:
    for base in world.game.theater.controlpoints:
        base.convoy_routes.clear()
    world.a.position = Point(0, 0, world.game.theater.terrain)
    world.b.position = Point(100, 0, world.game.theater.terrain)
    world.enemy.position = Point(50, 0, world.game.theater.terrain)
    assert position_owner(world.game, P(0, 0)) is Player.BLUE
    assert position_owner(world.game, P(100, 0)) is Player.BLUE
    assert not segment_is_friendly(
        world.game, Player.BLUE, GroundSegment(P(0, 0), P(100, 0), False)
    )
    assert segment_is_friendly(
        world.game, Player.BLUE, GroundSegment(P(0, 0), P(0, 100), False)
    )


def test_offroad_leg_checks_the_whole_line_not_only_its_midpoint(world: Any) -> None:
    for base in world.game.theater.controlpoints:
        base.convoy_routes.clear()
    world.a.position = Point(0, 0, world.game.theater.terrain)
    world.b.position = Point(60, 0, world.game.theater.terrain)
    world.enemy.position = Point(20, 0, world.game.theater.terrain)
    assert position_owner(world.game, P(50, 0)) is Player.BLUE
    assert not segment_is_friendly(
        world.game, Player.BLUE, GroundSegment(P(0, 0), P(100, 0), False)
    )
