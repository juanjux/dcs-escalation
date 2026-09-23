"""The Tickets tab: what each ticket says it is, and spending one a step at a time."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game.highcommand.orders import Ticket
from game.highcommand.prizes import CannotGive, Choice, Prize, PrizeKind, Step
from qt_ui.windows.highcommand import model as data

SITES = [Choice("7", "BEETLE", "Destroyed, at Mount Pleasant"), Choice("8", "WOLF")]
SYSTEMS = {"7": [Choice("Hawk", "Hawk", "Hawk CWAR, Hawk TR")], "8": []}


def _kind(key: str, *steps: Step) -> PrizeKind:
    return PrizeKind(key, lambda score, context: None, ticket=True, steps=steps)


KINDS = {
    "sam": _kind(
        "sam",
        Step("Where?", lambda game, prize, picked: SITES),
        Step("Which system?", lambda game, prize, picked: SYSTEMS[picked[0]], True),
    ),
    "runway": _kind("runway", Step("Which runway?", lambda game, prize, picked: [])),
    "awacs": _kind("awacs"),
}


@pytest.fixture(autouse=True)
def kinds(monkeypatch: Any) -> None:
    monkeypatch.setattr(data, "kind_of", lambda prize: KINDS.get(prize.kind))


def _ticket(kind: str, line: str = "A ticket for a SAM battery.") -> Ticket:
    return Ticket(Prize(kind, 6, True, line, ()), "WOLF", 11)


def _view(kind: str) -> data.TicketView:
    game: Any = SimpleNamespace(high_command=SimpleNamespace(tickets=[_ticket(kind)]))
    [view] = data.ticket_views(game)
    return view


def test_a_ticket_says_whether_it_can_be_spent_now() -> None:
    game: Any = SimpleNamespace()

    assert data.ticket_state(game, _ticket("awacs")) == data.READY
    assert data.ticket_state(game, _ticket("sam")) == "2 PICKS"
    assert data.ticket_state(game, _ticket("runway")) == data.NOT_NOW


def test_the_pane_is_titled_with_what_spending_gives() -> None:
    assert data.spending_title("A ticket for an extra AWACS for 3 turns.") == (
        "An extra AWACS for 3 turns."
    )
    assert data.spending_title("A ticket to put one pilot back.") == (
        "Put one pilot back."
    )


def test_the_preview_says_what_the_prize_s_give_will() -> None:
    assert data.preview("sam", ["BEETLE", "Hawk"]) == "Hawk set up at BEETLE."
    assert data.preview("runway", ["Mount Pleasant"]) == (
        "The runway at Mount Pleasant is repaired."
    )
    assert data.preview("awacs", []).startswith("Nothing to pick.")


@pytest.fixture
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _pane(spend: Any) -> Any:
    from qt_ui.windows.highcommand.tickets import SpendPane

    return SpendPane(spend)


def test_a_step_with_one_option_is_picked_by_itself(qt_app: Any) -> None:
    spent: list[tuple[str, ...]] = []

    def spend(ticket: Any, picked: tuple[str, ...]) -> str:
        spent.append(picked)
        return "Hawk set up."

    pane = _pane(spend)
    pane.show_ticket(
        SimpleNamespace(theater=SimpleNamespace(ground_objects=[])), _view("sam")
    )

    assert not pane.go.isEnabled()
    pane._pick(SITES[0])

    assert [choice.key for choice in pane.picked] == ["7", "Hawk"]
    assert pane.go.isEnabled()
    assert pane.preview.text() == "Hawk set up at BEETLE. Spending is final."
    pane.go.click()
    assert spent == [("7", "Hawk")]
    assert pane.result == "Hawk set up." and pane.go.text() == "Next ticket"


def test_a_step_with_nothing_to_pick_blocks_the_spend(qt_app: Any) -> None:
    pane = _pane(lambda ticket, picked: "given")
    pane.show_ticket(SimpleNamespace(), _view("sam"))

    pane._pick(SITES[1])

    assert not pane.go.isEnabled()
    pane._change(0)
    assert pane.picked == []


def test_a_refusal_keeps_the_ticket_and_says_why(qt_app: Any) -> None:
    def refuse(ticket: Any, picked: Any) -> str:
        raise CannotGive("None of our bases has room.")

    pane = _pane(refuse)
    pane.show_ticket(SimpleNamespace(), _view("awacs"))

    pane.go.click()

    assert pane.result is None
    assert pane.refusal == "None of our bases has room."
    assert pane.go.text() == "Try again"
