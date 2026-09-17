"""Holding an arrow key on a squadron's size must not throw the focus away.

Changing a number refreshes the counters, which rebuilds the list of types, and
rebuilding a list moves its selection -- which takes the keyboard focus with it. The
first press then worked and the second went to the type list instead.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_counter_refresh_puts_the_focus_back(qt_app: Any) -> None:
    from PySide6.QtWidgets import QLineEdit, QWidget

    from qt_ui.windows.airwingconfig.dialog import AirWingConfigurationTab

    holder = QWidget()
    box = QLineEdit(holder)
    holder.show()
    box.setFocus()
    assert holder.focusWidget() is box

    # What the refresh does to the focus, without a campaign behind it: the tab's
    # own method, given panes that only have to answer refresh().
    tab = AirWingConfigurationTab.__new__(AirWingConfigurationTab)
    stolen = QLineEdit(holder)

    class _Pane:
        def refresh(self, *args: Any, **kwargs: Any) -> None:
            stolen.setFocus()

    tab.type_list = _Pane()  # type: ignore[assignment]
    tab.bases_pane = _Pane()  # type: ignore[assignment]
    tab.window = lambda: holder  # type: ignore[method-assign]

    AirWingConfigurationTab._refresh_counters(tab)

    assert holder.focusWidget() is box
