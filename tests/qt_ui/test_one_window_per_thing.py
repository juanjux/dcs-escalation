"""One window per thing, however many times it is asked for."""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def test_the_same_thing_opens_the_same_window(qt_app: Any) -> None:
    """Clicking a package twice left two identical windows stacked on each other."""
    from PySide6.QtWidgets import QDialog

    from qt_ui.dialogs import open_once

    built: list[QDialog] = []

    def build() -> QDialog:
        dialog = QDialog()
        built.append(dialog)
        return dialog

    first = open_once("package:1", build)
    again = open_once("package:1", build)
    assert again is first
    assert len(built) == 1

    # A different thing is a different window.
    other = open_once("package:2", build)
    assert other is not first
    assert len(built) == 2
    first.close()
    other.close()


def test_a_closed_window_is_built_again(qt_app: Any) -> None:
    """Rebuilt rather than shown again, so it never comes back with a turn-old view
    of the game."""
    from PySide6.QtWidgets import QDialog

    from qt_ui.dialogs import open_once

    built: list[QDialog] = []

    def build() -> QDialog:
        dialog = QDialog()
        built.append(dialog)
        return dialog

    first = open_once("flight:1", build)
    first.close()
    second = open_once("flight:1", build)
    assert second is not first
    assert len(built) == 2
    second.close()


def test_a_window_qt_destroyed_is_let_go_of(qt_app: Any) -> None:
    """The C++ object goes when its parent does; asking the wrapper anything after
    that raises."""
    import shiboken6
    from PySide6.QtWidgets import QDialog, QWidget

    from qt_ui.dialogs import _live, open_once

    parent = QWidget()
    dialog = open_once("pilot:1", lambda: QDialog(parent))
    assert _live.get("pilot:1") is dialog

    shiboken6.delete(parent)
    qt_app.processEvents()
    assert "pilot:1" not in _live

    # And the next ask builds a new one rather than raising.
    again = open_once("pilot:1", QDialog)
    assert again is not None
    again.close()


def test_a_window_is_not_raised_for_something_it_is_not_about(qt_app: Any) -> None:
    """A package has no id of its own, so its key is the address of the object -- and
    an address a deleted package gave up can be handed to the next one."""
    from PySide6.QtWidgets import QDialog

    from qt_ui.dialogs import open_once

    first = QDialog()
    first.about = "package A"  # type: ignore[attr-defined]
    second = QDialog()
    second.about = "package B"  # type: ignore[attr-defined]

    opened = open_once("package:1", lambda: first)
    assert opened is first

    # The same key, a different package: the window up is not the one being asked for.
    again = open_once(
        "package:1",
        lambda: second,
        about=lambda window: getattr(window, "about", None) == "package B",
    )
    assert again is second
    second.close()
