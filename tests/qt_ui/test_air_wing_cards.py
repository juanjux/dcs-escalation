"""Cards taken out of the squadrons column must not be left on the screen.

A widget with no parent is a top-level window, and one that still has its shown flag
when it loses its parent is a window on the desktop. Nothing ever closed those: the
pane keeps its cards and puts them back, so they are nobody's to delete. Changing a
squadron's pilot limit rebuilds the column, which scattered the whole list of them
across the desktop -- twelve of them, on one click of the spinner.

The window never appears under the offscreen platform the tests run on, so what is
checked here is the order: hidden, and then unparented.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def test_a_card_is_hidden_before_it_loses_its_parent(qt_app: Any) -> None:
    from PySide6.QtWidgets import QApplication, QLabel, QWidget

    from qt_ui.windows.airwingconfig.dialog import SquadronsPane

    class Card(QLabel):
        """A card that remembers what was done to it, and in which order."""

        def __init__(self, name: str) -> None:
            super().__init__(name)
            self.done: list[str] = []

        def hide(self) -> None:
            self.done.append("hidden")
            super().hide()

        def setParent(self, parent: Optional[QWidget]) -> None:  # type: ignore[override]
            self.done.append("kept" if parent is not None else "unparented")
            super().setParent(parent)

    # The pane only asks its tab for the Add button's handler.
    pane = SquadronsPane(cast(Any, SimpleNamespace(add_squadron=lambda: None)))
    pane.show()
    QApplication.processEvents()

    first = Card("391st Fighter Squadron")
    pane.show_cards([first], "Squadrons", "none")  # type: ignore[list-item]
    QApplication.processEvents()
    first.done.clear()

    # Rebuilt with somebody else in it, the way changing a pilot limit rebuilds it.
    pane.show_cards([Card("34th Bomb Squadron")], "Squadrons", "none")  # type: ignore[list-item]
    QApplication.processEvents()

    assert "unparented" in first.done
    assert first.done.index("hidden") < first.done.index("unparented")
    assert first.parent() is None
    assert not first.isVisible()
    pane.close()
