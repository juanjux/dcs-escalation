"""The line at the bottom of a point's window when the point is the objective of an
open High Command order, leading to the order."""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from game.highcommand.orders import Order, tier_name
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.pilot.common import chip, label

LINE_HEIGHT = 44
COUNTS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def orders_at_ground_object(game: Any, name: str) -> list[Order]:
    return [
        order
        for order in game.high_command.orders
        if order.task is None and order.objective == name
    ]


def orders_at_base(game: Any, name: str) -> list[Order]:
    return [
        order
        for order in game.high_command.orders
        if order.task is not None and order.base == name
    ]


class Ring(QWidget):
    """The map marker's ring, small."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(12, 12)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(ink.ORANGE), 2))
        painter.drawEllipse(1, 1, 10, 10)
        painter.end()


class Link(QLabel):
    def __init__(self, text: str, on_click: Callable[[], None]) -> None:
        super().__init__(text)
        self.on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"font-size: 13px; color: {ink.ORANGE}; background: transparent;"
            " border: none;"
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_click()


class ObjectiveLine(QFrame):
    """The line saying this point is the objective of a High Command order, and a
    way to it.

    With one order the whole line opens it. A base asked for two things at once has a
    link per order.
    """

    def __init__(
        self,
        orders: Sequence[Order],
        turn: int,
        count: int,
        open_order: Callable[[str], None],
        base: bool = False,
    ) -> None:
        super().__init__()
        self.orders = list(orders)
        self.open_order = open_order
        self.setFixedHeight(LINE_HEIGHT)
        self.setObjectName("hcObjectiveLine")
        self.setStyleSheet(
            f"#hcObjectiveLine {{ background: {ink.LAST_TURN_FILL};"
            f" border: 1px solid {ink.POINT_LINE_BORDER};"
            f" border-left: 3px solid {ink.ORANGE}; border-radius: 3px; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)
        row.addWidget(Ring())
        what = "base" if base else "point"
        if len(self.orders) == 1:
            said = f"This {what} is the objective of a High Command order"
        else:
            number = COUNTS.get(len(self.orders), str(len(self.orders)))
            said = f"This {what} is the objective of {number} High Command orders"
        row.addWidget(label(said, 13, ink.TITLE))
        row.addStretch()
        if len(self.orders) == 1:
            self._one(row, self.orders[0], turn, count)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self._each(row, turn)
        self.setLayout(row)

    def _one(self, row: QHBoxLayout, order: Order, turn: int, count: int) -> None:
        left = order.turns_left(turn)
        prize = order.prize
        kind = "ticket" if prize is not None and prize.ticket else "instant"
        tier = tier_name(order.tier, count)
        if left <= 1:
            row.addWidget(label(f"{tier} ·", 12, ink.SOFT))
            row.addWidget(chip("LAST TURN", ink.ON_ORANGE, ink.ORANGE))
            row.addWidget(label(f"· {kind}", 12, ink.SOFT))
        else:
            row.addWidget(label(f"{tier} · {left} turns left · {kind}", 12, ink.SOFT))
        row.addWidget(Link("Open order ›", lambda: self.open_order(order.objective)))

    def _each(self, row: QHBoxLayout, turn: int) -> None:
        for index, order in enumerate(self.orders):
            if index:
                divider = QFrame()
                divider.setFixedSize(1, 14)
                divider.setStyleSheet(
                    f"background: {ink.POINT_LINE_BORDER}; border: none;"
                )
                row.addWidget(divider)
            name = order.task.value if order.task is not None else order.objective
            row.addWidget(Link(f"{name} ›", partial(self.open_order, order.objective)))
            left = order.turns_left(turn)
            if left <= 1:
                row.addWidget(chip("LAST TURN", ink.ON_ORANGE, ink.ORANGE))
            else:
                row.addWidget(label(f"{left} turns", 12, ink.QUIET))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and len(self.orders) == 1:
            self.open_order(self.orders[0].objective)


def objective_line(
    game: Any,
    orders: Sequence[Order],
    open_order: Callable[[str], None],
    base: bool = False,
) -> Optional[ObjectiveLine]:
    """The line for these orders, or None when there are none or the High Command
    is off."""
    if not orders or not game.settings.high_command_enabled:
        return None
    return ObjectiveLine(
        orders, game.turn, game.settings.high_command_orders, open_order, base
    )
