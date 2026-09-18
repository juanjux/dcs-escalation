"""The OPFOR agent can buy red ground units without the player's cheat being on.

Upstream #959 gave GroundUnitPurchaseAdapter a guard so the PLAYER cannot buy for red
unless the enemy buy/sell cheat is on. That is right for the base menu and wrong for
the API, which is red's own commander -- and it was asymmetric as well, because
aircraft purchases never had the guard: the agent could buy red a squadron but not a
rifle company. Reported from a live campaign by the agent itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.purchaseadapter import GroundUnitPurchaseAdapter, TransactionError
from game.theater.player import Player


class _Orders:
    def __init__(self) -> None:
        self.ordered: dict[Any, int] = {}

    def order(self, units: dict[Any, int]) -> None:
        for unit, count in units.items():
            self.ordered[unit] = self.ordered.get(unit, 0) + count

    def pending_orders(self, unit: Any) -> int:
        return self.ordered.get(unit, 0)


class _Unit:
    """Hashable: the order book keys on the unit type."""

    price = 12
    display_name = "Type 04A (ZBD-04A)"


def _adapter(commands_the_coalition: bool) -> tuple[Any, Any]:
    unit = _Unit()
    cp: Any = SimpleNamespace(
        captured=Player.RED,
        ground_unit_orders=_Orders(),
        base=SimpleNamespace(total_units_of_type=lambda _u: 0),
        has_ground_unit_source=lambda _game: True,
    )
    coalition: Any = SimpleNamespace(budget=92)
    coalition.adjust_budget = lambda amount: setattr(
        coalition, "budget", coalition.budget + amount
    )
    game: Any = SimpleNamespace(
        settings=SimpleNamespace(enable_enemy_buy_sell=False)  # the cheat is OFF
    )
    return unit, GroundUnitPurchaseAdapter(
        cast(Any, cp),
        cast(Any, coalition),
        cast(Any, game),
        commands_the_coalition=commands_the_coalition,
    )


def test_the_player_still_cannot_buy_for_red_without_the_cheat() -> None:
    unit, adapter = _adapter(commands_the_coalition=False)
    with pytest.raises(TransactionError, match="not authorized"):
        adapter.buy(unit, 2)


def test_reds_own_commander_can() -> None:
    unit, adapter = _adapter(commands_the_coalition=True)
    adapter.buy(unit, 2)
    assert adapter.pending_delivery_quantity(unit) == 2
