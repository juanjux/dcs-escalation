"""A position with a button that copies it to the clipboard."""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
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
        self, position: Point, settings: Any, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.text = format_for(settings, position)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(self.text)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setProperty("style", "small")
        layout.addWidget(label)

        copy = QPushButton("Copy")
        copy.setProperty("style", "btn-small")
        copy.setToolTip("Copy these coordinates to the clipboard")
        copy.setMaximumWidth(60)
        copy.clicked.connect(self.copy)
        layout.addWidget(copy)
        layout.addStretch()

        self.setLayout(layout)

    def copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text)
