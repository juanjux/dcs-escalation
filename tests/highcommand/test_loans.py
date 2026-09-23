"""Squadrons lent to the player for a few turns."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Any

import pytest

from game.highcommand.loans import Loan, loan_base, return_loans
from game.highcommand.orders import HighCommand, Ticket
from game.highcommand.prizes import CannotGive, Prize
from game.theater import Player
from tests.highcommand.stubs import at

AIRCRAFT: Any = SimpleNamespace(helicopter=False, lha_capable=False, flyable=True)


def _base(name: str, x_nm: float, room: int, operates: bool = True) -> Any:
    return SimpleNamespace(
        name=name,
        position=at(x_nm),
        can_operate=lambda aircraft: operates,
        unclaimed_parking=lambda parking: room,
    )


def _game(ours: list[Any], theirs: list[Any], turn: int = 10) -> Any:
    return SimpleNamespace(
        turn=turn,
        settings=SimpleNamespace(ground_start_ai_planes=False),
        theater=SimpleNamespace(
            control_points_for=lambda player: (
                ours if player is Player.BLUE else theirs
            )
        ),
    )


def test_support_goes_to_the_rearmost_base_and_combat_to_the_nearest() -> None:
    rear, middle, forward = (
        _base("Rear", 0, 4),
        _base("Middle", 50, 4),
        _base("Forward", 90, 4),
    )
    full, grounded = _base("Full", 95, 0), _base("Grounded", 99, 4, operates=False)
    game = _game([rear, middle, forward, full, grounded], [_base("Enemy", 100, 4)])

    assert loan_base(game, Player.BLUE, AIRCRAFT, 2, front=False) is rear
    assert loan_base(game, Player.BLUE, AIRCRAFT, 2, front=True) is forward
    assert loan_base(game, Player.BLUE, AIRCRAFT, 5, front=True) is None


def _squadron(name: str, aircraft: str, wing: Any) -> Any:
    refunds: list[str] = []
    squadron = SimpleNamespace(
        name=name,
        aircraft=aircraft,
        refund_orders=lambda: refunds.append(name),
        coalition=SimpleNamespace(air_wing=wing),
        refunds=refunds,
    )
    wing.squadrons[aircraft].append(squadron)
    return squadron


def test_a_loan_that_has_run_out_is_taken_back() -> None:
    unclaimed: list[str] = []
    wing = SimpleNamespace(
        squadrons=defaultdict(list),
        unclaim_squadron_def=lambda squadron: unclaimed.append(squadron.name),
    )
    over = _squadron("VAW-113", "E-2C", wing)
    running = _squadron("VF-11", "F-14B", wing)
    loans = [Loan(over, until=12), Loan(running, until=14)]

    lines = list(return_loans(_game([], [], turn=12), loans))

    assert [loan.squadron for loan in loans] == [running]
    assert "E-2C" not in wing.squadrons and wing.squadrons["F-14B"] == [running]
    assert over.refunds == ["VAW-113"] and unclaimed == ["VAW-113"]
    assert lines == ["VAW-113 (E-2C) goes back: its loan is over."]


def test_a_ticket_that_cannot_be_given_now_stays() -> None:
    faction = SimpleNamespace(awacs=set(), tankers=set(), aircraft=set())
    game: Any = SimpleNamespace(
        turn=10, coalition_for=lambda player: SimpleNamespace(faction=faction)
    )
    prize = Prize("awacs", 5, True, "A ticket for an extra AWACS.", (("turns", 3),))
    command = HighCommand(tickets=[Ticket(prize, "DEPOT", 9)])

    with pytest.raises(CannotGive):
        command.spend(game, command.tickets[0], ())

    assert len(command.tickets) == 1
