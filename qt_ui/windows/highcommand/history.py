"""The History tab: the orders that closed and the tickets spent, newest first."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from game.highcommand.orders import SPENT, HistoryEntry, Outcome
from qt_ui.widgets.cards import card
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.rows import (
    chip_font,
    draw,
    draw_chip,
    elide,
    font,
    mono_font,
)
from qt_ui.windows.pilot.common import label

HISTORY_ROW = 40
#: Each outcome's chip, as (fill, text).
CHIPS = {
    Outcome.ACHIEVED.value: (ink.INSTANT_FILL, ink.INSTANT),
    Outcome.EXPIRED.value: ("#1D2731", ink.QUIET),
    Outcome.GONE.value: ("#1D2731", ink.MUTED),
    SPENT: (ink.TICKET_FILL, ink.ORANGE),
}

ModelIndex = QModelIndex | QPersistentModelIndex


class HistoryModel(QAbstractListModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.entries: list[HistoryEntry] = []

    def set_entries(self, entries: Sequence[HistoryEntry]) -> None:
        self.beginResetModel()
        self.entries = list(entries)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.line
        return None


class HistoryDelegate(QStyledItemDelegate):
    """The turn, what closed or was spent, what it gave, and the outcome."""

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        return QSize(option.rect.width(), HISTORY_ROW)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex
    ) -> None:
        entry = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, HistoryEntry):
            return
        rect: QRect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor(ink.CARD))
        painter.setPen(QColor(ink.DIVIDER))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        baseline = rect.top() + 25
        x = draw(
            painter,
            rect.left() + 14,
            baseline,
            f"T{entry.turn}",
            mono_font(12),
            ink.MUTED,
        )
        name = font(13, QFont.Weight.DemiBold)
        x = draw(painter, x + 14, baseline, entry.name, name, ink.TITLE)

        word = entry.outcome.upper()
        fill, colour = CHIPS.get(entry.outcome, ("#1D2731", ink.MUTED))
        chip_width = QFontMetrics(chip_font()).horizontalAdvance(word) + 12
        right = rect.right() - 14
        draw_chip(painter, right - chip_width, rect.top() + 12, word, fill, colour)

        body = font(12)
        room = right - chip_width - 12 - (x + 12)
        draw(painter, x + 12, baseline, elide(body, entry.line, room), body, ink.QUIET)
        painter.restore()


class HistoryPage(QWidget):
    """What the High Command closed and gave, newest first."""

    def __init__(self) -> None:
        super().__init__()
        self.model = HistoryModel(self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(HistoryDelegate(self.view))
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet(
            f"QListView {{ background: {ink.CARD}; border: none; outline: none; }}"
        )
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.view)
        self.list = card()
        self.list.setLayout(column)

        self.empty = label(
            "Nothing yet. An order that closes, or a ticket spent, is listed here.",
            12.5,
            ink.QUIET,
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 0, 14, 14)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.empty, 1)
        self.setLayout(layout)

    def show_history(self, entries: Sequence[HistoryEntry]) -> None:
        newest_first = list(reversed(entries))
        self.model.set_entries(newest_first)
        self.list.setVisible(bool(newest_first))
        self.empty.setVisible(not newest_first)
