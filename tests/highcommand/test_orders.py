"""The objectives the High Command orders taken."""

from __future__ import annotations

import logging
import pickle
import random
from types import SimpleNamespace
from typing import Any

import pytest

from game.game import Game, TurnState
from game.highcommand import objectives as listing
from game.highcommand.objectives import Effort, Objective
from game.highcommand.orders import (
    LONGEST,
    ORDERS,
    SHORTEST,
    HighCommand,
    Order,
    Outcome,
    tiers,
)
from game.highcommand.prizes import Prize


def _objective(name: str, score: int) -> Objective:
    difficulty = min(5, score - 1)
    return Objective(
        name=name,
        kind="Factory",
        targets=(),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        difficulty=difficulty,
        importance=score - difficulty,
        justification=f"{name} earns.",
        prize=Prize("cash", score, False, f"Cash for {name}."),
    )


#: Three low, three middling and three high, by score.
BOARD = [
    _objective(name, score)
    for name, score in (
        ("L1", 2),
        ("L2", 3),
        ("L3", 3),
        ("M1", 5),
        ("M2", 6),
        ("M3", 6),
        ("H1", 8),
        ("H2", 9),
        ("H3", 10),
    )
]


def _game(turn: int, dead: tuple[str, ...] = ()) -> Any:
    return SimpleNamespace(
        turn=turn,
        theater=SimpleNamespace(
            ground_objects=[SimpleNamespace(name=name, is_dead=True) for name in dead]
        ),
    )


@pytest.fixture
def board(monkeypatch: pytest.MonkeyPatch) -> list[Objective]:
    standing = list(BOARD)
    monkeypatch.setattr(listing, "enemy_objectives", lambda game: list(standing))
    return standing


def test_the_objectives_split_into_tiers_of_score() -> None:
    split = tiers(BOARD, ORDERS)

    assert [[o.name for o in tier] for tier in split] == [
        ["L1", "L2", "L3"],
        ["M1", "M2", "M3"],
        ["H1", "H2", "H3"],
    ]
    assert [len(tier) for tier in tiers(BOARD[:8], ORDERS)] == [2, 3, 3]


def test_one_order_for_each_tier_with_its_prize_and_a_lifetime(
    board: list[Objective],
) -> None:
    command = HighCommand()

    closed = command.refresh(_game(10), random.Random(1))

    assert closed == []
    assert [order.tier for order in command.orders] == [2, 1, 0]
    for order in command.orders:
        assert order.objective[0] == "LMH"[order.tier]
        assert SHORTEST <= order.expires_on - 10 <= LONGEST
        assert order.prize == Prize(
            "cash", order.score, False, f"Cash for {order.objective}."
        )
        assert order.justification == f"{order.objective} earns."


def test_an_open_order_stays_as_it_is(board: list[Objective]) -> None:
    command = HighCommand()
    command.refresh(_game(10), random.Random(1))
    before = list(command.orders)

    command.refresh(_game(11), random.Random(2))

    assert command.orders == before


def _single(tier: int, objective: str, expires_on: int) -> HighCommand:
    order = Order(objective, tier, ordered_on=10, expires_on=expires_on, prize=None)
    return HighCommand(orders=[order])


def test_a_lapsed_order_gives_way_to_another_from_its_tier(
    board: list[Objective],
) -> None:
    command = _single(0, "L1", expires_on=12)

    closed = command.refresh(_game(12), random.Random(3))

    assert [(c.order.objective, c.outcome) for c in closed] == [("L1", Outcome.EXPIRED)]
    low = next(order for order in command.orders if order.tier == 0)
    assert low.objective in {"L2", "L3"}


def test_destroying_the_objective_closes_it_even_on_its_last_turn(
    board: list[Objective],
) -> None:
    board.remove(next(o for o in board if o.name == "H1"))
    command = _single(2, "H1", expires_on=12)

    closed = command.refresh(_game(12, dead=("H1",)), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.DESTROYED]


def test_an_objective_that_is_no_longer_there_closes_its_order(
    board: list[Objective],
) -> None:
    board.remove(next(o for o in board if o.name == "M1"))
    command = _single(1, "M1", expires_on=14)

    closed = command.refresh(_game(12), random.Random(3))

    assert [c.outcome for c in closed] == [Outcome.GONE]


def test_orders_come_back_from_a_save_written_before_a_field_was() -> None:
    order = Order("L1", 0, ordered_on=10, expires_on=12, prize=None)
    state = dict(order.__dict__)
    del state["justification"]
    prize = Prize("cash", 5, False, "Cash.")
    prize_state = dict(prize.__dict__)
    del prize_state["terms"]

    restored: Any = Order.__new__(Order)
    restored.__setstate__(state)
    restored_prize: Any = Prize.__new__(Prize)
    restored_prize.__setstate__(prize_state)

    assert restored.justification == ""
    assert restored_prize.terms == ()
    assert pickle.loads(pickle.dumps(HighCommand([order]))) == HighCommand([order])


def test_a_fault_in_the_orders_does_not_stop_the_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail(game: Any) -> None:
        raise RuntimeError("broken")

    game: Any = SimpleNamespace(
        check_win_loss=lambda: TurnState.CONTINUE,
        high_command=SimpleNamespace(refresh=fail),
    )

    with caplog.at_level(logging.ERROR):
        Game.refresh_high_command(game)

    assert "High Command" in caplog.text
