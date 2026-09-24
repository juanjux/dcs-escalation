"""The High Command window: the requests open, what each asks and pays.

Non-modal and one of a kind: "Show on map" moves the main window's map and this
window stays where it is. Orders cannot be declined or deleted, so nothing here
offers to.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from qt_ui.widgets.cards import card, make_transparent
from qt_ui.widgets.controls import button, mono
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.groundobject.header import KIND_FILL
from game.theater.player import Player
from qt_ui.windows.highcommand import model as data
from qt_ui.windows.intel.dialog import SideSwitch
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.model import OrderView
from qt_ui.windows.highcommand.model import TicketView
from qt_ui.windows.highcommand.rows import OrderDelegate, OrdersModel
from qt_ui.windows.highcommand.effects import EffectsPage
from qt_ui.windows.highcommand.history import HistoryPage
from qt_ui.windows.highcommand.loans import LoansPage
from qt_ui.windows.highcommand.tickets import TicketsPage
from qt_ui.windows.pilot.common import ACCENT, RED, chip, label

LIST_WIDTH = 420


def _rule(vertical: bool = False) -> QFrame:
    line = QFrame()
    if vertical:
        line.setFixedSize(1, 28)
    else:
        line.setFixedHeight(1)
    line.setStyleSheet(f"background: {ink.DIVIDER}; border: none;")
    return line


def _caption(text: str) -> QLabel:
    widget = label(text.upper(), 10.5, ink.CAPTION, bold=True)
    widget.setStyleSheet(widget.styleSheet() + " letter-spacing: 1px;")
    return widget


def _wrapped(text: str, size: float, colour: str, italic: bool = False) -> QLabel:
    widget = label(text, size, colour)
    widget.setWordWrap(True)
    if italic:
        widget.setStyleSheet(widget.styleSheet() + " font-style: italic;")
    return widget


class Headline(QWidget):
    """Orders open, how many are in their last turn, tickets and loans."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(58)
        self.setObjectName("hcHeadline")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.paint_side(own=True)
        row = QHBoxLayout()
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)
        self.orders = self._figure(24)
        row.addLayout(self._pair(self.orders, "requests open"))
        self.last_turn = chip("", ink.ON_ORANGE, ink.ORANGE)
        row.addWidget(self.last_turn)
        row.addSpacing(8)
        row.addWidget(_rule(vertical=True))
        row.addSpacing(8)
        self.tickets = self._figure(18)
        row.addLayout(self._pair(self.tickets, "tickets to spend"))
        row.addSpacing(8)
        row.addWidget(_rule(vertical=True))
        row.addSpacing(8)
        self.loans = self._figure(18)
        row.addLayout(self._pair(self.loans, "on loan"))
        row.addStretch()
        self.note = label("", 12, ink.MUTED)
        row.addWidget(self.note)
        self.row = row
        self.setLayout(row)

    def paint_side(self, own: bool) -> None:
        window = ink.WINDOW if own else ink.ENEMY_WINDOW
        band = ink.ORANGE if own else ink.ENEMY_BAND
        self.setStyleSheet(
            f"#hcHeadline {{ background: {window}; border-left: 4px solid {band};"
            f" border-bottom: 1px solid {ink.DIVIDER}; }}"
        )

    @staticmethod
    def _figure(size: int) -> QLabel:
        widget = label("0", size, ink.TITLE, bold=True)
        widget.setFont(mono(size))
        return widget

    @staticmethod
    def _pair(figure: QLabel, words: str) -> QHBoxLayout:
        pair = QHBoxLayout()
        pair.setSpacing(8)
        pair.addWidget(figure, 0, Qt.AlignmentFlag.AlignBaseline)
        pair.addWidget(label(words, 12, ink.MUTED), 0, Qt.AlignmentFlag.AlignBaseline)
        return pair

    def show_figures(self, figures: data.Headline) -> None:
        self.orders.setText(str(figures.orders))
        self.last_turn.setText(f"{figures.last_turn} IN ITS LAST TURN")
        self.last_turn.setVisible(figures.last_turn > 0)
        self.tickets.setText(str(figures.tickets))
        self.loans.setText(str(figures.loans))
        self.note.setText(
            f"Turn {figures.turn} · requests are optional and not mandatory"
        )


class Tab(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class TabStrip(QWidget):
    """The tabs, each with its count; the Orders count turns orange when an order is
    in its last turn."""

    changed = Signal(int)

    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.names = names
        self.counts: list[Optional[int]] = [None] * len(names)
        self.warm: list[bool] = [False] * len(names)
        self.current = 0
        row = QHBoxLayout()
        row.setContentsMargins(14, 10, 14, 0)
        row.setSpacing(2)
        self.tabs: list[Tab] = []
        for index in range(len(names)):
            tab = Tab()
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setTextFormat(Qt.TextFormat.RichText)
            tab.clicked.connect(lambda i=index: self.select(i))
            self.tabs.append(tab)
            row.addWidget(tab)
        row.addStretch()
        self.setLayout(row)
        make_transparent(self)
        self._paint()

    def set_count(self, index: int, count: Optional[int], warm: bool = False) -> None:
        self.counts[index] = count
        self.warm[index] = warm
        self._paint()

    def select(self, index: int) -> None:
        if index != self.current:
            self.current = index
            self._paint()
            self.changed.emit(index)

    def _paint(self) -> None:
        for index, tab in enumerate(self.tabs):
            chosen = index == self.current
            count = self.counts[index]
            number = ""
            if count is not None:
                colour = ink.ORANGE if self.warm[index] else ink.MUTED
                number = f"&nbsp;&nbsp;<span style='color:{colour}'>{count}</span>"
            tab.setText(f"{self.names[index]}{number}")
            tab.setStyleSheet(
                f"font-size: 13px; padding: 6px 16px;"
                f" color: {ink.TITLE if chosen else ink.SOFT};"
                f" font-weight: {'600' if chosen else 'normal'};"
                + (
                    f" background: {ink.CARD}; border: 1px solid {ink.CARD_BORDER};"
                    " border-bottom: none;"
                    if chosen
                    else " background: transparent; border: none;"
                )
            )


class Pips(QWidget):
    """Five squares, filled up to a figure from 1 to 5."""

    def __init__(self) -> None:
        super().__init__()
        self.value = 0
        self.setFixedSize(5 * 9 + 4 * 3, 9)

    def set_value(self, value: int) -> None:
        self.value = value
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        for index in range(5):
            colour = ink.BODY if index < self.value else ink.PIP_OFF
            painter.fillRect(QRect(index * 12, 0, 9, 9), QColor(colour))
        painter.end()


class Figures(QWidget):
    """Difficulty, importance, score and turns left, side by side."""

    def __init__(self) -> None:
        super().__init__()
        row = QHBoxLayout()
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(18)
        self.difficulty, self.difficulty_pips = self._rated(row, "Difficulty")
        self.importance, self.importance_pips = self._rated(row, "Importance")
        self.score, self.score_note = self._cell(row, "Score")
        self.turns, self.turns_note = self._cell(row, "Turns left")
        self.setLayout(row)

    def _column(self, row: QHBoxLayout, name: str) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(_caption(name))
        row.addLayout(column, 1)
        return column

    def _rated(self, row: QHBoxLayout, name: str) -> tuple[QLabel, Pips]:
        column = self._column(row, name)
        line = QHBoxLayout()
        line.setSpacing(8)
        figure = label("", 18, ink.TITLE, bold=True)
        figure.setFont(mono(18))
        pips = Pips()
        line.addWidget(figure)
        line.addWidget(pips, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addStretch()
        column.addLayout(line)
        return figure, pips

    def _cell(self, row: QHBoxLayout, name: str) -> tuple[QLabel, QLabel]:
        column = self._column(row, name)
        line = QHBoxLayout()
        line.setSpacing(6)
        figure = label("", 18, ink.TITLE, bold=True)
        figure.setFont(mono(18))
        note = label("", 11.5, ink.MUTED)
        line.addWidget(figure, 0, Qt.AlignmentFlag.AlignBaseline)
        line.addWidget(note, 0, Qt.AlignmentFlag.AlignBaseline)
        line.addStretch()
        column.addLayout(line)
        return figure, note

    def show_order(self, order: OrderView) -> None:
        self.difficulty.setText(str(order.difficulty))
        self.difficulty_pips.set_value(order.difficulty)
        self.importance.setText(str(order.importance))
        self.importance_pips.set_value(order.importance)
        self.score.setText(str(order.score))
        self.score_note.setText("/ 10")
        self.turns.setText(str(order.turns_left))
        self.turns.setStyleSheet(
            self.turns.styleSheet()
            + f" color: {ink.ORANGE if order.last_turn else ink.TITLE};"
        )
        self.turns_note.setText(
            f"of {order.lifetime} · last turn {order.last_open_turn}"
        )


def _boxed(inner: QWidget) -> QWidget:
    holder = card()
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(inner)
    holder.setLayout(layout)
    return holder


class Detail(QWidget):
    """Everything about the selected order."""

    def __init__(self, show_on_map: Callable[[], None]) -> None:
        super().__init__()
        make_transparent(self)
        column = QVBoxLayout()
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.name = label("", 24, ink.TITLE, bold=True)
        head.addWidget(self.name)
        self.kind = chip("", RED, KIND_FILL["RED"])
        head.addWidget(self.kind, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch()
        self.map_button = button("Show on map  ↗", "primary", show_on_map)
        self.map_button.setFixedHeight(28)
        head.addWidget(self.map_button, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(head)
        self.subtitle = label("", 12.5, ink.QUIET)
        column.addWidget(self.subtitle)

        column.addWidget(_caption("Why"))
        self.why = _wrapped("", 14, ink.BODY)
        column.addWidget(self.why)

        self.figures = Figures()
        column.addWidget(_boxed(self.figures))

        pair = QHBoxLayout()
        pair.setSpacing(12)
        self.taken_title = label("", 13, ink.TITLE, bold=True)
        self.taken_detail = _wrapped("", 11.5, ink.MUTED)
        pair.addLayout(
            self._titled("Taken when", self.taken_title, self.taken_detail), 1
        )
        self.prize = _wrapped("", 13, ink.BODY)
        self.prize_chip = chip("", ink.ORANGE, ink.TICKET_FILL)
        pair.addLayout(self._titled("Prize", self.prize, self.prize_chip), 1)
        column.addLayout(pair)

        lists = QHBoxLayout()
        lists.setSpacing(12)
        self.hard = _wrapped("", 12, ink.SOFT)
        lists.addLayout(self._listed("What makes it hard", self.hard), 1)
        self.worth_names = _wrapped("", 12, ink.SOFT)
        self.worth_values = _wrapped("", 12, ink.SOFT)
        self.worth_values.setFont(mono(12))
        self.worth_values.setAlignment(Qt.AlignmentFlag.AlignRight)
        worth = QHBoxLayout()
        worth.addWidget(self.worth_names, 1)
        worth.addWidget(self.worth_values)
        worth_column = QVBoxLayout()
        worth_column.setSpacing(6)
        worth_column.addWidget(_caption("Worth"))
        worth_column.addLayout(worth)
        worth_column.addStretch()
        lists.addLayout(worth_column, 1)
        column.addLayout(lists)
        column.addStretch()
        self.setLayout(column)

    @staticmethod
    def _titled(name: str, first: QWidget, second: QWidget) -> QVBoxLayout:
        inner = QWidget()
        box = QVBoxLayout()
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(4)
        box.addWidget(first)
        box.addWidget(second, 0, Qt.AlignmentFlag.AlignLeft)
        inner.setLayout(box)
        make_transparent(inner)
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(_caption(name))
        column.addWidget(_boxed(inner), 1)
        return column

    @staticmethod
    def _listed(name: str, body: QLabel) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(6)
        column.addWidget(_caption(name))
        column.addWidget(body)
        column.addStretch()
        return column

    def show_order(self, order: OrderView) -> None:
        self.name.setText(order.name)
        self.kind.setText(f"{order.kind.upper()} · {order.owner}")
        ours = order.owner == "BLUE"
        self.kind.setStyleSheet(
            f"background: {KIND_FILL['BLUE' if ours else 'RED']};"
            f" color: {ACCENT if ours else RED}; border: none; border-radius: 3px;"
            " padding: 2px 7px; font-size: 10px; font-weight: bold;"
            " letter-spacing: 0.8px;"
        )
        where = [order.base] if order.order.task is None and order.base else []
        self.subtitle.setText(
            " · ".join(
                [*where, f"requested turn {order.order.ordered_on}", order.tier_words]
            )
        )
        self.map_button.setEnabled(order.position is not None)
        if order.comical:
            self.why.setText(f"“{order.justification}”")
            self.why.setStyleSheet(
                f"font-size: 14px; color: {ink.SOFT}; background: transparent;"
                " border: none; font-style: italic;"
            )
        else:
            self.why.setText(order.justification)
            self.why.setStyleSheet(
                f"font-size: 14px; color: {ink.BODY}; background: transparent;"
                " border: none;"
            )
        self.figures.show_order(order)
        self.taken_title.setText(order.taken_title)
        self.taken_detail.setText(order.taken_detail)
        self.prize.setText(order.prize_line)
        if order.ticket:
            self.prize_chip.setText("TICKET · KEPT TO SPEND LATER")
            colour, fill = ink.ORANGE, ink.TICKET_FILL
        else:
            self.prize_chip.setText("INSTANT · GIVEN WHEN ACHIEVED")
            colour, fill = ink.INSTANT, ink.INSTANT_FILL
        self.prize_chip.setStyleSheet(
            f"background: {fill}; color: {colour}; border: none; border-radius: 3px;"
            " padding: 2px 7px; font-size: 10px; font-weight: bold;"
            " letter-spacing: 0.8px;"
        )
        self.hard.setText(
            "\n".join(f"· {hazard}" for hazard in order.hazards) or "Nothing known."
        )
        self.worth_names.setText("\n".join(name for name, _ in order.worth))
        self.worth_values.setText("\n".join(value for _, value in order.worth))


class Message(QWidget):
    """What a pane says when it has nothing to list."""

    def __init__(self) -> None:
        super().__init__()
        make_transparent(self)
        column = QVBoxLayout()
        column.setContentsMargins(24, 24, 24, 24)
        column.setSpacing(6)
        column.addStretch()
        self.title = label("", 15, ink.TITLE, bold=True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = _wrapped("", 12.5, ink.QUIET)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.title)
        column.addWidget(self.text)
        column.addStretch()
        self.setLayout(column)

    def say(self, title: str, text: str) -> None:
        self.title.setText(title)
        self.text.setText(text)


class OrdersPage(QWidget):
    """The order list and the selected order in detail."""

    def __init__(self, show_on_map: Callable[[OrderView], None]) -> None:
        super().__init__()
        self.model = OrdersModel(self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(OrderDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet(
            f"QListView {{ background: {ink.CARD}; border: none; outline: none; }}"
        )

        heading = QHBoxLayout()
        heading.setContentsMargins(14, 8, 14, 8)
        heading.addWidget(_caption("Request · highest tier first"))
        heading.addStretch()
        heading.addWidget(_caption("Turns left"))
        head = QWidget()
        head.setLayout(heading)
        make_transparent(head)
        footnote = _wrapped(
            "A new request replaces one that is achieved, runs out, or loses its"
            " objective — at the start of next turn, in the same tier.",
            11,
            ink.CAPTION,
        )
        footnote.setContentsMargins(14, 8, 14, 10)
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(0)
        left_column.addWidget(head)
        left_column.addWidget(_rule())
        left_column.addWidget(self.view, 1)
        left_column.addWidget(footnote)
        left = card()
        left.setLayout(left_column)
        left.setMinimumWidth(LIST_WIDTH)

        self.detail = Detail(lambda: self._show_on_map(show_on_map))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.detail)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([LIST_WIDTH, 660])
        self.splitter = splitter

        self.message = Message()
        self.stack = QStackedWidget()
        self.stack.addWidget(splitter)
        self.stack.addWidget(self.message)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 0, 14, 14)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.view.selectionModel().currentChanged.connect(
            lambda current, _previous: self._select(current)
        )

    def show_orders(
        self, orders: list[OrderView], enabled: bool, enemy_idle: bool = False
    ) -> None:
        chosen = self.selected
        self.model.set_orders(orders)
        if not orders:
            if enabled and enemy_idle:
                self.message.say(
                    "The enemy has no requests",
                    "The enemy's High Command makes requests only when GeneraLLM"
                    " plays it.",
                )
            elif enabled:
                self.message.say(
                    "No requests open this turn",
                    "The enemy has nothing left worth asking for. New requests"
                    " come at the start of a turn.",
                )
            else:
                self.message.say(
                    "The High Command is off",
                    "No requests are made. Tickets already earned can still be"
                    " spent.",
                )
            self.stack.setCurrentWidget(self.message)
            return
        self.stack.setCurrentWidget(self.splitter)
        row = self.model.row_of(chosen.order.objective) if chosen else None
        self.view.setCurrentIndex(self.model.index(row or 0, 0))

    def open_order(self, objective: str) -> bool:
        row = self.model.row_of(objective)
        if row is None:
            return False
        self.view.setCurrentIndex(self.model.index(row, 0))
        return True

    @property
    def selected(self) -> Optional[OrderView]:
        return self.model.at(self.view.currentIndex())

    def _select(self, index: QModelIndex) -> None:
        order = self.model.at(index)
        if order is not None:
            self.detail.show_order(order)

    def _show_on_map(self, show_on_map: Callable[[OrderView], None]) -> None:
        order = self.selected
        if order is not None:
            show_on_map(order)


class HighCommandWindow(QDialog):
    """The High Command's orders, one tab per kind of thing it keeps."""

    TABS = ["Requests", "Tickets", "On loan", "Active Effects", "History"]
    ORDERS, TICKETS, LOANS, EFFECTS, HISTORY = 0, 1, 2, 3, 4

    def __init__(self, game_model: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game_model = game_model
        #: Whose High Command the window shows: the player's, or the enemy's.
        self.side = Player.BLUE
        self.setWindowTitle("High Command")
        self.setMinimumSize(1100, 720)
        self.setWindowFlag(Qt.WindowType.Tool, True)

        self.headline = Headline()
        self.side_switch = SideSwitch(self.show_side)
        self.headline.row.addSpacing(12)
        self.headline.row.addWidget(self.side_switch)
        self.tabs = TabStrip(self.TABS)
        self.orders = OrdersPage(self.show_on_map)
        self.tickets = TicketsPage(self.spend, self.ticket_spent, self.show_place)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.orders)
        self.pages.addWidget(self.tickets)
        self.loans = LoansPage()
        self.pages.addWidget(self.loans)
        self.effects = EffectsPage()
        self.pages.addWidget(self.effects)
        self.history = HistoryPage()
        self.pages.addWidget(self.history)
        self.tabs.changed.connect(self.pages.setCurrentIndex)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.headline)
        layout.addWidget(self.tabs)
        body = QWidget()
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body.setObjectName("hcBody")
        self.body = body
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self.pages)
        body.setLayout(body_layout)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(body, 1)
        self.setLayout(layout)

        GameUpdateSignal.get_instance().gameupdated.connect(self._game_updated)
        self._paint_side()
        self.reload()

    def show_side(self, player: Player) -> None:
        """Show the player's High Command, or the enemy's."""
        self.side = player
        self._paint_side()
        self.reload()

    def _paint_side(self) -> None:
        own = self.side.is_blue
        window = ink.WINDOW if own else ink.ENEMY_WINDOW
        self.setStyleSheet(f"QDialog {{ background: {window}; }}")
        self.body.setStyleSheet(f"#hcBody {{ background: {window}; }}")
        self.headline.paint_side(own)
        self.side_switch.show_side(self.side)
        self.tickets.set_read_only(not own)

    @property
    def game(self) -> Any:
        return getattr(self.game_model, "game", None)

    def _game_updated(self, *_: Any) -> None:
        if self.isVisible():
            self.reload()

    def reload(self) -> None:
        game = self.game
        if game is None:
            return
        side = self.side
        figures = data.headline(game, side)
        self.headline.show_figures(figures)
        self.tabs.set_count(self.ORDERS, figures.orders, warm=figures.last_turn > 0)
        self.tabs.set_count(self.TICKETS, figures.tickets)
        self.orders.show_orders(
            data.order_views(game, side),
            game.settings.high_command_enabled,
            enemy_idle=side.is_red and not game.opfor_high_command_active,
        )
        self.tickets.show_tickets(game, data.ticket_views(game, side))
        self.tabs.set_count(self.LOANS, figures.loans)
        self.loans.show_loans(data.loan_views(game, side))
        effects = data.effect_views(game, side)
        self.tabs.set_count(self.EFFECTS, len(effects))
        self.effects.show_effects(effects)
        self.history.show_history(data.command_for(game, side).history)

    def open_order(self, objective: Optional[str]) -> None:
        """Show this request, on the Requests tab."""
        self.tabs.select(0)
        self.pages.setCurrentIndex(0)
        if objective is not None:
            self.orders.open_order(objective)

    def show_on_map(self, order: OrderView) -> None:
        """The map goes to the objective. This window stays where it is."""
        if order.position is not None:
            self._look_at(order.position)

    def show_place(self, position: Any) -> None:
        """The map goes to a ticket's option, or to what a spent ticket set up."""
        if position is not None:
            self._look_at(position)

    @staticmethod
    def _look_at(position: Any) -> None:
        """Move the map there, at the zoom the player left it at."""
        from game.server import EventStream
        from game.sim import GameUpdateEvents

        EventStream.put_nowait(GameUpdateEvents().look_at(position.latlng()))

    def spend(self, ticket: TicketView, picked: tuple[str, ...]) -> str:
        """Spend a ticket and say what it gave; CannotGive when it cannot be."""
        if not self.side.is_blue:
            raise ValueError("the enemy's tickets are GeneraLLM's to spend")
        return self.game.high_command.spend(self.game, ticket.ticket, picked)

    def ticket_spent(self, line: str) -> None:
        """What a ticket gave shows in the rest of the application too."""
        GameUpdateSignal.get_instance().updateGame(self.game)
        if not self.isVisible():
            self.reload()


def main_window() -> Optional[QWidget]:
    """The application's main window, to parent the High Command window on when it
    is opened from a window that has no parent of its own."""
    from PySide6.QtWidgets import QApplication

    return next(
        (
            widget
            for widget in QApplication.topLevelWidgets()
            if type(widget).__name__ == "QLiberationWindow"
        ),
        None,
    )


def open_high_command(
    game_model: Any, parent: Optional[QWidget], objective: Optional[str] = None
) -> HighCommandWindow:
    """The High Command window, on this order if one is named."""
    from qt_ui.dialogs import open_once

    window = open_once("high-command", lambda: HighCommandWindow(game_model, parent))
    window.open_order(objective)
    return window
