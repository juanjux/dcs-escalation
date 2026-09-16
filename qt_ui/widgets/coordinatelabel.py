"""A position with a button that copies it to the clipboard."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)
from dcs import Point

from game.coordinates import format_for


class CoordinateLabel(QWidget):
    """The formatted position, and Copy beside it.

    The text is selectable, so it can also be picked out by hand. The format comes from
    the campaign's ``coordinate_format`` setting.
    """

    def __init__(
        self,
        position: Point,
        settings: Any,
        parent: Optional[QWidget] = None,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self.text = format_for(settings, position)

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

        copy = QPushButton("" if compact else "Copy")
        copy.setProperty("style", "btn-small")
        copy.setToolTip("Copy these coordinates to the clipboard")
        if compact:
            # A row has no room for a word, and the glyph is the one the map uses.
            # Styled here rather than left to the app sheet, whose grey gradient
            # disappears into a dark card.
            copy.setFixedSize(22, 22)
            copy.setCursor(Qt.CursorShape.PointingHandCursor)
            copy.setIcon(QIcon(_copy_icon()))
            copy.setStyleSheet(
                "QPushButton { background: #1B2732;"
                " border: 1px solid #2C3A47; border-radius: 3px; }"
                "QPushButton:hover { background: #24323F; }"
            )
        else:
            copy.setMaximumWidth(60)
        copy.clicked.connect(self.copy)
        layout.addWidget(copy)
        if not compact:
            layout.addStretch()

        self.setLayout(layout)

    def copy(self) -> None:  # noqa: D401
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text)


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
