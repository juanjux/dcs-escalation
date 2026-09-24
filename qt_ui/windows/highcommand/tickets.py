"""The Tickets tab: the prizes kept to spend, and spending one in the pane beside the
list, a step at a time.

A ticket's steps come from its prize kind. A finished step collapses to one line with
Change; a step picked by itself shows done, with no Change; a step with nothing to
pick says so and leaves the ticket where it was. A refusal from the game keeps the
ticket too.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from game.highcommand.prizes import CannotGive, Choice, Step
from qt_ui.widgets.cards import card, make_transparent
from qt_ui.widgets.controls import button, style_button
from qt_ui.windows.highcommand import model as data
from qt_ui.windows.highcommand import palette as ink
from qt_ui.windows.highcommand.model import TicketView
from qt_ui.windows.highcommand.rows import chip_font, draw, elide, font
from qt_ui.windows.pilot.common import label

TICKET_ROW = 64
CHOICE_ROW = 36
#: How many choices a step shows before it scrolls.
SHOWN_CHOICES = 7
DISC = 18
#: The state words at the right of a ticket's row, and their colours.
STATE_INK = {data.READY: ink.INSTANT, data.NOT_NOW: ink.MUTED}
PICKS_INK = "#BEDCF6"
DIMMED = "#A9B7C3"
DONE = "#86C39A"
ACTIVE = "#8FC3F0"
BLOCKED = "#3A4B5C"
REFUSED = "#2A1E1D"
REFUSED_BAR = "#E08A7A"
GIVEN = "#1C2D25"

ModelIndex = QModelIndex | QPersistentModelIndex


class TicketsModel(QAbstractListModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.tickets: list[TicketView] = []

    def set_tickets(self, tickets: Sequence[TicketView]) -> None:
        self.beginResetModel()
        self.tickets = list(tickets)
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.tickets)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        ticket = self.at(index)
        if ticket is None:
            return None
        if role == Qt.ItemDataRole.UserRole:
            return ticket
        if role == Qt.ItemDataRole.DisplayRole:
            return ticket.line
        return None

    def at(self, index: ModelIndex) -> Optional[TicketView]:
        if not index.isValid() or not 0 <= index.row() < len(self.tickets):
            return None
        return self.tickets[index.row()]


class TicketDelegate(QStyledItemDelegate):
    """The prize line over two lines at most, who earned it, and its state."""

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        return QSize(option.rect.width(), TICKET_ROW)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex
    ) -> None:
        ticket = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(ticket, TicketView):
            return
        rect: QRect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(
            rect,
            QColor(ink.SELECTED if selected else ink.HOVER if hovered else ink.CARD),
        )
        if selected:
            painter.fillRect(
                QRect(rect.left(), rect.top(), 3, rect.height()),
                QColor(ink.SELECTED_BAR),
            )
        painter.setPen(QColor(ink.DIVIDER))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        state_face = chip_font()
        state_width = QFontMetrics(state_face).horizontalAdvance(ticket.state)
        state_ink = STATE_INK.get(ticket.state, PICKS_INK)
        draw(
            painter,
            rect.right() - 14 - state_width,
            rect.top() + 56,
            ticket.state,
            state_face,
            state_ink,
        )

        face = font(13)
        dimmed = ticket.state == data.NOT_NOW
        painter.setFont(face)
        painter.setPen(QColor(DIMMED if dimmed else ink.BODY))
        text_rect = QRect(rect.left() + 14, rect.top() + 6, rect.width() - 28, 36)
        metrics = QFontMetrics(face)
        text = _two_lines(metrics, ticket.line, text_rect.width())
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text
        )
        small = font(11)
        draw(
            painter,
            rect.left() + 14,
            rect.top() + 56,
            elide(small, ticket.earned, rect.width() - 40 - state_width),
            small,
            ink.MUTED,
        )
        painter.restore()


def _two_lines(metrics: QFontMetrics, text: str, width: int) -> str:
    """The text wrapped to two lines, the second elided."""
    words = text.split()
    first = ""
    while (
        words and metrics.horizontalAdvance((first + " " + words[0]).strip()) <= width
    ):
        first = (first + " " + words.pop(0)).strip()
    if not words:
        return first
    second = metrics.elidedText(" ".join(words), Qt.TextElideMode.ElideRight, width)
    return f"{first}\n{second}"


class Disc(QWidget):
    """A step's number in a circle: blue while asked, green when done, grey when it
    has nothing to pick from."""

    def __init__(self, number: int, colour: str, done: bool = False) -> None:
        super().__init__()
        self.number = number
        self.colour = colour
        self.done = done
        self.setFixedSize(DISC, DISC)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.colour))
        painter.drawEllipse(0, 0, DISC, DISC)
        painter.setPen(QColor(ink.ON_ORANGE))
        painter.setFont(font(10.5, QFont.Weight.Bold))
        painter.drawText(
            QRect(0, 0, DISC, DISC),
            Qt.AlignmentFlag.AlignCenter,
            "✓" if self.done else str(self.number),
        )
        painter.end()


class ChoiceRow(QWidget):
    """One option of a step: a radio circle, its label and its detail, and a button
    to see it on the map when it is a place."""

    picked = Signal(str)
    #: Where the option is, to show on the map.
    show_on_map = Signal(object)

    def __init__(self, choice: Choice) -> None:
        super().__init__()
        self.choice = choice
        self.hovered = False
        self.setFixedHeight(CHOICE_ROW)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(choice.detail)
        self.map_button: Optional[QPushButton] = None
        if choice.position is not None:
            self.map_button = button(
                "Show on map  ↗",
                "normal",
                lambda: self.show_on_map.emit(choice.position),
            )
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 10, 0)
            row.addStretch()
            row.addWidget(self.map_button)
            self.setLayout(row)

    def enterEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        self.hovered = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        self.hovered = False
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.choice.key)

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hovered:
            painter.fillRect(self.rect(), QColor(ink.HOVER))
        painter.setPen(QColor(ink.DIVIDER))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.setPen(QColor(ink.SOFT))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(14, 12, 12, 12)
        name = font(13, QFont.Weight.DemiBold)
        end = draw(painter, 36, 23, self.choice.label, name, ink.TITLE)
        detail = font(11.5)
        left = max(110, end + 12)
        right = self.width() - 14
        if self.map_button is not None:
            right = self.map_button.geometry().left() - 12
        draw(
            painter,
            left,
            23,
            elide(detail, self.choice.detail, right - left),
            detail,
            ink.MUTED,
        )
        painter.end()


class Link(QLabel):
    clicked = Signal()

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"font-size: 12px; color: {ACTIVE}; background: transparent; border: none;"
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


def _step_card(header: QHBoxLayout, body: Optional[QWidget] = None) -> QWidget:
    holder = card()
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    head = QWidget()
    head.setFixedHeight(34)
    head.setLayout(header)
    make_transparent(head)
    column.addWidget(head)
    if body is not None:
        column.addWidget(body)
    holder.setLayout(column)
    return holder


def _header(number: int, colour: str, question: str, done: bool) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(12, 0, 12, 0)
    row.setSpacing(10)
    row.addWidget(Disc(number, colour, done))
    row.addWidget(label(question, 13, ink.TITLE, bold=not done))
    return row


def _note(text: str, fill: str, bar: str, colour: str = ink.BODY) -> QLabel:
    note = QLabel(text)
    note.setWordWrap(True)
    note.setTextFormat(Qt.TextFormat.RichText)
    note.setStyleSheet(
        f"background: {fill}; border: none; border-left: 3px solid {bar};"
        f" border-radius: 3px; padding: 10px 12px; font-size: 13px; color: {colour};"
    )
    return note


class SpendPane(QWidget):
    """Spending the selected ticket: its steps, what it will give, and the button."""

    #: A ticket was spent, with the line saying what it gave.
    spent = Signal(str)
    #: A place to show on the map: an option being picked from, or the ground object
    #: a SAM ticket was spent on.
    show_on_map = Signal(object)
    #: "Next ticket" after a spend.
    next_ticket = Signal()

    def __init__(self, spend: Callable[[TicketView, tuple[str, ...]], str]) -> None:
        super().__init__()
        make_transparent(self)
        self.spend = spend
        self.game: Any = None
        self.ticket: Optional[TicketView] = None
        self.picked: list[Choice] = []
        self.result: Optional[str] = None
        self.refusal: Optional[str] = None
        #: The enemy's tickets are shown and not spent: GeneraLLM spends them.
        self.read_only = False

        column = QVBoxLayout()
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(12)
        caption = label("SPEND TICKET", 10.5, ink.CAPTION, bold=True)
        caption.setStyleSheet(caption.styleSheet() + " letter-spacing: 1px;")
        column.addWidget(caption)
        self.title = label("", 17, ink.TITLE, bold=True)
        self.title.setWordWrap(True)
        column.addWidget(self.title)
        self.steps = QVBoxLayout()
        self.steps.setSpacing(8)
        column.addLayout(self.steps)
        column.addStretch()

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.preview = label("", 12.5, ink.SOFT)
        self.preview.setWordWrap(True)
        footer.addWidget(self.preview, 1)
        self.cancel = button("Cancel", "normal", self.start_over)
        footer.addWidget(self.cancel)
        self.show_site = button("Show on map", "normal")
        footer.addWidget(self.show_site)
        self.go = QPushButton("Spend ticket")
        self._orange(self.go)
        self.go.clicked.connect(self._spend)
        footer.addWidget(self.go)
        column.addLayout(footer)
        self.setLayout(column)
        self.site: Any = None
        self.show_site.clicked.connect(
            lambda: self.show_on_map.emit(self.site.position if self.site else None)
        )

    @staticmethod
    def _orange(widget: QPushButton) -> None:
        style_button(widget, "normal")
        widget.setStyleSheet(
            f"QPushButton {{ background: {ink.ORANGE}; color: {ink.ON_ORANGE};"
            f" border: 1px solid {ink.ORANGE}; border-radius: 3px; padding: 4px 14px;"
            " font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #F5AA66; }"
            "QPushButton:disabled { background: #1B2530; color: #4F6070;"
            " border-color: #28333D; }"
        )

    def show_ticket(self, game: Any, ticket: Optional[TicketView]) -> None:
        self.game = game
        self.ticket = ticket
        self.picked = []
        self.result = None
        self.refusal = None
        self.site = None
        self._redraw()

    def start_over(self) -> None:
        self.picked = []
        self.refusal = None
        self._redraw()

    # ------------------------------------------------------------------ drawing

    def _clear(self) -> None:
        while self.steps.count():
            item = self.steps.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Off the pane now: deleteLater only runs once the event loop gets
                # back, and until then the old step would still be drawn.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _redraw(self) -> None:
        self._clear()
        self.show_site.setVisible(False)
        if self.result is not None:
            self._show_result()
            return
        ticket = self.ticket
        self.title.setText(ticket.title if ticket else "")
        self.setVisible(ticket is not None)
        if ticket is None:
            return
        if self.read_only:
            self.steps.addWidget(
                _note(
                    "The enemy's ticket. GeneraLLM spends it.",
                    ink.CARD,
                    ink.ENEMY_BAND,
                    ink.SOFT,
                )
            )
            self.preview.setText("")
            self.cancel.setVisible(False)
            self.go.setVisible(False)
            return
        steps = ticket.steps
        blocked = self._draw_steps(ticket, steps)
        complete = not blocked and len(self.picked) == len(steps)
        if self.refusal is not None:
            self.steps.addWidget(
                _note(
                    f"{self.refusal}<br><span style='color:{ink.QUIET}'>Not spent."
                    " The ticket stays.</span>",
                    REFUSED,
                    REFUSED_BAR,
                )
            )
        if complete:
            said = data.preview(
                ticket.ticket.prize.kind, [choice.label for choice in self.picked]
            )
            self.preview.setText(f"{said} Spending is final.".strip())
        else:
            self.preview.setText("")
        self.go.setText("Try again" if self.refusal is not None else "Spend ticket")
        self.go.setEnabled(complete)
        self.cancel.setVisible(bool(self.picked))
        self.go.setVisible(True)

    def _draw_steps(self, ticket: TicketView, steps: Sequence[Step]) -> bool:
        """The steps up to the one being asked. True if that one has nothing to
        pick from."""
        prize = ticket.ticket.prize
        for number, step in enumerate(steps, start=1):
            index = number - 1
            if index < len(self.picked):
                self._done(number, step, self.picked[index], ticket)
                continue
            options = step.options(
                self.game, prize, tuple(choice.key for choice in self.picked)
            )
            if step.auto and len(options) == 1:
                self.picked.append(options[0])
                self._done(number, step, options[0], ticket, fixed=True)
                continue
            if not options:
                body = label(
                    "Nothing to pick from now. The ticket stays until there is.",
                    12.5,
                    ink.QUIET,
                )
                body.setContentsMargins(40, 0, 12, 12)
                self.steps.addWidget(
                    _step_card(_header(number, BLOCKED, step.question, False), body)
                )
                return True
            self._asking(number, step, options)
            return False
        return False

    def _done(
        self,
        number: int,
        step: Step,
        choice: Choice,
        ticket: TicketView,
        fixed: bool = False,
    ) -> None:
        header = _header(number, DONE, step.question, done=True)
        header.addWidget(label(choice.label, 13, ink.TITLE, bold=True))
        detail = label(choice.detail, 11.5, ink.MUTED)
        header.addWidget(detail, 1)
        if not fixed:
            change = Link("Change")
            change.clicked.connect(lambda: self._change(number - 1))
            header.addWidget(change)
        self.steps.addWidget(_step_card(header))

    def _asking(self, number: int, step: Step, options: Sequence[Choice]) -> None:
        header = _header(number, ACTIVE, step.question, done=False)
        header.addStretch()
        header.addWidget(label(f"{len(options)} to pick from", 11.5, ink.MUTED))
        body = QWidget()
        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        for choice in options:
            row = ChoiceRow(choice)
            row.picked.connect(lambda _key, chosen=choice: self._pick(chosen))
            row.show_on_map.connect(self.show_on_map.emit)
            rows.addWidget(row)
        rows.addStretch()
        body.setLayout(rows)
        make_transparent(body)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        scroll.setFixedHeight(CHOICE_ROW * min(len(options), SHOWN_CHOICES))
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        self.steps.addWidget(_step_card(header, scroll))

    def _show_result(self) -> None:
        self.title.setText(self.ticket.title if self.ticket else "")
        self.steps.addWidget(
            _note(
                f"<span style='color:{DONE}; font-size: 10px; font-weight: bold;"
                f" letter-spacing: 1px'>GIVEN</span><br>{self.result}",
                GIVEN,
                DONE,
                ink.TITLE,
            )
        )
        self.preview.setText("")
        self.cancel.setVisible(False)
        self.show_site.setVisible(self.site is not None)
        self.go.setText("Next ticket")
        self.go.setEnabled(True)

    # ------------------------------------------------------------------ actions

    def _pick(self, choice: Choice) -> None:
        self.picked.append(choice)
        self.refusal = None
        self._redraw()

    def _change(self, index: int) -> None:
        self.picked = self.picked[:index]
        self.refusal = None
        self._redraw()

    def _spend(self) -> None:
        if self.result is not None:
            self.next_ticket.emit()
            return
        ticket = self.ticket
        if ticket is None:
            return
        keys = tuple(choice.key for choice in self.picked)
        try:
            line = self.spend(ticket, keys)
        except CannotGive as refusal:
            self.refusal = str(refusal)
            self._redraw()
            return
        except Exception:
            logging.exception("Could not spend the High Command ticket")
            self.refusal = "The game could not give it."
            self._redraw()
            return
        self.result = line
        self.site = self._site(ticket, keys)
        self._redraw()
        self.spent.emit(line)

    def _site(self, ticket: TicketView, keys: tuple[str, ...]) -> Any:
        """The ground object a SAM ticket was spent on, to show on the map."""
        if ticket.ticket.prize.kind != "sam" or not keys or self.game is None:
            return None
        return next(
            (tgo for tgo in self.game.theater.ground_objects if str(tgo.id) == keys[0]),
            None,
        )


class TicketsPage(QWidget):
    """The tickets kept, and spending the selected one."""

    def __init__(
        self,
        spend: Callable[[TicketView, tuple[str, ...]], str],
        on_spent: Callable[[str], None],
        show_on_map: Callable[[Any], None],
    ) -> None:
        super().__init__()
        self.game: Any = None
        self.model = TicketsModel(self)
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(TicketDelegate(self.view))
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setStyleSheet(
            f"QListView {{ background: {ink.CARD}; border: none; outline: none; }}"
        )
        footnote = label(
            "Tickets never expire. A ticket that cannot be spent now stays until it"
            " can.",
            11,
            ink.CAPTION,
        )
        footnote.setWordWrap(True)
        footnote.setContentsMargins(14, 8, 14, 10)
        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(0)
        left_column.addWidget(self.view, 1)
        left_column.addWidget(footnote)
        left = card()
        left.setLayout(left_column)
        left.setMinimumWidth(420)

        self.pane = SpendPane(spend)
        self.pane.spent.connect(on_spent)
        self.pane.show_on_map.connect(show_on_map)
        self.pane.next_ticket.connect(self._next)

        self.empty = label(
            "No tickets kept. A ticket is earned by achieving a request whose prize"
            " is one.",
            12.5,
            ink.QUIET,
        )
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.pane)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 660])
        self.splitter = splitter

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 0, 14, 14)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.empty, 1)
        self.setLayout(layout)

        self.view.selectionModel().currentChanged.connect(
            lambda current, _previous: self._select(current)
        )

    def set_read_only(self, read_only: bool) -> None:
        self.pane.read_only = read_only
        self.pane.result = None

    def show_tickets(self, game: Any, tickets: Sequence[TicketView]) -> None:
        """The list as it stands. A pane showing what was just given keeps it until
        Next ticket."""
        self.game = game
        chosen = self.selected
        keep = self.pane.result is not None
        self.model.set_tickets(tickets)
        self.splitter.setVisible(bool(tickets) or keep)
        self.empty.setVisible(not tickets and not keep)
        if keep:
            return
        row = 0
        if chosen is not None:
            row = next(
                (n for n, view in enumerate(tickets) if view.ticket is chosen.ticket),
                0,
            )
        if tickets:
            self.view.setCurrentIndex(self.model.index(row, 0))
        else:
            self.pane.show_ticket(game, None)

    @property
    def selected(self) -> Optional[TicketView]:
        return self.model.at(self.view.currentIndex())

    def _select(self, index: QModelIndex) -> None:
        # A reset list clears the selection; that is not the player picking nothing,
        # and a pane showing what was just given keeps it.
        ticket = self.model.at(index)
        if ticket is None:
            return
        self.pane.result = None
        self.pane.show_ticket(self.game, ticket)

    def _next(self) -> None:
        self.pane.result = None
        if self.model.rowCount():
            self.view.setCurrentIndex(self.model.index(0, 0))
            self._select(self.view.currentIndex())
        else:
            self.pane.show_ticket(self.game, None)
            self.splitter.setVisible(False)
            self.empty.setVisible(True)
