"""Picking a man out of the leave list.

The rows are a grid of labels rather than a list view, so the click has to be turned
into a row by geometry -- which is exactly the kind of thing that works until somebody
adds a column. The colours themselves are the pilot picker's, so what is worth pinning
here is that the right row is found and that the tint says something.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_dialogs: list[Any] = []


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


@pytest.fixture(autouse=True)
def cleanup_dialogs(qt_app: Any) -> Iterator[None]:
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    yield
    # Retain wrappers until Qt has destroyed the widgets. Closing a dialog only
    # hides it; deferred destruction must finish before the next modal is shown.
    for dialog in reversed(_dialogs):
        dialog.close()
        dialog.body.removeEventFilter(dialog)
        dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()
    assert all(not isValid(dialog) for dialog in _dialogs)
    _dialogs.clear()


def _dialog(
    qt_app: Any,
    cross_squadron: bool = False,
    *,
    aircraft: int = 12,
    extra_pilots: int = 0,
    configure: Callable[[Any], None] | None = None,
) -> Any:
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
        it.owned_aircraft = aircraft
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
        pilot.wants_leave = True
    for squadron_of in ([home, away] if cross_squadron else [home]):
        squadron_of.current_roster.extend(
            Pilot(f"Reserve {index}") for index in range(extra_pilots)
        )
    if configure is not None:
        configure(requests)

    game: Any = SimpleNamespace(settings=settings, turn=6)
    dialog = LeaveRequestsDialog(game, requests)
    _dialogs.append(dialog)
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


@pytest.mark.parametrize(
    ("aircraft", "expected"),
    [
        (0, [True, True, True]),
        (2, [True, True, True]),
        (4, [True, False, False]),
        (5, [False, False, False]),
        (6, [False, False, False]),
    ],
)
def test_defaults_grant_only_with_enough_remaining_pilots(
    qt_app: Any, aircraft: int, expected: list[bool]
) -> None:
    dialog = _dialog(qt_app, aircraft=aircraft, extra_pilots=2)
    try:
        assert [row.grant.isChecked() for row in dialog.rows] == expected
        assert all(
            row.pilot.wants_leave and not row.pilot.on_leave for row in dialog.rows
        )
        assert len(dialog.rows[0].squadron.current_roster) == 5
    finally:
        dialog.close()


def test_grant_updates_every_row_in_its_squadron_and_can_be_undone(qt_app: Any) -> None:
    dialog = _dialog(qt_app, aircraft=4, extra_pilots=2)
    try:
        assert all(row.cells[4].text() == "4 free · 4 aircraft" for row in dialog.rows)
        dialog.rows[0].grant.setChecked(False)
        assert all(row.cells[4].text() == "5 free · 4 aircraft" for row in dialog.rows)
        dialog.rows[1].grant.setChecked(True)
        assert all(row.cells[4].text() == "4 free · 4 aircraft" for row in dialog.rows)
        # Manual decisions may still accept a shortage, but every row must warn.
        dialog.rows[2].grant.setChecked(True)
        assert all("<b>3 free</b>" in row.cells[4].text() for row in dialog.rows)
        assert all("fewer pilots" in row.cells[4].toolTip() for row in dialog.rows)
        dialog.select(0)
        assert all("fewer pilots" in row.cells[4].toolTip() for row in dialog.rows)
        dialog.rows[2].grant.setChecked(False)
        assert all(row.cells[4].text() == "4 free · 4 aircraft" for row in dialog.rows)
        assert all("fewer pilots" not in row.cells[4].toolTip() for row in dialog.rows)
    finally:
        dialog.close()


def test_cover_and_defaults_are_independent_between_squadrons(qt_app: Any) -> None:
    dialog = _dialog(qt_app, cross_squadron=True, aircraft=4, extra_pilots=3)
    try:
        assert [row.grant.isChecked() for row in dialog.rows] == [True, False, False]
        dialog.rows[0].grant.setChecked(False)
        assert dialog.rows[0].cells[4].text() == "5 free · 4 aircraft"
        assert dialog.rows[2].cells[4].text() == "5 free · 4 aircraft"
        assert dialog.rows[1].cells[4].text() == "4 free · 4 aircraft"
    finally:
        dialog.close()


def test_grant_all_and_clear_all_refresh_cover_and_header(qt_app: Any) -> None:
    from PySide6.QtCore import Qt

    dialog = _dialog(qt_app, aircraft=4, extra_pilots=2)
    try:
        assert dialog.grant_all.checkState() == Qt.CheckState.PartiallyChecked
        dialog.grant_all.setCheckState(Qt.CheckState.Checked)
        assert all(row.grant.isChecked() for row in dialog.rows)
        assert all("2 free" in row.cells[4].text() for row in dialog.rows)
        dialog.grant_all.setCheckState(Qt.CheckState.Unchecked)
        assert not any(row.grant.isChecked() for row in dialog.rows)
        assert all(row.cells[4].text() == "5 free · 4 aircraft" for row in dialog.rows)
    finally:
        dialog.close()


def test_partial_grant_all_renders_a_visible_dash(qt_app: Any) -> None:
    from PySide6.QtWidgets import QStyle, QStyleOptionButton

    dialog = _dialog(qt_app, aircraft=4, extra_pilots=2)
    button = dialog.grant_all
    option = QStyleOptionButton()
    button.initStyleOption(option)
    indicator = button.style().subElementRect(
        QStyle.SubElement.SE_CheckBoxIndicator, option, button
    )
    image = button.grab().toImage()
    assert image.pixelColor(indicator.center()).name() == "#ffffff"
    assert (
        image.pixelColor(indicator.left() + 1, indicator.top() + 1).name() == "#83a56a"
    )


def test_default_grants_prioritize_lowest_morale(qt_app: Any) -> None:
    def configure(requests: Any) -> None:
        for (_, pilot), morale in zip(requests, [60, 30, 10]):
            pilot.morale = morale

    dialog = _dialog(qt_app, aircraft=4, extra_pilots=2, configure=configure)
    try:
        assert [row.grant.isChecked() for row in dialog.rows] == [False, False, True]
    finally:
        dialog.close()


def test_unavailable_pilots_do_not_count_as_cover(qt_app: Any) -> None:
    from game.squadrons.pilot import PilotStatus

    def configure(requests: Any) -> None:
        squadron = requests[0][0]
        for pilot, status in zip(
            squadron.current_roster[3:],
            [PilotStatus.Wounded, PilotStatus.OnLeave, PilotStatus.Dead],
        ):
            pilot.status = status

    dialog = _dialog(qt_app, aircraft=2, extra_pilots=3, configure=configure)
    try:
        assert [row.grant.isChecked() for row in dialog.rows] == [True, False, False]
        assert all(row.cells[4].text() == "2 free · 2 aircraft" for row in dialog.rows)
    finally:
        dialog.close()


def test_answers_are_applied_only_on_confirmation(qt_app: Any) -> None:
    dialog = _dialog(qt_app, aircraft=4, extra_pilots=2)
    try:
        assert all(not row.pilot.on_leave for row in dialog.rows)
        dialog.answer()
        assert [row.pilot.on_leave for row in dialog.rows] == [True, False, False]
        assert not any(row.pilot.wants_leave for row in dialog.rows)
        assert dialog.rows[0].squadron.owned_aircraft == 4
    finally:
        dialog.close()
