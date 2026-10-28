"""Evacuated and disbanded objectives must not award destruction prizes."""

from typing import Any

import pytest

from game.groundmovement.dispatch import advance_armor, dispatch_armor
from game.highcommand import objectives
from game.highcommand.orders import HighCommand, Order, Outcome
from game.highcommand.prizes import Prize
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from tests.highcommand.stubs import Base, armour, sam, unit
from tests.highcommand.test_orders import _game
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401


def command_for(name: str, side: Player = Player.BLUE) -> HighCommand:
    return HighCommand(
        side=side,
        orders=[
            Order(
                name,
                0,
                ordered_on=0,
                expires_on=10,
                prize=Prize("squadron", 5, True, "Squadron ticket.", side=side),
            )
        ],
    )


@pytest.fixture
def no_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(objectives, "enemy_objectives", lambda *args: [])


@pytest.mark.parametrize("moving_owner", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("arrived", [False, True])
def test_evacuating_an_armor_group_never_earns_the_opponent_a_ticket(
    world: Any, no_targets: None, moving_owner: Player, arrived: bool
) -> None:
    w = prepare(world)
    w.a._coalition.player = moving_owner
    w.b._coalition.player = moving_owner
    w.source.groups[0].units[:] = [u for u in w.source.units if u.id == 7]
    transit = dispatch_armor(
        w.game, w.source.id, moving_owner, [7], w.destination, GameUpdateEvents()
    )
    moving = w.game.db.tgos.get(transit.detachment_id)
    if arrived:
        w.game.turn += 1
        advance_armor(w.game, GameUpdateEvents())
        assert transit.finished and not list(moving.units)
    else:
        assert not moving.is_dead
    game = _game(w.game.turn, ground_objects=(w.source, moving))
    command = command_for(w.source.name, moving_owner.opponent)
    closed = command.refresh(game)
    assert [entry.outcome for entry in closed] == [Outcome.GONE]
    assert command.pay(game, closed) == []
    assert not command.tickets and not command.loans
    assert [entry.outcome for entry in command.history] == ["gone"]


@pytest.mark.parametrize("kind", [armour, sam])
def test_disbanding_a_site_does_not_count_as_destroying_it(
    kind: Any, no_targets: None
) -> None:
    site = kind("TARGET", 0, [unit("Tank")])
    site.groups[0].units.clear()
    assert site.is_dead
    command = command_for(site.name)
    game = _game(1, ground_objects=(site,))
    closed = command.refresh(game)
    assert [entry.outcome for entry in closed] == [Outcome.GONE]
    assert not command.pay(game, closed) and not command.tickets


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_actual_destroyed_units_still_earn_a_ticket(
    owner: Player, no_targets: None
) -> None:
    casualty = unit("Tank")
    casualty.alive = False
    site = armour("TARGET", 0, [casualty], base=Base("Base", side=owner))
    command = command_for(site.name, owner.opponent)
    game = _game(1, ground_objects=(site,))
    closed = command.refresh(game)
    assert [entry.outcome for entry in closed] == [Outcome.ACHIEVED]
    assert command.pay(game, closed)
    assert len(command.tickets) == 1


def test_empty_sibling_does_not_turn_casualties_elsewhere_into_a_full_victory(
    no_targets: None,
) -> None:
    casualty = unit("Tank")
    casualty.alive = False
    destroyed = armour("TARGET", 0, [casualty])
    empty = armour("TARGET", 1, [])
    game = _game(1, ground_objects=(destroyed, empty))
    command = command_for("TARGET")
    closed = command.refresh(game)
    assert [entry.outcome for entry in closed] == [Outcome.GONE]
    assert not command.pay(game, closed) and not command.tickets
