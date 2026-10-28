"""Movement placeholders are hidden, without hiding real survivors or casualties."""

from copy import deepcopy
from typing import Any

import pytest

from game.groundmovement.dispatch import advance_armor, dispatch_armor, stop_armor
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
)
from game.groundmovement.presentation import departed_detachments, empty_movement_group
from game.groundmovement.settings import set_enabled
from game.server.tgos.models import TgoJs
from game.sidc import Status
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401


def setup(world: Any, owner: Player = Player.BLUE) -> Any:
    prepare(world)
    world.game.settings.set_plugin_option("gpsjamming", False)
    for cp in world.game.theater.controlpoints:
        cp._coalition.game = world.game
    world.a._coalition.player = owner
    world.b._coalition.player = owner
    # One tank and two trucks, all self-propelled and alive.
    world.source.groups[0].units[:] = [
        unit for unit in world.source.units if unit.id in (5, 6, 7)
    ]
    return world


def move(world: Any, selected: tuple[int, ...] = (5, 6, 7)) -> tuple[Any, Any, Any]:
    events = GameUpdateEvents()
    transit = dispatch_armor(
        world.game,
        world.source.id,
        world.a.captured,
        selected,
        world.destination,
        events,
    )
    return transit, world.game.db.tgos.get(transit.detachment_id), events


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_full_move_hides_empty_source_live_and_after_reload(
    world: Any, owner: Player
) -> None:
    w = setup(world, owner)
    original = tuple(w.source.units)
    transit, moving, events = move(w)
    assert empty_movement_group(w.source)
    assert w.source.id in events.deleted_tgos and w.source not in events.updated_tgos
    assert moving in events.updated_tgos and not moving.is_dead
    assert tuple(moving.units) == original
    assert departed_detachments(w.game, w.source) == [moving]
    # The map applies the same rule to campaigns saved before this fix.
    restored = deepcopy(w.game)
    visible = {tgo.id: tgo for tgo in TgoJs.all_in_game(restored)}
    assert w.source.id not in visible
    assert not visible[moving.id].dead
    assert len(visible[moving.id].units) == 3
    assert restored.db.tgos.get(w.source.id).is_dead
    assert transit.detachment_id == moving.id


def test_partial_move_keeps_remaining_source_and_real_losses_visible(
    world: Any,
) -> None:
    w = setup(world)
    transit, moving, events = move(w, (7,))
    assert not empty_movement_group(w.source)
    assert w.source in events.updated_tgos and w.source.id not in events.deleted_tgos
    assert not departed_detachments(w.game, w.source)
    for unit in moving.units:
        unit.kill(events)
    advance_armor(w.game, events)
    assert transit.finished and moving.is_dead
    assert not empty_movement_group(moving)
    assert moving.sidc_status == Status.PRESENT_DESTROYED
    assert moving.id not in events.deleted_tgos
    assert {tgo.id: tgo for tgo in TgoJs.all_in_game(w.game)}[moving.id].dead


def test_no_movement_or_refilled_source_is_not_hidden(world: Any) -> None:
    w = setup(world)
    units = tuple(w.source.units)
    w.source.groups[0].units.clear()
    assert not empty_movement_group(w.source)
    assert w.source.id in {tgo.id for tgo in TgoJs.all_in_game(w.game)}
    w.source.groups[0].units[:] = units
    move(w)
    replacement = deepcopy(units[0])
    replacement.ground_object = w.source
    w.source.groups[0].units.append(replacement)
    assert not empty_movement_group(w.source)
    events = GameUpdateEvents().update_tgo(w.source)
    assert w.source in events.updated_tgos and not events.deleted_tgos
    assert not departed_detachments(w.game, w.source)


@pytest.mark.parametrize("paused", [False, True])
def test_paused_and_stopped_formations_stay_visible(world: Any, paused: bool) -> None:
    w = setup(world)
    transit, moving, _ = move(w)
    if paused:
        set_enabled(w.game.settings, False)
        advance_armor(w.game, GameUpdateEvents())
        assert transit.pause_reason
    else:
        stop_armor(w.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    assert empty_movement_group(w.source)
    assert not empty_movement_group(moving)
    assert departed_detachments(w.game, w.source) == [moving]


def test_base_arrival_removes_delivered_placeholder_from_live_map(world: Any) -> None:
    w = setup(world)
    transit, moving, _ = move(w)
    w.game.turn += 1
    events = GameUpdateEvents()
    advance_armor(w.game, events)
    assert transit.finished
    assert empty_movement_group(moving)
    assert moving.id in events.deleted_tgos and moving not in events.updated_tgos
    assert not TgoJs.all_in_game(w.game)
    assert not departed_detachments(w.game, w.source)


def test_multiple_departures_are_not_misrepresented_as_one_group(world: Any) -> None:
    w = setup(world)
    _, first, _ = move(w, (7,))
    _, second, _ = move(w, (5, 6))
    assert set(departed_detachments(w.game, w.source)) == {first, second}
    assert {tgo.id for tgo in TgoJs.all_in_game(w.game)} == {first.id, second.id}


def test_follow_repeated_moves_to_the_current_detachment(world: Any) -> None:
    w = setup(world)
    transit, first, _ = move(w)
    stop_armor(w.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    next_transit = dispatch_armor(
        w.game,
        first.id,
        Player.BLUE,
        (5, 6, 7),
        MovementDestination(DestinationKind.POSITION, GroundPosition(90, 10)),
        GameUpdateEvents(),
    )
    current = w.game.db.tgos.get(next_transit.detachment_id)
    assert empty_movement_group(first)
    assert departed_detachments(w.game, w.source) == [current]
    assert departed_detachments(w.game, first) == [current]
