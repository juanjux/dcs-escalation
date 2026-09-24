"""GeneraLLM reads its own High Command and spends its tickets."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.agent import highcommand as api
from game.agent import service
from game.highcommand import describe, orders
from game.highcommand.campaign import Task
from game.highcommand.orders import Effect, HighCommand, Order, Ticket
from game.highcommand.prizes import Choice, Prize, PrizeKind, Step
from game.theater.player import Player

TURN = 14
SITES = [Choice("7", "BEETLE", "Destroyed"), Choice("8", "WOLF", "Empty")]
SYSTEMS = {"7": [Choice("SA-10", "SA-10", "")], "8": []}
GIVEN: list[tuple[str, ...]] = []


def _give(game: Any, prize: Prize, picked: tuple[str, ...]) -> str:
    GIVEN.append(picked)
    return f"SA-10 set up at {picked[0]}."


KINDS = {
    "sam": PrizeKind(
        "sam",
        lambda score, context: None,
        ticket=True,
        give=_give,
        steps=(
            Step("Where?", lambda game, prize, picked: SITES),
            Step(
                "Which system?",
                lambda game, prize, picked: SYSTEMS[picked[0]],
                auto=True,
            ),
        ),
    ),
}


@pytest.fixture(autouse=True)
def kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    GIVEN.clear()
    for module in (api, describe, orders):
        monkeypatch.setattr(module, "kind_of", lambda prize: KINDS.get(prize.kind))


class _At:
    def __init__(self, lat: float) -> None:
        self.lat, self.lng = lat, -60.0

    def latlng(self) -> Any:
        return self


def _game() -> Any:
    command = HighCommand(side=Player.RED)
    command.orders = [
        Order(
            "MUSK",
            2,
            ordered_on=TURN - 1,
            expires_on=TURN + 2,
            prize=Prize("sam", 6, True, "A ticket for a SAM battery.", (), Player.RED),
            kind="AA Defense Site",
            difficulty=3,
            importance=4,
            justification="Its Hawk covers Mount Pleasant.",
        ),
        Order(
            "Mount Pleasant (OCA/Runway)",
            1,
            ordered_on=TURN - 1,
            expires_on=TURN + 1,
            prize=None,
            kind="Airfield",
            task=Task.RUNWAY,
            base="Mount Pleasant",
        ),
    ]
    command.tickets = [
        Ticket(
            Prize("sam", 6, True, "A ticket for a SAM battery.", (), Player.RED),
            "X",
            12,
        )
    ]
    command.effects = [Effect("discount", "42% off SAM batteries", "WOLF", TURN + 3)]
    command.note(TURN, "achieved", "X", "A ticket for a SAM battery.")
    musk = SimpleNamespace(
        id="tgo-musk",
        name="MUSK",
        position=_At(-51.5),
        control_point=SimpleNamespace(name="Mount Pleasant"),
        units=[SimpleNamespace(alive=True)] * 3,
    )
    base = SimpleNamespace(id="cp-mpa", name="Mount Pleasant", position=_At(-51.8))
    return SimpleNamespace(
        turn=TURN,
        settings=SimpleNamespace(high_command_enabled=True, high_command_orders=3),
        opfor_high_command_active=True,
        high_command_for=lambda player: command,
        theater=SimpleNamespace(ground_objects=[musk], controlpoints=[base]),
        command=command,
    )


def test_the_read_carries_what_each_request_asks_and_where_to_strike() -> None:
    read = api.high_command(_game(), "red")

    musk, runway = read["requests"]
    assert musk["target_id"] == "tgo-musk" and musk["pos"] == [-51.5, -60.0]
    assert musk["asked"] == "Destroy every unit"
    assert musk["done_when"].startswith("Every unit destroyed: 3 units")
    assert musk["prize"] == {"line": "A ticket for a SAM battery.", "ticket": True}
    assert musk["tier"] == "high" and musk["turns_left"] == 2
    assert runway["target_id"] == "cp-mpa" and "prize" not in runway
    assert runway["asked"] == "OCA/Runway — crater the runway"
    assert read["tickets"][0]["steps"] == ["Where?", "Which system?"]
    assert read["tickets"][0]["state"] == "2 PICKS"
    assert read["effects"] == [
        {"label": "42% off SAM batteries", "earned_by": "WOLF", "turns_left": 3}
    ]
    assert [entry["outcome"] for entry in read["history"]] == ["achieved"]


def test_a_ticket_asks_its_picks_one_at_a_time() -> None:
    game = _game()

    first = api.ticket_choices(game, "red", 0, [])
    done = api.ticket_choices(game, "red", 0, ["7"])

    assert first["done"] is False and first["question"] == "Where?"
    assert [choice["key"] for choice in first["choices"]] == ["7", "8"]
    assert done == {
        "ticket": 0,
        "done": True,
        "picked": ["7", "SA-10"],
        "gives": "SA-10 set up at BEETLE.",
    }


def test_spending_gives_the_prize_and_the_ticket_goes() -> None:
    game = _game()

    result = api.spend_ticket(game, "red", 0, ["7"])

    assert result.ok and result.detail == "SA-10 set up at 7."
    assert GIVEN == [("7", "SA-10")]
    assert game.command.tickets == []
    assert game.command.history[-1].outcome == "spent"


def test_a_step_with_nothing_to_pick_keeps_the_ticket() -> None:
    game = _game()

    result = api.spend_ticket(game, "red", 0, ["8"])

    assert not result.ok and "nothing to pick" in (result.error or "")
    assert len(game.command.tickets) == 1


def test_a_missing_pick_or_a_wrong_index_is_refused() -> None:
    game = _game()

    assert "needs a pick" in (api.spend_ticket(game, "red", 0, []).error or "")
    assert "no ticket 3" in (api.spend_ticket(game, "red", 3, []).error or "")


def test_the_player_s_high_command_is_not_readable() -> None:
    with pytest.raises(service.SideNotAllowedError):
        service.high_command(side="blue")
    with pytest.raises(service.SideNotAllowedError):
        service.spend_ticket(side="blue", ticket=0, picked=[])
