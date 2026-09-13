"""The command palette: the menus as searchable things, and following what is found.

The menus are walked rather than listed, so a menu entry added later is findable
without anyone remembering to register it -- which only works if the walk keeps up
with nesting, separators and mnemonics.
"""

from __future__ import annotations

import os
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def _menubar(shape: dict[str, list[str]]) -> Any:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenuBar

    bar = QMenuBar()
    for menu_name, items in shape.items():
        menu = bar.addMenu(menu_name)
        for item in items:
            if item == "-":
                menu.addSeparator()
            else:
                menu.addAction(QAction(item, bar))
    return bar


def test_the_menus_are_walked_into(qt_app: Any) -> None:
    from qt_ui.windows.palette.actions import action_entries

    bar = _menubar({"&File": ["&Save", "Save &As"], "&Help": ["&About"]})
    assert [entry.label for entry in action_entries(bar)] == [
        "Save",
        "Save As",
        "About",
    ]


def test_a_mnemonic_is_not_part_of_the_name(qt_app: Any) -> None:
    """Nobody searches for "&Save"."""
    from qt_ui.windows.palette.actions import clean

    assert clean("&Save") == "Save"
    assert clean("Save &As") == "Save As"
    assert clean("Fish && Chips") == "Fish & Chips"


def test_separators_are_not_commands(qt_app: Any) -> None:
    from qt_ui.windows.palette.actions import action_entries

    bar = _menubar({"&File": ["&Save", "-", "E&xit"]})
    assert [entry.label for entry in action_entries(bar)] == ["Save", "Exit"]


def test_a_command_says_which_menu_it_is_in(qt_app: Any) -> None:
    """Two menus can hold "Open", and the trail is what tells them apart."""
    from qt_ui.windows.palette.actions import action_entries

    bar = _menubar({"&File": ["&Open"]})
    entry = next(iter(action_entries(bar)))
    assert entry.detail == "File"
    assert "file" in entry.haystack


def test_a_command_can_be_found_again_from_what_it_was_indexed_under(
    qt_app: Any,
) -> None:
    """The pair in a Follow is all that survives the search, and a QSettings history
    keeps it between sessions, so it has to still address the same row."""
    from qt_ui.windows.palette.actions import action_at, action_entries

    bar = _menubar({"&File": ["&Save", "Save &As"], "&Help": ["&About"]})
    for entry in action_entries(bar):
        found = action_at(bar, entry.follow.key)
        assert found is not None
        from qt_ui.windows.palette.actions import clean

        assert clean(found.text()) == entry.label


def test_a_command_that_is_no_longer_there_is_not_found(qt_app: Any) -> None:
    """Menus change between versions, and a stale history must not raise."""
    from qt_ui.windows.palette.actions import action_at

    bar = _menubar({"&File": ["&Save"]})
    assert action_at(bar, "File › Something Else") is None
    assert action_at(None, "anything") is None


def test_a_shortcut_is_worth_searching_for(qt_app: Any) -> None:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenuBar

    from qt_ui.windows.palette.actions import action_entries

    bar = QMenuBar()
    menu = bar.addMenu("&File")
    action = QAction("&Save", bar)
    action.setShortcut("CTRL+S")
    menu.addAction(action)

    entry = next(iter(action_entries(bar)))
    assert "Ctrl+S" in entry.detail


# -- the box itself ---------------------------------------------------------------


def _window(shape: dict[str, list[str]]) -> Any:
    """A real window, because the palette is a dialog and a dialog needs a parent.

    Its menus are built the way the main window builds them: a QMenuBar inside a strip
    that also holds the toolbar icons, installed with ``setMenuWidget``. That shape is
    the whole point -- a window with an ordinary menu bar would not have caught the
    palette calling ``menuBar()``, which on this one threw the strip away.

    It carries the three things the palette asks of the main window: its menus, the
    campaign, and the index of it.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QWidget

    from game.search.index import GameIndex

    window = cast(Any, QMainWindow())
    window.menu_bar = _menubar({})
    for menu_name, items in shape.items():
        menu = window.menu_bar.addMenu(menu_name)
        for item in items:
            if item == "-":
                menu.addSeparator()
            else:
                menu.addAction(QAction(item, window))

    window.menu_strip = QWidget()
    row = QHBoxLayout()
    row.addWidget(window.menu_bar)
    window.menu_strip.setLayout(row)
    window.setMenuWidget(window.menu_strip)

    window.game_model = type("Model", (), {"game": None})()
    window.search_index = GameIndex()
    window.palette_child_dialogs = []
    return window


def _palette(qt_app: Any, shape: dict[str, list[str]] | None = None) -> Any:
    from qt_ui.windows.palette.palette import CommandPalette

    window = _window(shape or {"&File": ["&Save", "&Open"], "&Help": ["Show &logs"]})
    palette = cast(Any, CommandPalette(window))
    # Held, or the window is collected and the palette is left without a parent.
    palette._test_window = window
    return palette


def test_typing_finds_a_command(qt_app: Any) -> None:
    palette = _palette(qt_app)
    palette.query.setText("logs")
    palette.run_search()
    assert [hit.entry.label for hit in palette._hits] == ["Show logs"]


def test_nothing_typed_with_no_history_shows_nothing(qt_app: Any) -> None:
    palette = _palette(qt_app)
    palette.recent_keys = lambda: []
    palette.query.setText("")
    palette.run_search()
    assert palette._hits == []
    assert "Type to search" in palette.summary("")


def test_nothing_typed_offers_what_was_opened_last(qt_app: Any) -> None:
    """An empty box that says nothing is a box not worth opening."""
    palette = _palette(qt_app)
    palette.recent_keys = lambda: ["action:File › Save"]
    palette.query.setText("")
    palette.run_search()
    assert [hit.entry.label for hit in palette._hits] == ["Save"]


def test_a_query_that_matches_nothing_says_so(qt_app: Any) -> None:
    palette = _palette(qt_app)
    palette.query.setText("zzzzzz")
    palette.run_search()
    assert palette._hits == []
    assert palette.summary("zzzzzz") == "Nothing matches."


def test_the_arrows_wrap_round_the_list(qt_app: Any) -> None:
    """Down from the last row is the first: thirty results and one hand on the
    keyboard."""
    palette = _palette(qt_app)
    palette.query.setText("s")
    palette.run_search()
    assert palette.results.count() >= 2

    palette.results.setCurrentRow(palette.results.count() - 1)
    palette.step(1)
    assert palette.results.currentRow() == 0
    palette.step(-1)
    assert palette.results.currentRow() == palette.results.count() - 1


def test_following_nothing_does_nothing(qt_app: Any) -> None:
    """Enter on an empty list must not reach for a row that is not there."""
    palette = _palette(qt_app)
    palette.query.setText("zzzzzz")
    palette.run_search()
    palette.follow_selected()  # no exception is the assertion


def test_searching_without_a_campaign_still_finds_commands(qt_app: Any) -> None:
    """Half of what the palette does works before a campaign is loaded."""
    palette = _palette(qt_app)
    assert palette.window_.game_model.game is None
    palette.query.setText("save")
    palette.run_search()
    assert [hit.entry.label for hit in palette._hits] == ["Save"]


def test_opening_the_palette_leaves_the_menu_row_alone(qt_app: Any) -> None:
    """The window's menus and its toolbar icons share one strip, and QMainWindow's
    menuBar() builds an empty bar and installs it in the strip's place when the window
    has no bar of its own -- which took the whole row off the window, for good, on the
    first Ctrl+P, and the shortcut with it."""
    palette = _palette(qt_app)
    window = palette._test_window
    strip = window.menu_strip

    palette.run_search()
    palette.follow_selected()

    assert window.menuWidget() is strip
    assert [_clean(action.text()) for action in window.menu_bar.actions()] == [
        "File",
        "Help",
    ]


def test_the_menu_bar_is_found_without_being_built(qt_app: Any) -> None:
    from qt_ui.windows.palette.actions import menu_bar_of

    window = _window({"&File": ["&Save"]})
    assert menu_bar_of(window) is window.menu_bar

    # Any other window answers with its real bar, and with nothing when it has none.
    from PySide6.QtWidgets import QMainWindow

    plain = cast(Any, QMainWindow())
    bar = plain.menuBar()
    assert menu_bar_of(plain) is bar
    assert menu_bar_of(None) is None


def _clean(text: str) -> str:
    from qt_ui.windows.palette.actions import clean

    return clean(text)


def test_a_pilot_opens_his_own_dialog_when_the_window_has_one(qt_app: Any) -> None:
    """And his squadron's when it has not: the two are separate changes, and a row
    that does nothing is worse than a row that does the nearest thing."""
    from game.search.index import Follow
    from game.search.providers import PILOT
    from qt_ui.windows.palette.follow import _open_pilot

    window = _window({"&File": ["&Save"]})
    pilot, squadron = object(), object()

    opened: list[Any] = []
    window.open_pilot_dialog = opened.append
    _open_pilot(window, pilot, squadron)
    assert opened == [pilot]

    # Nothing to open him with, and nobody to open: no exception either way.
    del window.open_pilot_dialog
    _open_pilot(window, None, None)
    assert Follow(PILOT, "x").kind == PILOT
