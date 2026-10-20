"""Open requests promise distinct reward kinds, except different typed loans."""

from dataclasses import replace
import random
from types import SimpleNamespace
from typing import Any

import pytest

from game.highcommand import objectives, prizes as rewards
from game.highcommand.orders import HighCommand, Order
from game.highcommand.prizes import Prize, Prizes, repeats_offer
from game.theater import Player
from tests.highcommand.test_orders import BOARD, _game
from tests.highcommand.test_prizes import _side, _settings


def _loan(aircraft: str, score: int = 4) -> Prize:
    return Prize("squadron", score, True, "Loan.", (("type", aircraft),))


def test_different_amounts_and_durations_are_still_the_same_reward() -> None:
    first = Prize("discount", 3, False, "Discount.", (("on", "aircraft"),))
    second = Prize("discount", 8, False, "Another discount.", (("on", "ground units"),))
    assert repeats_offer(second, [first])
    assert not repeats_offer(Prize("cash", 5, False, "Cash."), [first])


def test_only_different_known_aircraft_types_allow_repeated_loan_rewards() -> None:
    assert repeats_offer(_loan("AH-1W", 8), [_loan("AH-1W")])
    assert not repeats_offer(_loan("A-10C II"), [_loan("AH-1W")])
    assert repeats_offer(_loan("AH-1W"), [Prize("squadron", 4, True, "Legacy loan.")])
    assert repeats_offer(
        Prize("awacs", 6, True, "AWACS."), [Prize("awacs", 2, True, "AWACS.")]
    )


def test_draw_skips_all_currently_offered_non_loan_kinds_deterministically() -> None:
    drawer = Prizes(_settings(), *_side())
    offered = [
        Prize(key, 2, False, "Offered.") for key in ("cash", "discount", "aircraft")
    ]
    for seed in range(100):
        prize = drawer.draw(8, seed, offered)
        assert prize is not None and not repeats_offer(prize, offered)
        assert drawer.draw(8, seed, offered) == prize


def test_squadron_loan_uses_a_different_type_even_at_the_same_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    squadron_kind = next(kind for kind in rewards.KINDS if kind.key == "squadron")
    monkeypatch.setattr(rewards, "KINDS", [squadron_kind])
    drawer = Prizes(_settings(), *_side())
    offered: list[Prize] = []
    for _ in range(3):
        prize = drawer.draw(5, "same", offered)
        assert prize is not None and not repeats_offer(prize, offered)
        offered.append(prize)
    assert len({prize.term("type") for prize in offered}) == 3
    assert drawer.draw(5, "same", offered) is None


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_refresh_replaces_duplicate_previews_but_keeps_existing_promises(
    side: Player, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings()
    drawer = Prizes(settings, *_side(), side=side)
    monkeypatch.setattr(Prizes, "of", lambda *args: drawer)
    board = [replace(o, prize=Prize("cash", o.score, False, "Cash.")) for o in BOARD]
    monkeypatch.setattr(objectives, "enemy_objectives", lambda *args: list(board))
    existing = Order("L1", 0, 9, 20, board[0].prize)
    command = HighCommand(orders=[existing], side=side)
    command.refresh(_game(10), random.Random(1))
    assert len(command.orders) == 3
    assert existing.prize == board[0].prize
    promised: list[Prize] = []
    for order in command.orders:
        assert order.prize is not None and not repeats_offer(order.prize, promised)
        promised.append(order.prize)
    before = list(command.orders)
    command.refresh(_game(11), random.Random(3))
    assert command.orders == before


def test_exhausted_reward_pool_leaves_slot_open_until_a_reward_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cash = next(kind for kind in rewards.KINDS if kind.key == "cash")
    monkeypatch.setattr(rewards, "KINDS", [cash])
    drawer = Prizes(_settings(), *_side())
    monkeypatch.setattr(Prizes, "of", lambda *args: drawer)
    board = [replace(o, prize=Prize("cash", o.score, False, "Cash.")) for o in BOARD]
    monkeypatch.setattr(objectives, "enemy_objectives", lambda *args: list(board))
    command = HighCommand()
    command.refresh(_game(10), random.Random(1))
    assert len(command.orders) == 1
    old = command.orders[0]
    old.expires_on = 11
    command.refresh(_game(11), random.Random(3))
    assert len(command.orders) == 1 and command.orders[0] is not old
