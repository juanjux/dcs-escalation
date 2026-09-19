"""A position, and what can be done with it.

Copying it was the only thing on offer, which is one keystroke short of the thing
anybody actually wants: the point in the aeroplane. The button is a small menu now --
copy, or write it down for one of the flights the player is sitting in, as a waypoint
or a markpoint. A campaign with nobody flying anything still gets the plain Copy it
always had.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)
from dcs import Point

from game.coordinates import format_for


class CoordinateLabel(QWidget):
    """The formatted position, and what to do with it beside it.

    The text is selectable, so it can also be picked out by hand. The format comes from
    the campaign's ``coordinate_format`` setting.

    ``game`` is optional: without it -- a test double, a dialog that has no way to
    reach one -- the button copies and nothing more.
    """

    def __init__(
        self,
        position: Point,
        settings: Any,
        parent: Optional[QWidget] = None,
        compact: bool = False,
        game: Any = None,
    ) -> None:
        super().__init__(parent)
        self.text = format_for(settings, position)
        self.position = position
        self.game = game

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(self.text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setProperty("style", "small")
        if compact:
            label.setStyleSheet(
                "font-size: 11px; color: #8E9DAA; background: transparent;"
                " border: none;"
            )
        layout.addWidget(label)

        self.button = QPushButton("" if compact else "Copy")
        self.button.setProperty("style", "btn-small")
        self.button.setToolTip("Copy these coordinates to the clipboard")
        if compact:
            # A row has no room for a word, and the glyph is the one the map uses.
            # Styled here rather than left to the app sheet, whose grey gradient
            # disappears into a dark card.
            self.button.setFixedSize(22, 22)
            self.button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.button.setIcon(QIcon(_copy_icon()))
            self.button.setStyleSheet(
                "QPushButton { background: #1B2732;"
                " border: 1px solid #2C3A47; border-radius: 3px; }"
                "QPushButton:hover { background: #24323F; }"
            )
        else:
            self.button.setMaximumWidth(60)
        self.button.clicked.connect(self.pressed)
        layout.addWidget(self.button)
        if not compact:
            layout.addStretch()

        self.setLayout(layout)

    # ------------------------------------------------------------------ actions

    def pressed(self) -> None:
        """Copy, unless there is an aircraft to put it in and a choice to make."""
        receivers = self._receivers()
        if not receivers:
            self.copy()
            return
        menu = QMenu(self)
        copy = QAction("Copy coordinates", menu)
        copy.triggered.connect(self.copy)
        menu.addAction(copy)
        menu.addSeparator()
        for kind in _kinds():
            self._add_kind(menu, kind, receivers)
        menu.exec(self.button.mapToGlobal(QPoint(0, self.button.height())))

    def copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text)

    def _receivers(self) -> list[Any]:
        if self.game is None:
            return []
        try:
            from game.ato.savedpoints import receivers

            return list(receivers(self.game.blue))
        except Exception:
            return []

    def _add_kind(self, menu: QMenu, kind: Any, receivers: list[Any]) -> None:
        """One entry per kind, with the aircraft behind it when there is a choice."""
        from game.ato.savedpoints import room_for

        label = f"Save as {kind.label.lower()}"
        if len(receivers) == 1:
            flight = receivers[0]
            action = QAction(f"{label} ({_name(flight)})", menu)
            self._wire(action, flight, kind, room_for(flight, kind))
            menu.addAction(action)
            return
        submenu = menu.addMenu(label)
        for flight in receivers:
            action = QAction(_name(flight), submenu)
            self._wire(action, flight, kind, room_for(flight, kind))
            submenu.addAction(action)

    def _wire(self, action: QAction, flight: Any, kind: Any, room: int) -> None:
        if room <= 0:
            action.setEnabled(False)
            action.setToolTip(f"{_name(flight)} has no room for another {kind.label}")
            return
        action.setToolTip(f"Room for {room} more")
        action.triggered.connect(
            lambda _checked=False, f=flight, k=kind: self._save(f, k)
        )

    def _save(self, flight: Any, kind: Any) -> None:
        from game.ato.savedpoints import SavedPoint, add_point

        add_point(
            flight,
            SavedPoint(kind=kind, name=self.text, x=self.position.x, y=self.position.y),
        )


def _kinds() -> list[Any]:
    from game.ato.savedpoints import PointKind

    return list(PointKind)


def _name(flight: Any) -> str:
    """A flight has no callsign until the mission is generated, so this is what the
    rest of the app shows: the name the player gave it, or its task."""
    return (
        str(getattr(flight, "custom_name", None) or flight.flight_type.value)
        + f" · {flight.unit_type.display_name}"
    )


def _copy_icon(ink: str = "#9FADB9") -> QPixmap:
    """Two overlapping sheets, drawn rather than typed.

    The copy glyph is not in every font the application may be running with, and a
    missing glyph is a blank square on a button nobody then presses.
    """
    icon = QPixmap(14, 14)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(ink), 1.2))
    painter.drawRoundedRect(QRectF(1.5, 3.5, 7.5, 9), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(5, 1.5, 7.5, 9), 1.5, 1.5)
    painter.end()
    return icon
