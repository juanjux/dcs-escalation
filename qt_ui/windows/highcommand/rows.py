"""The order list, drawn by a delegate: tier, objective, what is asked, the prize and
the turns left, with the order in its last turn filled orange."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from qt_ui.widgets.controls import mono
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.model import OrderView

ORDER_ROW = 72
LEFT = 14
RIGHT = 14
#: What the asked line and the prize line leave free on the right, for the turns;
#: the prize line leaves more beside the LAST TURN chip.
TURNS_ROOM = 70
LAST_TURN_ROOM = 104

ModelIndex = QModelIndex | QPersistentModelIndex


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    face = QFont("Segoe UI")
    face.setPixelSize(int(round(size)))
    face.setWeight(weight)
    return face


def mono_font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    face = mono(size)
    face.setWeight(weight)
    return face


def chip_font() -> QFont:
    face = font(9.5, QFont.Weight.Bold)
    face.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    return face


def draw(
    painter: QPainter, x: int, baseline: int, text: str, face: QFont, colour: str
) -> int:
    """Write one run and return where the next one starts."""
    painter.setFont(face)
    painter.setPen(QColor(colour))
    painter.drawText(QPoint(x, baseline), text)
    return x + QFontMetrics(face).horizontalAdvance(text)


def elide(face: QFont, text: str, room: int) -> str:
    if room <= 0:
        return ""
    return QFontMetrics(face).elidedText(text, Qt.TextElideMode.ElideRight, room)


def draw_chip(
    painter: QPainter,
    x: int,
    top: int,
    text: str,
    fill: str,
    colour: str,
    height: int = 16,
    face: Optional[QFont] = None,
) -> int:
    """A filled chip with its text centred; returns where it ends."""
    face = face or chip_font()
    width = QFontMetrics(face).horizontalAdvance(text) + 12
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawRoundedRect(QRect(x, top, width, height), 3, 3)
    painter.setFont(face)
    painter.setPen(QColor(colour))
    painter.drawText(QRect(x, top, width, height), Qt.AlignmentFlag.AlignCenter, text)
    return x + width


class OrdersModel(QAbstractListModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.orders: list[OrderView] = []

    def set_orders(self, orders: Sequence[OrderView]) -> None:
        self.beginResetModel()
        self.orders = list(orders)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.orders)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.orders):
            return None
        order = self.orders[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return order
        if role == Qt.ItemDataRole.DisplayRole:
            return order.name
        return None

    def at(self, index: ModelIndex) -> Optional[OrderView]:
        if not index.isValid() or not 0 <= index.row() < len(self.orders):
            return None
        return self.orders[index.row()]

    def row_of(self, objective: str) -> Optional[int]:
        for row, order in enumerate(self.orders):
            if order.order.objective == objective:
                return row
        return None


class OrderDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        return QSize(option.rect.width(), ORDER_ROW)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex
    ) -> None:
        order = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(order, OrderView):
            return
        rect: QRect = option.rect
        state = option.state
        selected = bool(state & QStyle.StateFlag.State_Selected)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected:
            background, bar = ink.SELECTED, ink.SELECTED_BAR
        elif order.last_turn:
            background, bar = ink.LAST_TURN_FILL, ink.ORANGE
        else:
            background, bar = (ink.HOVER if hovered else ink.CARD), None
        painter.fillRect(rect, QColor(background))
        if bar is not None:
            painter.fillRect(
                QRect(rect.left(), rect.top(), 3, rect.height()), QColor(bar)
            )
        painter.setPen(QColor(ink.DIVIDER))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        self._first_line(painter, rect, order)
        text_room = rect.width() - LEFT - TURNS_ROOM
        face = font(12)
        draw(
            painter,
            rect.left() + LEFT,
            rect.top() + 42,
            elide(face, order.asked, text_room),
            face,
            ink.BODY,
        )
        prize_room = (
            rect.width() - LEFT - (LAST_TURN_ROOM if order.last_turn else TURNS_ROOM)
        )
        self._prize(painter, rect, order, prize_room)
        self._turns(painter, rect, order)
        painter.restore()

    @staticmethod
    def _first_line(painter: QPainter, rect: QRect, order: OrderView) -> None:
        fill, colour = ink.TIERS[order.tier_colour]
        face = chip_font() if "/" not in order.tier_chip else mono_font(10)
        x = draw_chip(
            painter,
            rect.left() + LEFT,
            rect.top() + 8,
            order.tier_chip,
            fill,
            colour,
            face=face,
        )
        x = draw(
            painter,
            x + 8,
            rect.top() + 22,
            order.name,
            font(14, QFont.Weight.DemiBold),
            ink.TITLE,
        )
        where = (
            order.kind
            if not order.base or order.order.task
            else (f"{order.kind} · {order.base}")
        )
        face = font(11.5)
        room = rect.right() - RIGHT - TURNS_ROOM - (x + 8)
        draw(painter, x + 8, rect.top() + 22, elide(face, where, room), face, ink.MUTED)

    @staticmethod
    def _prize(painter: QPainter, rect: QRect, order: OrderView, room: int) -> None:
        label = "TICKET" if order.ticket else "INSTANT"
        colour = ink.ORANGE if order.ticket else ink.INSTANT
        x = draw(
            painter, rect.left() + LEFT, rect.top() + 60, label, chip_font(), colour
        )
        face = font(11.5)
        left = x + 6
        draw(
            painter,
            left,
            rect.top() + 60,
            elide(face, order.prize_line, rect.left() + LEFT + room - left),
            face,
            ink.QUIET,
        )

    @staticmethod
    def _turns(painter: QPainter, rect: QRect, order: OrderView) -> None:
        right = rect.right() - RIGHT
        number = str(order.turns_left)
        face = mono_font(22, QFont.Weight.DemiBold)
        width = QFontMetrics(face).horizontalAdvance(number)
        draw(
            painter,
            right - width,
            rect.top() + 36,
            number,
            face,
            ink.ORANGE if order.last_turn else ink.BODY,
        )
        if order.last_turn:
            chip = "LAST TURN"
            chip_width = QFontMetrics(chip_font()).horizontalAdvance(chip) + 12
            draw_chip(
                painter,
                right - chip_width,
                rect.top() + 44,
                chip,
                ink.ORANGE,
                ink.ON_ORANGE,
            )
            return
        face = font(10.5)
        word = "turns"
        width = QFontMetrics(face).horizontalAdvance(word)
        draw(painter, right - width, rect.top() + 54, word, face, ink.MUTED)
