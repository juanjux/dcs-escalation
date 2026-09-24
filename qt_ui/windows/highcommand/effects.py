"""The Active Effects tab: the prizes that last some turns, and when each ends."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from qt_ui.widgets.cards import card, make_transparent
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.loans import TimedRow
from qt_ui.windows.highcommand.model import EffectView
from qt_ui.windows.pilot.common import label


class EffectsPage(QWidget):
    """The effects running, the soonest to end first."""

    def __init__(self) -> None:
        super().__init__()
        heading = QHBoxLayout()
        heading.setContentsMargins(14, 8, 14, 8)
        for text in ("Effect", "Turns left"):
            caption = label(text.upper(), 10.5, ink.CAPTION, bold=True)
            caption.setStyleSheet(caption.styleSheet() + " letter-spacing: 1px;")
            heading.addWidget(caption)
            if text == "Effect":
                heading.addStretch()
        head = QWidget()
        head.setLayout(heading)
        make_transparent(head)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {ink.DIVIDER}; border: none;")

        self.rows = QVBoxLayout()
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(head)
        column.addWidget(rule)
        column.addLayout(self.rows)
        self.list = card()
        self.list.setLayout(column)

        self.empty = label(
            "No effects active. A prize that lasts some turns, such as a discount or"
            " an experience bonus, is listed here while it lasts.",
            12.5,
            ink.QUIET,
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 0, 14, 14)
        layout.addWidget(self.list)
        layout.addWidget(self.empty, 1)
        layout.addStretch()
        self.setLayout(layout)

    def show_effects(self, effects: Sequence[EffectView]) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for effect in effects:
            self.rows.addWidget(
                TimedRow(
                    effect.label,
                    f"from {effect.earned_by}",
                    effect.turns_left,
                    effect.until,
                )
            )
        self.list.setVisible(bool(effects))
        self.empty.setVisible(not effects)
