"""Copy coordinates or save a waypoint shared by all player aircraft."""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)
from dcs import Point

from game.ato.savedpoints import PointKind, SavedPoint, campaign_points
from game.coordinates import format_for

if TYPE_CHECKING:
    from game import Game


class CoordinateLabel(QWidget):
    """The formatted position, and what to do with it beside it.

    The text is selectable, so it can also be picked out by hand. The format comes from
    the campaign's ``coordinate_format`` setting.

    Without a campaign, the button just copies the coordinates.
    """

    def __init__(
        self,
        position: Point,
        settings: Any,
        parent: Optional[QWidget] = None,
        compact: bool = False,
        game: Optional[Game] = None,
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

        self.button = QPushButton("" if compact else ("GPS" if game else "Copy"))
        self.button.setProperty("style", "btn-small")
        self.button.setToolTip(
            "Copy or save these coordinates as a campaign waypoint"
            if game is not None
            else "Copy these coordinates to the clipboard"
        )
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
        if self.game is None:
            self.copy()
            return
        menu = QMenu(self)
        menu.addAction("Copy coordinates", self.copy)
        menu.addSeparator()
        menu.addAction("Save as waypoint", self._save)
        menu.exec(self.button.mapToGlobal(QPoint(0, self.button.height())))

    def copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text)

    def _save(self) -> None:
        if self.game is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Save as waypoint", "Waypoint name", text=self.text
        )
        if not accepted:
            return

        from game.elevation import elevation_ft
        from game.server.savedpoints.notifications import publish_points_changed

        latlng = self.position.latlng()
        height = elevation_ft(latlng.lat, latlng.lng)

        campaign_points(self.game.blue).append(
            SavedPoint(
                kind=PointKind.WAYPOINT,
                name=name.strip() or self.text,
                x=self.position.x,
                y=self.position.y,
                altitude_ft=height if height is not None else 0,
            )
        )
        publish_points_changed()


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
