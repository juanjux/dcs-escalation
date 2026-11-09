"""Reward bands respect value and the recipient coalition's existing support."""

from dataclasses import replace
import pickle
import random
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from game.ato.flighttype import FlightType
from game.data.groups import GroupTask
from game.highcommand import prizes as rewards
from game.highcommand.orders import HighCommand, HistoryEntry, Order, Ticket
from game.highcommand.prizes import Context, Prize, Prizes
from game.squadrons.pilot import Pilot
from game.theater import Player
from tests.highcommand.test_prizes import _Aircraft, _kind, _settings, _side


def required(prize: Prize | None) -> Prize:
    assert prize is not None
    return prize


@pytest.fixture
def campaign() -> Any:
    settings = _settings()
    faction, income, forces = _side(GroupTask.SHORAD, GroupTask.MERAD, GroupTask.LORAD)
    wings: dict[Player, list[Any]] = {Player.BLUE: [], Player.RED: []}
    game: Any = SimpleNamespace(
        coalition_for=lambda side: SimpleNamespace(
            air_wing=SimpleNamespace(iter_squadrons=lambda: wings[side])
        ),
        theater=SimpleNamespace(controlpoints=[]),
    )
    context = Context(settings, faction, income, random.Random(1), forces, game=game)
    return SimpleNamespace(
        settings=settings,
        faction=faction,
        income=income,
        forces=forces,
        wings=wings,
        game=game,
        context=context,
    )


def support(
    task: FlightType, count: int = 1, damaged: int = 0, selling: int = 0
) -> Any:
    return SimpleNamespace(
        capable_of=lambda other: other is task,
        owned_aircraft=count,
        pending_deliveries=-selling,
        aircraft_repairs=[object()] * damaged,
        current_roster=[],
    )


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize(
    "kind,task", [("awacs", FlightType.AEWC), ("tanker", FlightType.REFUELING)]
)
def test_existing_support_suppresses_only_its_own_role_and_coalition(
    campaign: Any, side: Player, kind: str, task: FlightType
) -> None:
    c = campaign
    context = replace(c.context, side=side)
    c.wings[side.opponent].append(support(task))
    assert _kind(kind).prize(5, context) is not None
    c.wings[side].append(support(task))
    assert _kind(kind).prize(5, context) is None
    other = "tanker" if kind == "awacs" else "awacs"
    assert _kind(other).prize(5, context) is not None


@pytest.mark.parametrize(
    "count,damaged,selling,needed",
    [
        (0, 0, 0, True),
        (1, 0, 0, False),
        (1, 1, 0, True),
        (2, 1, 0, False),
        (1, 0, 1, True),
    ],
)
def test_support_needs_use_airframes_not_spare_ato_capacity(
    campaign: Any, count: int, damaged: int, selling: int, needed: bool
) -> None:
    c = campaign
    squadron = support(FlightType.AEWC, count, damaged, selling)
    squadron.untasked_aircraft = (
        0  # An aircraft already assigned is still useful support.
    )
    c.wings[Player.BLUE].append(squadron)
    assert (_kind("awacs").prize(5, c.context) is not None) is needed


def test_actual_draw_uses_campaign_needs(
    campaign: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = campaign
    c.wings[Player.BLUE].extend(
        [support(FlightType.AEWC), support(FlightType.REFUELING)]
    )
    monkeypatch.setattr(
        rewards, "KINDS", [_kind("awacs"), _kind("tanker"), _kind("cash")]
    )
    drawer = Prizes(c.settings, c.faction, c.income, c.forces, game=c.game)
    assert {required(drawer.draw(5, seed)).kind for seed in range(100)} == {"cash"}


@pytest.mark.parametrize("kind", ["heal", "hospital"])
def test_medical_rewards_require_a_wounded_pilot(campaign: Any, kind: str) -> None:
    c = campaign
    assert _kind(kind).prize(5, c.context) is None
    wounded = Pilot("Recovering pilot")
    wounded.wound(3, turn=1)
    c.wings[Player.RED].append(SimpleNamespace(current_roster=[wounded]))
    assert _kind(kind).prize(5, c.context) is None
    c.wings[Player.BLUE].append(SimpleNamespace(current_roster=[wounded]))
    assert _kind(kind).prize(5, c.context) is not None


@pytest.mark.parametrize("score", [7, 8, 9, 10])
def test_high_scores_cannot_draw_modest_utility_rewards(
    campaign: Any, score: int
) -> None:
    c = campaign
    drawer = Prizes(c.settings, c.faction, c.income, c.forces)
    drawn = {required(drawer.draw(score, seed)).kind for seed in range(200)}
    assert drawn == {"cash", "morale", "sam", "squadron"}


def test_squadron_loans_cannot_be_low_score_rewards_and_scale_up(campaign: Any) -> None:
    c = campaign
    kind = _kind("squadron")
    assert all(kind.prize(score, c.context) is None for score in range(2, 7))
    prizes = [required(kind.prize(score, c.context)) for score in range(7, 11)]
    assert [prize.term("aircraft") for prize in prizes] == [6, 8, 10, 12]
    assert [prize.term("turns") for prize in prizes] == [4, 4, 5, 5]


@pytest.mark.parametrize("score", [7, 8, 9, 10])
def test_b21_squadron_rewards_are_limited_to_two_aircraft(
    campaign: Any, score: int
) -> None:
    c = campaign
    c.faction.aircraft = {_Aircraft("[CH] B-21", 45, FlightType.STRIKE)}
    prize = required(_kind("squadron").prize(score, c.context))

    assert prize.term("aircraft") == 2
    assert prize.term("turns") == rewards.half_up(score)
    assert prize.line == (
        f"A ticket for a squadron of 2 [CH] B-21 on loan for "
        f"{prize.term('turns')} turns."
    )


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("count", [6, 8, 10, 12])
def test_saved_b21_requests_and_unspent_tickets_are_reduced_to_two(
    side: Player, count: int
) -> None:
    prize = Prize(
        "squadron",
        10,
        True,
        f"A ticket for a squadron of {count} [CH] B-21 on loan for 5 turns.",
        (("aircraft", count), ("turns", 5), ("type", "[CH] B-21")),
        side,
    )
    history = HistoryEntry(1, "spent", "Ticket spent", prize.line)
    command = HighCommand(
        orders=[Order("Target", 2, 1, 4, prize)],
        tickets=[Ticket(prize, "Previous target", 1)],
        history=[history],
        side=side,
    )

    restored = pickle.loads(pickle.dumps(command))

    assert restored.orders[0].prize == restored.tickets[0].prize
    for reduced in (restored.orders[0].prize, restored.tickets[0].prize):
        assert reduced.term("aircraft") == 2
        assert reduced.term("turns") == 5
        assert reduced.score == 10 and reduced.side is side and reduced.ticket
        assert reduced.line == (
            "A ticket for a squadron of 2 [CH] B-21 on loan for 5 turns."
        )
        assert pickle.loads(pickle.dumps(reduced)) == reduced
    assert restored.history == [history]


@pytest.mark.parametrize(
    "kind,aircraft,count",
    [
        ("squadron", "F-16C", 12),
        ("squadron", "[CH] B-21", 1),
        ("squadron", "[CH] B-21", 2),
        ("loaned-aircraft", "[CH] B-21", 12),
    ],
)
def test_b21_save_migration_leaves_other_rewards_unchanged(
    kind: str, aircraft: str, count: int
) -> None:
    prize = Prize(
        kind,
        10,
        True,
        "Previously promised reward.",
        (("aircraft", count), ("turns", 5), ("type", aircraft)),
    )
    assert pickle.loads(pickle.dumps(prize)) == prize


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("legacy", [False, True])
def test_b21_ticket_redeems_two_aircraft_at_a_base_with_two_free_slots(
    monkeypatch: pytest.MonkeyPatch, side: Player, legacy: bool
) -> None:
    from game.squadrons.squadron import Squadron
    from tests.highcommand.test_loan_basing import _game

    game = _game(side)
    game.aircraft.display_name = "[CH] B-21"
    game.aircraft.price = 45
    game.aircraft.helicopter = False
    game.aircraft.task_priorities = {FlightType.STRIKE: 1}
    context = Context(
        _settings(), game.coalition_for(side).faction, 100, random.Random(1), side=side
    )
    kind = _kind("squadron")
    prize = required(kind.prize(10, context))
    if legacy:
        prize = replace(
            prize,
            line="A ticket for a squadron of 12 [CH] B-21 on loan for 5 turns.",
            terms=(("aircraft", 12), ("turns", 5), ("type", "[CH] B-21")),
        )
    prize = pickle.loads(pickle.dumps(prize))
    ticket = Ticket(prize, "Objective", 9)
    command = game.high_command
    command.tickets = [ticket]
    base = game.bases[0]
    base.unclaimed_parking = lambda parking: 2
    squadron = MagicMock(name="B-21 loan")
    squadron.name = "Loan squadron"
    squadron.owned_aircraft = 2
    squadron.location = base
    create = MagicMock(return_value=squadron)
    monkeypatch.setattr(Squadron, "create_from", create)

    assert str(base.id) in {c.key for c in kind.steps[0].options(game, prize, ())}
    command.spend(game, ticket, (str(base.id),))

    assert create.call_args.args[2] == 2
    assert create.call_args.args[3] is base
    assert command.tickets == []
    assert command.loans[0].squadron is squadron
    assert command.loans[0].until == game.turn + 5


def test_existing_high_score_healing_tickets_remain_redeemable(campaign: Any) -> None:
    c = campaign
    from game.highcommand.prizes import Prize, kind_of

    ticket = Prize("heal", 9, True, "Previously promised healing.")
    wounded = Pilot("Recovering pilot")
    wounded.wound(3, turn=1)
    c.wings[Player.BLUE].append(
        SimpleNamespace(name="Squadron", aircraft="F-16C", current_roster=[wounded])
    )
    kind = kind_of(ticket)
    assert kind is not None and kind.give is not None
    choices = kind.steps[0].options(c.game, ticket, ())
    assert len(choices) == 1 and choices[0].key == str(wounded.id)
    kind.give(c.game, ticket, (str(wounded.id),))
    assert not wounded.wounded
