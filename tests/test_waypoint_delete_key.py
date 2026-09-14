"""Delete removes the selected waypoints, under the same rule the button obeys.

The list is the one place in the flight editor where waypoints are picked, and the
only way to remove one was a button at the other end of the tab. The key must not be
able to do what the button refuses to: half a deletion is worse than none.
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
    yield QApplication.instance() or QApplication([])


def _list(qt_app: Any) -> Any:
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
        QFlightWaypointList,
    )

    return QFlightWaypointList.__new__(QFlightWaypointList)


def test_delete_asks_the_tab_rather_than_deleting_itself(qt_app: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QTableView

    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
        QFlightWaypointList,
    )

    view = QFlightWaypointList.__new__(QFlightWaypointList)
    QTableView.__init__(view)
    asked: list[bool] = []
    view.delete_requested.connect(lambda: asked.append(True))

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier
    )
    view.keyPressEvent(event)

    assert asked == [True]
    assert event.isAccepted()


def test_another_key_is_left_to_the_table(qt_app: Any) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QTableView

    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
        QFlightWaypointList,
    )

    view = QFlightWaypointList.__new__(QFlightWaypointList)
    QTableView.__init__(view)
    asked: list[bool] = []
    view.delete_requested.connect(lambda: asked.append(True))

    view.keyPressEvent(
        QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )
    )

    assert asked == []


def test_the_key_obeys_the_buttons_rule() -> None:
    """The tab's handler, without Qt: a disabled button means the key does nothing."""
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab import (
        QFlightWaypointTab,
    )

    deleted: list[bool] = []
    tab = SimpleNamespace(
        delete_selected=SimpleNamespace(isEnabled=lambda: False),
        on_delete_waypoint=lambda: deleted.append(True),
    )
    QFlightWaypointTab.on_delete_requested(tab)  # type: ignore[arg-type]
    assert deleted == []

    tab.delete_selected = SimpleNamespace(isEnabled=lambda: True)
    QFlightWaypointTab.on_delete_requested(tab)  # type: ignore[arg-type]
    assert deleted == [True]
