"""Picking a man out of the leave list.

The rows are a grid of labels rather than a list view, so the click has to be turned
into a row by geometry -- which is exactly the kind of thing that works until somebody
adds a column. The colours themselves are the pilot picker's, so what is worth pinning
here is that the right row is found and that the tint says something.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication([])
        except Exception as exc:  # pragma: no cover - no display of any kind
            pytest.skip(f"no Qt platform available: {exc}")
    return app


def _dialog(qt_app: Any, cross_squadron: bool = False) -> Any:
    from dcs.unit import Skill
    from PySide6.QtCore import Qt

    from game.settings import Settings
    from game.squadrons import friendship
    from game.squadrons.pilot import Pilot
    from game.squadrons.squadron import Squadron
    from qt_ui.windows.LeaveRequestsDialog import LeaveRequestsDialog

    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value

    def squadron(name: str) -> Any:
        it: Any = Squadron.__new__(Squadron)
        it.settings = settings
        it.name = name
        it.nickname = None
        it.country = None
        it.aircraft = "F/A-18C"
        it.owned_aircraft = 12
        it.current_roster = []
        it.available_pilots = []
        it.coalition = SimpleNamespace(
            player=SimpleNamespace(is_blue=True), game=SimpleNamespace(turn=6)
        )
        return it

    home = squadron("VFA-2")
    away = squadron("VMFA-251") if cross_squadron else home

    chosen, friend, stranger = Pilot("Chosen"), Pilot("Friend"), Pilot("Stranger")
    friendship.move(friend, chosen, 5.0)
    friendship.move(chosen, friend, 5.0)
    requests: Any = [(home, chosen), (away, friend), (home, stranger)]
    for squadron_of, pilot in requests:
        squadron_of.current_roster.append(pilot)

    game: Any = SimpleNamespace(settings=settings, turn=6)
    dialog = LeaveRequestsDialog(game, requests)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    dialog.resize(1000, 400)
    dialog.show()
    qt_app.processEvents()
    return dialog


def test_a_click_lands_on_the_row_it_was_aimed_at(qt_app: Any) -> None:
    dialog = _dialog(qt_app)
    middle = dialog.rows[1].backdrop.geometry().center().y()
    dialog.select_at(middle)
    assert dialog.selected == 1


def test_clicking_the_same_man_twice_puts_the_list_back(qt_app: Any) -> None:
    dialog = _dialog(qt_app)
    middle = dialog.rows[0].backdrop.geometry().center().y()
    dialog.select_at(middle)
    dialog.select_at(middle)
    assert dialog.selected is None
    assert all("transparent" in row.backdrop.styleSheet() for row in dialog.rows)


def test_the_man_he_gets_on_with_is_the_one_that_is_coloured(qt_app: Any) -> None:
    dialog = _dialog(qt_app)
    dialog.select(0)
    assert "rgba(" in dialog.rows[1].backdrop.styleSheet()  # the friend
    assert "transparent" in dialog.rows[2].backdrop.styleSheet()  # the stranger


def test_it_says_what_the_colour_is_worth(qt_app: Any) -> None:
    dialog = _dialog(qt_app)
    dialog.select(0)
    assert "worth" in dialog.rows[1].cells[0].toolTip()


def test_a_friend_in_another_squadron_buys_nothing_and_says_so(qt_app: Any) -> None:
    """The bonus is a squadron's, so a colour on its own would let you get this
    exactly wrong."""
    dialog = _dialog(qt_app, cross_squadron=True)
    dialog.select(0)
    assert "nothing extra" in dialog.rows[1].cells[0].toolTip()
