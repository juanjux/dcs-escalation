"""The debriefing says which High Command requests the mission achieved, and what
each pays."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from game.debriefingreport import DebriefingReport, RequestAchieved, requests_achieved
from game.game import Game
from game.highcommand.orders import Closed, HighCommand, Order, Outcome
from game.highcommand.prizes import Prize

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TURN = 15


def _closed(objective: str, outcome: Outcome, ticket: bool) -> Closed:
    prize = Prize("cash", 5, ticket, "A ticket." if ticket else "Cash.", ())
    order = Order(objective, 1, ordered_on=12, expires_on=TURN, prize=prize)
    return Closed(order, outcome)


def _command() -> HighCommand:
    command = HighCommand()
    command.note(TURN, "achieved", "TURKEY", "A ticket for a SAM battery.")
    command.note(TURN, "achieved", "OX", "$96M added to our budget.")
    command.note(TURN, "expired", "HERRING", "ran out after 3 turns")
    return command


CLOSED = [
    _closed("TURKEY", Outcome.ACHIEVED, ticket=True),
    _closed("OX", Outcome.ACHIEVED, ticket=False),
    _closed("HERRING", Outcome.EXPIRED, ticket=False),
]


def test_only_the_achieved_requests_are_reported_with_what_they_paid() -> None:
    achieved = requests_achieved(CLOSED, _command().history, TURN, blue=True)

    assert achieved == [
        RequestAchieved("TURKEY", "A ticket for a SAM battery.", True, True),
        RequestAchieved("OX", "$96M added to our budget.", False, True),
    ]


def test_they_are_added_to_the_report_of_the_mission_just_flown() -> None:
    report = DebriefingReport(turn=TURN - 1)
    game: Any = SimpleNamespace(
        last_debriefing_report=report, turn=TURN, high_command=_command()
    )

    Game._report_requests(game, CLOSED, blue=True)

    assert [request.objective for request in report.high_command] == ["TURKEY", "OX"]


def test_a_report_from_an_older_mission_is_left_alone() -> None:
    report = DebriefingReport(turn=TURN - 3)
    game: Any = SimpleNamespace(
        last_debriefing_report=report, turn=TURN, high_command=_command()
    )

    Game._report_requests(game, CLOSED, blue=True)

    assert report.high_command == []


@pytest.fixture
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_window_lists_them(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import QDebriefingWindow, RequestRow

    report = DebriefingReport(turn=TURN - 1)
    report.high_command = requests_achieved(CLOSED, _command().history, TURN, blue=True)
    shell: Any = SimpleNamespace(_section=lambda caption, hint, card: card)

    card = QDebriefingWindow._high_command_section(shell, report)

    assert card is not None
    assert len(card.findChildren(RequestRow)) == 2
    assert QDebriefingWindow._high_command_section(shell, DebriefingReport()) is None
