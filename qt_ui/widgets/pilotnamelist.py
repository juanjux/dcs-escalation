"""Name-library rows in the Air Wing's card and selection palette."""

from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from qt_ui.delegates import painter_context
from qt_ui.widgets.cards import CARD_BG, CARD_BORDER
from qt_ui.windows.airwingconfig.common import (
    ACCENT,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

DETAIL_ROLE = int(Qt.ItemDataRole.UserRole) + 1
ListKind = Literal["categories", "names", "pilots"]
SELECTED = "#1E3A52"
HOVERED = "#1A2A38"


class NameRowDelegate(QStyledItemDelegate):
    def __init__(self, kind: ListKind, parent: QListWidget) -> None:
        super().__init__(parent)
        self.kind = kind

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(100, 36 if self.kind == "names" else 52)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        with painter_context(painter):
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
            rect = option.rect
            painter.fillRect(
                rect, QColor(SELECTED if selected else HOVERED if hovered else CARD_BG)
            )
            painter.setPen(QColor(CARD_BORDER))
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            if selected:
                painter.fillRect(
                    QRect(rect.x(), rect.y(), 3, rect.height()), QColor(ACCENT)
                )
            numbered = self.kind != "categories"
            left = rect.x() + (42 if numbered else 14)
            font = QFont(option.font)
            font.setPixelSize(13)
            font.setWeight(
                QFont.Weight.Normal if self.kind == "names" else QFont.Weight.DemiBold
            )
            painter.setFont(font)
            painter.setPen(QColor(TEXT_PRIMARY if selected else TEXT_BASE))
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            width = max(0, rect.right() - left - (26 if self.kind == "names" else 12))
            title = QRect(left, rect.y(), width, rect.height())
            if self.kind != "names":
                title.setY(rect.y() + 7)
                title.setHeight(20)
            painter.drawText(
                title,
                Qt.AlignmentFlag.AlignVCenter,
                painter.fontMetrics().elidedText(
                    text, Qt.TextElideMode.ElideRight, width
                ),
            )
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.setPen(QColor(TEXT_SECONDARY if selected else TEXT_LABEL))
            if numbered:
                ordinal = QRect(rect.x() + 8, rect.y(), 24, rect.height())
                painter.drawText(
                    ordinal,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    f"{index.row() + 1:02}",
                )
            if self.kind != "names":
                detail = str(index.data(DETAIL_ROLE) or "")
                painter.drawText(
                    QRect(left, rect.y() + 28, width, 17),
                    Qt.AlignmentFlag.AlignVCenter,
                    painter.fontMetrics().elidedText(
                        detail, Qt.TextElideMode.ElideRight, width
                    ),
                )
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(ACCENT if selected else TEXT_LABEL))
                for dx in (0, 4):
                    for dy in (-4, 0, 4):
                        painter.drawEllipse(
                            rect.right() - 16 + dx, rect.center().y() + dy, 2, 2
                        )


class StyledNameList(QListWidget):
    def __init__(self, kind: ListKind, empty_text: str) -> None:
        super().__init__()
        self.empty_text = empty_text
        self.setItemDelegate(NameRowDelegate(kind, self))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setStyleSheet(
            f"QListWidget {{ background: {CARD_BG}; border: none; outline: none; }}"
        )
        self.verticalScrollBar().setStyleSheet(
            f"QScrollBar:vertical {{ background: {CARD_BG}; width: 12px; margin: 0; }}"
            "QScrollBar::handle:vertical { background: #435466; min-height: 30px; border-radius: 3px; }"
            "QScrollBar::handle:vertical:hover { background: #6E93B0; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.count():
            painter = QPainter(self.viewport())
            font = QFont(self.font())
            font.setPixelSize(12)
            painter.setFont(font)
            painter.setPen(QColor(TEXT_LABEL))
            painter.drawText(
                self.viewport().rect().adjusted(18, 18, -18, -18),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.empty_text,
            )
            painter.end()
