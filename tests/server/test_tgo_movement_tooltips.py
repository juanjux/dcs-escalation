"""Movement destinations are derived from active orders, not stale source sites."""

from dataclasses import replace
from typing import Any

import pytest
from dcs import Point

from game.coordinates import CoordinateFormat, format_dd
from game.groundmovement.dispatch import advance_armor, dispatch_armor, stop_armor
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
)
from game.groundmovement.planning import movement_destination
from game.server.tgos.models import TgoJs
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_presentation import setup
from tests.test_sam_movement import make_site, selected


def moving_group(
    world: Any, category: str, destination: MovementDestination
) -> tuple[Any, Any]:
    if category == "armor":
        source = world.source
    elif category == "ewr":
        source = make_site(world, ("EWR 1L13", "Truck Ural-375"), radar=True)
    else:
        source = make_site(world)
    transit = dispatch_armor(
        world.game,
        source.id,
        world.a.captured,
        (7,) if category == "armor" else selected(world),
        destination,
        GameUpdateEvents(),
    )
    return transit, world.game.db.tgos.get(transit.detachment_id)


@pytest.mark.parametrize("category", ["armor", "aa", "ewr"])
@pytest.mark.parametrize("finish", ["stop", "arrive"])
def test_gps_destination_is_visible_only_during_active_movement(
    world: Any, category: str, finish: str
) -> None:
    w = setup(world)
    w.game.settings.coordinate_format = CoordinateFormat.MGRS
    destination = MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10))
    transit, moving = moving_group(w, category, destination)
    model = TgoJs.for_tgo(moving)
    assert model.category == category and model.in_transit
    expected = format_dd(Point(90, 10, w.game.theater.terrain).latlng())
    assert model.movement_destination_label == expected
    if finish == "stop":
        stop_armor(w.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    else:
        w.game.turn += 1
        advance_armor(w.game, GameUpdateEvents())
    assert transit.finished
    assert not TgoJs.for_tgo(moving).in_transit
    assert TgoJs.for_tgo(moving).movement_destination_label is None
    assert TgoJs.for_tgo(moving).iads_state != "relocating"


@pytest.mark.parametrize("kind", [DestinationKind.BASE, DestinationKind.FRONTLINE])
def test_named_armor_destination_and_stationary_source_are_not_confused(
    world: Any, kind: DestinationKind
) -> None:
    w = setup(world)
    destination = movement_destination(
        w.game,
        Player.BLUE,
        kind,
        base_id=w.b.id if kind is DestinationKind.BASE else w.a.id,
        opposing_base_id=w.enemy.id if kind is DestinationKind.FRONTLINE else None,
    )
    _, moving = moving_group(w, "armor", destination)
    expected = (
        w.b.name
        if kind is DestinationKind.BASE
        else f"front line {w.a.name} / {w.enemy.name}"
    )
    assert TgoJs.for_tgo(moving).movement_destination_label == expected
    assert TgoJs.for_tgo(w.source).movement_destination_label is None


@pytest.mark.parametrize("category", ["armor", "aa", "ewr"])
def test_enemy_movement_does_not_reveal_its_planned_destination(
    world: Any, category: str
) -> None:
    w = setup(world, Player.RED)
    destination = MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10))
    _, moving = moving_group(w, category, destination)
    model = TgoJs.for_tgo(moving)
    assert model.in_transit and not model.blue
    assert model.movement_destination_label is None


def test_missing_legacy_order_does_not_break_the_map(world: Any) -> None:
    w = setup(world)
    destination = MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10))
    transit, moving = moving_group(w, "armor", destination)
    del w.game.ground_movements.orders[transit.order_id]
    assert TgoJs.for_tgo(moving).movement_destination_label is None


def test_changed_base_ownership_does_not_expose_an_enemy_order(world: Any) -> None:
    w = setup(world)
    destination = MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10))
    transit, moving = moving_group(w, "armor", destination)
    order = w.game.ground_movements.orders[transit.order_id]
    w.game.ground_movements.orders[order.id] = replace(order, owner=Player.RED)
    assert TgoJs.for_tgo(moving).blue
    assert TgoJs.for_tgo(moving).movement_destination_label is None
