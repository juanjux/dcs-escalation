"""Borrowed aircraft cannot generate sales or be reinforced with purchases."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from game.highcommand.loans import Loan, loan_for
from game.procurement import ProcurementAi
from game.purchaseadapter import AircraftPurchaseAdapter, TransactionError
from game.settings import Settings
from game.theater import Player


class Squadron(SimpleNamespace):
    def __str__(self) -> str:
        return str(self.name)


@pytest.fixture
def world() -> Any:
    commands = {side: SimpleNamespace(loans=[]) for side in (Player.BLUE, Player.RED)}
    coalition = SimpleNamespace(budget=1000.0)
    coalition.adjust_budget = lambda change: setattr(
        coalition, "budget", coalition.budget + change
    )
    coalition.game = SimpleNamespace(
        settings=Settings(), turn=10, high_command_for=commands.__getitem__
    )
    base: Any = SimpleNamespace(
        coalition=coalition,
        captured=Player.BLUE,
        name="Base",
        sunk=False,
        unclaimed_parking=lambda _: 30,
    )
    squadron: Any = Squadron(
        id=uuid4(),
        name="Loan squadron",
        player=Player.BLUE,
        coalition=coalition,
        location=base,
        aircraft=SimpleNamespace(
            price=20,
            display_name="Test aircraft",
            helicopter=False,
            lha_capable=False,
            flyable=True,
        ),
        owned_aircraft=6,
        untasked_aircraft=6,
        pending_deliveries=0,
        max_size=10,
        has_aircraft_capacity_for=lambda _: True,
        pilot_limits_enabled=False,
    )
    loan = Loan(squadron, 13)
    commands[Player.BLUE].loans.append(loan)
    return SimpleNamespace(
        game=coalition.game,
        squadron=squadron,
        coalition=coalition,
        commands=commands,
        loan=loan,
        adapter=AircraftPurchaseAdapter(base),
    )


@pytest.mark.parametrize("action", ["buy", "sell"])
@pytest.mark.parametrize("pending", [-2, 0, 2])
@pytest.mark.parametrize("quantity", [1, 5, 10])
def test_loans_reject_bulk_trades_and_pending_order_bypasses(
    world: Any, action: str, pending: int, quantity: int
) -> None:
    sq = world.squadron
    sq.pending_deliveries = pending
    with pytest.raises(TransactionError, match="on-loan"):
        getattr(world.adapter, action)(sq, quantity)
    assert (sq.owned_aircraft, sq.untasked_aircraft, sq.pending_deliveries) == (
        6,
        6,
        pending,
    )
    assert world.coalition.budget == 1000
    assert not world.adapter.can_buy(sq)
    assert not world.adapter.can_sell(sq)
    assert not world.adapter.can_sell_or_cancel(sq)
    assert "on-loan" in world.adapter.why_cannot_buy(sq)


@pytest.mark.parametrize(
    "action", ["do_purchase", "do_sale", "do_cancel_purchase", "do_cancel_sale"]
)
def test_direct_mutators_also_reject_a_loan(world: Any, action: str) -> None:
    with pytest.raises(TransactionError, match="on-loan"):
        getattr(world.adapter, action)(world.squadron)
    assert world.squadron.pending_deliveries == 0
    assert world.squadron.untasked_aircraft == 6


def test_same_name_permanent_squadron_is_still_tradeable(world: Any) -> None:
    permanent: Any = Squadron(**vars(world.squadron))
    permanent.id = uuid4()
    assert loan_for(permanent) is None
    world.adapter.sell(permanent, 1)
    assert permanent.pending_deliveries == -1
    assert world.coalition.budget == 1020
    world.adapter.buy(permanent, 1)
    world.adapter.buy(permanent, 1)
    assert permanent.pending_deliveries == 1
    assert world.coalition.budget == 980


def test_expired_loan_is_blocked_until_it_is_actually_returned(world: Any) -> None:
    world.game.turn = world.loan.until
    assert loan_for(world.squadron) is world.loan
    assert not world.adapter.can_sell(world.squadron)


def test_red_loans_use_the_red_register(world: Any) -> None:
    world.squadron.player = Player.RED
    world.commands[Player.BLUE].loans.clear()
    world.commands[Player.RED].loans.append(world.loan)
    assert not world.adapter.can_buy(world.squadron)
    with pytest.raises(TransactionError, match="on-loan"):
        world.adapter.sell(world.squadron, 1)


def test_automatic_reinforcement_skips_the_loan(world: Any) -> None:
    budget, success = ProcurementAi.fulfill_aircraft_request([world.squadron], 1, 100)
    assert (budget, success) == (100, False)
    assert world.squadron.pending_deliveries == 0


def test_automatic_reinforcement_can_still_buy_for_a_permanent_squadron(
    world: Any,
) -> None:
    permanent: Any = Squadron(**vars(world.squadron))
    permanent.id = uuid4()
    budget, success = ProcurementAi.fulfill_aircraft_request(
        [world.squadron, permanent], 1, 100
    )
    assert (budget, success) == (80, True)
    assert permanent.pending_deliveries == 1
    assert world.squadron.pending_deliveries == 0


def test_a_healthy_loan_can_still_relocate(world: Any) -> None:
    from datetime import datetime
    from game.squadrons.squadron import Squadron as CampaignSquadron

    sq = world.squadron
    sq.destination = None
    sq.aircraft_repairs = []
    sq.expected_size_next_turn = 6
    sq.location.runway_is_operational = lambda: True
    planned: list[object] = []
    sq.replan_ferry_flights = planned.append
    destination: Any = SimpleNamespace(
        can_operate=lambda aircraft: True, unclaimed_parking=lambda parking: 20
    )
    CampaignSquadron.plan_relocation(sq, destination, datetime(2026, 1, 1))
    assert sq.destination is destination
    assert len(planned) == 1
    assert world.coalition.budget == 1000


@pytest.mark.parametrize("action", ["buy_aircraft", "sell_aircraft"])
def test_planner_api_returns_an_error_without_mutating_inventory(
    world: Any, action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game.agent import planner

    monkeypatch.setattr(planner, "_resolve_squadron", lambda *args: world.squadron)
    result = getattr(planner, action)(world.game, "blue", str(world.squadron.id), 1)
    assert not result.ok and "on-loan" in result.error
    assert world.squadron.pending_deliveries == 0
    assert world.coalition.budget == 1000
