"""The debriefing says which High Command requests the mission achieved, and what
each pays."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

from game.debriefingreport import DebriefingReport, RequestAchieved, requests_achieved
from game.game import Game
from game.highcommand.campaign import Task
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

    assert [(r.objective, r.prize, r.ticket, r.blue) for r in achieved] == [
        ("TURKEY", "A ticket for a SAM battery.", True, True),
        ("OX", "$96M added to our budget.", False, True),
    ]


def test_each_says_what_it_asked() -> None:
    runway = Order(
        "Mount Pleasant (OCA/Runway)",
        2,
        ordered_on=12,
        expires_on=TURN,
        prize=None,
        kind="Airfield",
        task=Task.RUNWAY,
        base="Mount Pleasant",
    )
    depot = Order("DEPOT", 0, ordered_on=12, expires_on=TURN, prize=None, kind="Depot")
    site = Order("OX", 1, ordered_on=12, expires_on=TURN, prize=None, kind="Oil field")
    closed = [Closed(order, Outcome.ACHIEVED) for order in (runway, depot, site)]

    achieved = requests_achieved(closed, [], TURN, True, motorpools={"DEPOT"})

    assert [(r.tier, r.kind, r.taken) for r in achieved] == [
        ("high tier", "Airfield", "The runway cratered"),
        ("low tier", "Depot", "One vehicle destroyed"),
        ("medium tier", "Oil field", "Every unit destroyed"),
    ]
    assert requests_achieved(closed, [], TURN, True, tiers=5)[0].tier == "tier 3 of 5"


def test_they_are_added_to_the_report_of_the_mission_just_flown() -> None:
    report = DebriefingReport(turn=TURN - 1)
    command = _command()
    game: Any = _game(report, command)

    Game._report_requests(game, CLOSED, blue=True)

    assert [request.objective for request in report.high_command] == ["TURKEY", "OX"]
    assert report.high_command[0].taken == "Every unit destroyed"


def test_a_report_that_cannot_be_written_does_not_stop_the_turn() -> None:
    report = DebriefingReport(turn=TURN - 1)
    game: Any = _game(report, _command())
    del game.theater

    Game._report_requests(game, CLOSED, blue=True)

    assert report.high_command == []


def test_a_report_from_an_older_mission_is_left_alone() -> None:
    report = DebriefingReport(turn=TURN - 3)
    game: Any = _game(report, _command())

    Game._report_requests(game, CLOSED, blue=True)

    assert report.high_command == []


def _game(report: DebriefingReport, command: HighCommand) -> SimpleNamespace:
    return SimpleNamespace(
        last_debriefing_report=report,
        turn=TURN,
        high_command=command,
        high_command_for=lambda side: command,
        theater=SimpleNamespace(ground_objects=[]),
        settings=SimpleNamespace(high_command_orders=3),
    )


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


def test_the_enemy_s_requests_are_shown_only_when_the_campaign_reports_them(
    qt_app: Any,
) -> None:
    from qt_ui.windows.QDebriefingWindow import (
        GroupHeader,
        QDebriefingWindow,
        RequestRow,
    )

    report = DebriefingReport(turn=TURN - 1)
    report.high_command = [
        RequestAchieved("TURKEY", "Cash.", False, True),
        RequestAchieved("MUSK", "A ticket.", True, False),
    ]
    shell: Any = SimpleNamespace(_section=lambda caption, hint, card: card)

    report.game = SimpleNamespace(
        settings=SimpleNamespace(high_command_report_enemy=True)
    )
    shown = QDebriefingWindow._high_command_section(shell, report)
    assert shown is not None
    assert [h.title for h in shown.findChildren(GroupHeader)] == ["OURS", "ENEMY"]
    assert len(shown.findChildren(RequestRow)) == 2

    report.game = SimpleNamespace(
        settings=SimpleNamespace(high_command_report_enemy=False)
    )
    hidden = QDebriefingWindow._high_command_section(shell, report)
    assert hidden is not None
    assert hidden.findChildren(GroupHeader) == []
    assert len(hidden.findChildren(RequestRow)) == 1


def test_a_row_says_it_was_achieved_and_what_it_asked(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import RequestRow, request_summary

    request = RequestAchieved(
        "OX",
        "A ticket for a SAM battery.",
        True,
        tier="medium tier",
        kind="Oil field",
        taken="Every unit destroyed",
    )

    assert request_summary(request) == "Medium tier · Oil field · Every unit destroyed"
    row = RequestRow(request)
    row.resize(900, row.height())
    assert not row.grab().isNull()


def test_a_request_from_an_older_save_still_shows(qt_app: Any) -> None:
    from qt_ui.windows.QDebriefingWindow import RequestRow, request_summary

    saved = dict(RequestAchieved("OX", "Cash.", False).__dict__)
    for name in ("tier", "kind", "taken"):
        del saved[name]
    request = RequestAchieved.__new__(RequestAchieved)
    request.__setstate__(saved)

    assert request_summary(request) == ""
    row = RequestRow(request)
    row.resize(900, row.height())
    assert not row.grab().isNull()
