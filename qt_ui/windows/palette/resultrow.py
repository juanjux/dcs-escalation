"""A result, painted rather than built.

Thirty results is a hundred and twenty widgets if each row is a box of labels, and
they are thrown away and made again on every keystroke: measured at twenty-two
milliseconds a letter against a campaign of a thousand entries, where the search
itself took one. Painted, only the rows on screen cost anything, and the same
delegate draws all of them.

This is how the pilot list and the Air Wing list are already drawn.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from game.search.index import Hit
from game.search.providers import (
    ACTION,
    BASE,
    FLIGHT,
    OBJECTIVE,
    PILOT,
    SETTING,
    SQUADRON,
)

#: The role the hit itself is stored under.
HitRole = Qt.ItemDataRole.UserRole + 1

ROW_HEIGHT = 44
CHIP_X = 14
CHIP_WIDTH = 84
TEXT_X = CHIP_X + CHIP_WIDTH + 10
RIGHT_MARGIN = 14

#: Baselines measured from the top of the row.
LINE_1 = 19
LINE_2 = 34

SELECTED_FILL = QColor("#1E3A52")
HOVER_FILL = QColor("#1A2A38")
SEPARATOR = QColor("#1A2430")
LABEL = QColor("#F2F7FA")
DETAIL = QColor("#6B7A87")
NOTE = QColor("#4F6070")

#: What each kind is called in its chip, and the colour of that chip.
KINDS: dict[str, tuple[str, QColor]] = {
    ACTION: ("COMMAND", QColor("#8FC3F0")),
    SETTING: ("SETTING", QColor("#A9C99A")),
    BASE: ("BASE", QColor("#86C39A")),
    OBJECTIVE: ("OBJECTIVE", QColor("#E0A86B")),
    SQUADRON: ("SQUADRON", QColor("#D270E1")),
    FLIGHT: ("FLIGHT", QColor("#70E186")),
    PILOT: ("PILOT", QColor("#B7C6D2")),
}


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


class ResultDelegate(QStyledItemDelegate):
    """Paints one result: its kind, what it is called, and where it lives."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        hit: Optional[Hit] = index.data(HitRole)
        if hit is None:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, SELECTED_FILL)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, HOVER_FILL)
        painter.fillRect(QRect(rect.left(), rect.bottom(), rect.width(), 1), SEPARATOR)

        entry = hit.entry
        name, colour = KINDS.get(entry.follow.kind, (entry.follow.kind.upper(), DETAIL))

        chip_font = _font(10, QFont.Weight.Bold)
        painter.setFont(chip_font)
        painter.setPen(colour)
        painter.drawText(
            QRect(rect.left() + CHIP_X, rect.top(), CHIP_WIDTH, ROW_HEIGHT),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

        right = rect.right() - RIGHT_MARGIN
        if entry.note:
            note_font = _font(11)
            painter.setFont(note_font)
            painter.setPen(NOTE)
            width = QFontMetrics(note_font).horizontalAdvance(entry.note)
            painter.drawText(
                QRect(right - width, rect.top(), width, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                entry.note,
            )
            right -= width + 12

        left = rect.left() + TEXT_X
        available = max(0, right - left)

        label_font = _font(13, QFont.Weight.DemiBold)
        painter.setFont(label_font)
        painter.setPen(LABEL)
        painter.drawText(
            left,
            rect.top() + LINE_1,
            QFontMetrics(label_font).elidedText(
                entry.label, Qt.TextElideMode.ElideRight, available
            ),
        )

        if entry.detail:
            detail_font = _font(11)
            painter.setFont(detail_font)
            painter.setPen(DETAIL)
            painter.drawText(
                left,
                rect.top() + LINE_2,
                QFontMetrics(detail_font).elidedText(
                    entry.detail, Qt.TextElideMode.ElideRight, available
                ),
            )

        painter.restore()
