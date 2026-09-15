"""The widgets the pilot dialog is built from: chips, stars, bars and rows.

The dialog is four cards of rows. Each row is a fixed-height widget with a bottom line,
and a card is a stack of rows with the last line removed -- which is why the stack is a
class rather than a function: opening a disclosure changes which row is last.

The palette is imported from the Air Wing rather than copied, so the two cannot drift
apart.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qt_ui.widgets.cards import CARD_BG, CARD_BORDER, card, make_transparent
from qt_ui.widgets.controls import mono, wrapped_tooltip
from qt_ui.windows.airwingconfig.common import (
    ACCENT,
    AMBER,
    BAR_TRACK,
    GREEN,
    LINE,
    PANEL,
    RED,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)
from qt_ui.rankstars import (
    RANK_LEVELS,
    STAR_EMPTY,
    STAR_FILLED,
    STAR_FILLED_DIMMED,
)

__all__ = [
    "ACCENT",
    "AMBER",
    "BAR_TRACK",
    "GREEN",
    "LINE",
    "PANEL",
    "RED",
    "TEXT_BASE",
    "TEXT_LABEL",
    "TEXT_MUTED",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_TERTIARY",
    "Bands",
    "Bar",
    "Clickable",
    "Elided",
    "captioned",
    "Row",
    "Stack",
    "chip",
    "label",
    "rich",
    "stars",
]

#: The fill of a row that is open, and of a family heading. One step up from the card
#: rather than a colour: it says "this belongs together", not "look at this".
ROW_OPEN = "#182430"
ROW_HOVER = "#1A2A38"
HEADING_BG = "#1B2732"

#: The two families of a combat record, coloured so the eye can find its way back to
#: the one it was reading.
AIR_FAMILY = "#6E93B0"
GROUND_FAMILY = "#9A7A55"

#: Hardening, which is history rather than state: tan, so nobody reads it as a warning.
TAN = "#C9B28E"
TAN_DIMMED = "#9A8A6E"

#: Nothing to show. Quieter than a hint, because an empty card is not news.
EMPTY = "#4F6070"

SEPARATOR = CARD_BORDER


def label(
    text: str,
    size: float = 12.0,
    colour: str = TEXT_BASE,
    bold: bool = False,
    monospace: bool = False,
) -> QLabel:
    """One piece of text on a card, with no background of its own.

    The app stylesheet gives every QLabel a panel-coloured background, which over a
    card reads as a box around every word.
    """
    widget = QLabel(text)
    if monospace:
        widget.setFont(mono(int(size)))
    widget.setStyleSheet(
        f"font-size: {size}px; color: {colour}; background: transparent;"
        f" border: none; font-weight: {'600' if bold else 'normal'};"
    )
    return widget


class Elided(QLabel):
    """A label that elides its text rather than being clipped by its neighbours.

    A plain QLabel asks for the width of its full text, so a long name in the header was
    painted over by the stars beside it.

    """

    def __init__(
        self,
        text: str,
        size: float = 12.0,
        colour: str = TEXT_BASE,
        bold: bool = False,
    ) -> None:
        super().__init__(text)
        self.full = text
        self.colour = colour
        font = QFont()
        font.setPixelSize(int(round(size)))
        if bold:
            font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMinimumWidth(0)

    def sizeHint(self) -> QSize:
        # Asked of the float metrics and rounded up: the integer advance rounds down,
        # and a label given exactly that many pixels elides a name that fits.
        metrics = QFontMetricsF(self.font())
        return QSize(
            math.ceil(metrics.horizontalAdvance(self.full)) + 1,
            math.ceil(metrics.height()),
        )

    def minimumSizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance("…"), metrics.height())

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor(self.colour))
        metrics = QFontMetrics(self.font())
        painter.drawText(
            self.rect(),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(self.full, Qt.TextElideMode.ElideRight, self.width()),
        )
        painter.end()


def rich(html: str, size: float = 12.0) -> QLabel:
    """A line that carries more than one colour, which is most of them."""
    widget = QLabel(html)
    widget.setStyleSheet(f"font-size: {size}px; background: transparent; border: none;")
    return widget


def chip(text: str, ink: str, fill: str = "", outline: bool = False) -> QLabel:
    """A short word in a box: the state, PLAYER, CHEAT."""
    widget = QLabel(text)
    background = f"background: {fill};" if fill else "background: transparent;"
    border = f"border: 1px solid {ink};" if outline else "border: none;"
    widget.setStyleSheet(
        f"{background} color: {ink}; {border} border-radius: 3px;"
        " padding: 2px 7px; font-size: 10px; font-weight: bold;"
        " letter-spacing: 0.8px;"
    )
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return widget


def stars(level: int, size: float = 13.0, dimmed: bool = False) -> QLabel:
    """Five slots, filled to the rung he stands on -- the roster's own shape."""
    filled = max(0, min(RANK_LEVELS, level))
    on = STAR_FILLED_DIMMED if dimmed else STAR_FILLED
    widget = rich(
        f"<span style='color:{on}'>{'★' * filled}</span>"
        f"<span style='color:{STAR_EMPTY}'>{'★' * (RANK_LEVELS - filled)}</span>",
        size,
    )
    widget.setStyleSheet(
        f"font-size: {size}px; letter-spacing: 1.5px; background: transparent;"
        " border: none;"
    )
    return widget


#: Section headings. Brighter than the caption grey the other dialogs use, and sat
#: closer to the card, because at that distance and that weight they read as floating
#: over the page rather than as the name of the box under them.
CAPTION_INK = "#8E9DAA"
CAPTION_GAP = 5


class Clickable(QLabel):
    """A word you can press.

    A link inside a row that is itself clickable is not enough: the row sees the press
    first and shuts itself under the finger. This takes the press.
    """

    clicked = Signal()

    def __init__(
        self, text: str = "", size: float = 11.0, colour: str = ACCENT
    ) -> None:
        super().__init__(text)
        self.colour = colour
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"font-size: {size}px; color: {colour}; background: transparent;"
            " border: none;"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            # Accepted, so whatever is behind it never sees the press.
            event.accept()
            return
        super().mousePressEvent(event)


def captioned(
    name: str,
    content: QWidget,
    hint: str = "",
    ink: str = "",
    tooltip: str = "",
) -> QWidget:
    """A heading and the card it names, as one thing to put in a column."""
    holder = QWidget()
    make_transparent(holder)
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(CAPTION_GAP)
    column.addWidget(heading(name, hint, ink, tooltip))
    column.addWidget(content)
    holder.setLayout(column)
    return holder


def heading(name: str, hint: str = "", ink: str = "", tooltip: str = "") -> QWidget:
    """The heading on its own, for the one row two cards share."""
    holder = QWidget()
    make_transparent(holder)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    title = label(name.upper(), 11, ink or CAPTION_INK, bold=True)
    title.setStyleSheet(title.styleSheet() + " letter-spacing: 1px;")
    row.addWidget(title)
    if hint:
        # Not shrinkable: Ignored gives up its width to the stretch beside it, and the
        # hint was drawn at nothing pixels wide.
        row.addWidget(label(hint, 11, EMPTY))
    row.addStretch()
    holder.setLayout(row)
    if tooltip:
        holder.setToolTip(wrapped_tooltip(tooltip))
    return holder


class Bar(QWidget):
    """A thin bar with a fraction of it filled.

    A QProgressBar styled down to six pixels still carries a chunk, a groove and a
    text alignment nobody wants; this is the two rounded rectangles that were meant.
    """

    def __init__(
        self,
        fraction: float,
        colour: str,
        width: Optional[int] = None,
        height: int = 6,
        track: str = BAR_TRACK,
        alpha: float = 1.0,
    ) -> None:
        super().__init__()
        self.fraction = max(0.0, min(1.0, fraction))
        self.colour = colour
        self.track = track
        self.alpha = alpha
        self.setFixedHeight(height)
        if width is not None:
            self.setFixedWidth(width)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = self.height() / 2

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), radius, radius)
        painter.fillPath(path, QColor(self.track))

        if self.fraction > 0:
            filled = QPainterPath()
            filled.addRoundedRect(
                0, 0, self.width() * self.fraction, self.height(), radius, radius
            )
            colour = QColor(self.colour)
            colour.setAlphaF(self.alpha)
            painter.fillPath(filled, colour)
        painter.end()


class Bands(QWidget):
    """One segment per band, with only the one he is in at full strength.

    The whole scale rather than a bar, because the question a player has is not "how
    much" but "which band, and how close to the next".
    """

    GAP = 2
    FADED = 0.35

    def __init__(self, colours: Sequence[str], current: int, height: int = 6) -> None:
        super().__init__()
        self.colours = list(colours)
        self.current = current
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:
        if not self.colours:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        count = len(self.colours)
        gaps = self.GAP * (count - 1)
        width = (self.width() - gaps) / count
        radius = self.height() / 2
        for index, name in enumerate(self.colours):
            left = index * (width + self.GAP)
            path = QPainterPath()
            path.addRoundedRect(left, 0, width, self.height(), radius, radius)
            colour = QColor(name)
            if index != self.current:
                colour.setAlphaF(self.FADED)
            painter.fillPath(path, colour)
        painter.end()


class Row(QWidget):
    """One line of a card: a fixed height, a bottom rule, and a layout to fill.

    ``interactive`` makes it light up under the cursor and emit :attr:`clicked`, which
    is how a kill row opens.
    """

    clicked = Signal()

    def __init__(
        self,
        height: int = 30,
        fill: str = "",
        separator: bool = True,
        interactive: bool = False,
        vertical: bool = False,
        margins: tuple[int, int, int, int] = (14, 0, 14, 0),
        spacing: int = 8,
    ) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"pilotRow{id(self)}")
        self.setFixedHeight(height)
        self.fill = fill
        self.separator = separator
        self.interactive = interactive
        self._hovered = False
        if interactive:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setMouseTracking(True)

        self.body: QBoxLayout = QVBoxLayout() if vertical else QHBoxLayout()
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)
        self.setLayout(self.body)
        self._restyle()

    def add(self, *widgets: QWidget) -> Row:
        for widget in widgets:
            self.body.addWidget(widget)
        return self

    def stretch(self) -> Row:
        self.body.addStretch()
        return self

    def set_separator(self, on: bool) -> None:
        if on != self.separator:
            self.separator = on
            self._restyle()

    def set_fill(self, fill: str) -> None:
        self.fill = fill
        self._restyle()

    def _restyle(self) -> None:
        fill = self.fill or "transparent"
        if self._hovered and self.interactive:
            fill = ROW_HOVER if not self.fill else self.fill
        rule = f" border-bottom: 1px solid {SEPARATOR};" if self.separator else ""
        self.setStyleSheet(
            f"#{self.objectName()} {{ background: {fill}; border: none;{rule} }}"
        )

    def enterEvent(self, event: object) -> None:
        if self.interactive:
            self._hovered = True
            self._restyle()

    def leaveEvent(self, event: object) -> None:
        if self.interactive:
            self._hovered = False
            self._restyle()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.interactive and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class Stack(QWidget):
    """A card made of rows, with the line under the last visible one taken off.

    A disclosure changes which row that is, so the card is asked to look again rather
    than told: the rows do not know about each other.
    """

    def __init__(self, rows: Sequence[QWidget] = ()) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"pilotStack{id(self)}")
        self.setStyleSheet(
            f"#{self.objectName()} {{ background: {CARD_BG};"
            f" border: 1px solid {CARD_BORDER}; border-radius: 3px; }}"
        )
        self.rows: list[QWidget] = []
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.setLayout(column)
        for widget in rows:
            self.append(widget)
        self.refresh()

    def append(self, widget: QWidget) -> None:
        self.rows.append(widget)
        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.addWidget(widget)

    def refresh(self) -> None:
        """Give every row its line back except whichever one is now last."""
        visible = [
            row for row in self.rows if isinstance(row, Row) and not row.isHidden()
        ]
        for row in self.rows:
            if isinstance(row, Row):
                row.set_separator(row is not visible[-1] if visible else True)
        # A card that has just opened is taller than it was, and nothing else tells
        # the column that holds it.
        self.updateGeometry()


def panel(
    inner: QWidget, margins: tuple[int, int, int, int] = (14, 14, 14, 14)
) -> QWidget:
    """A card with one widget inside it, for the cards that are not rows."""
    holder = card()
    layout = QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(10)
    make_transparent(inner)
    layout.addWidget(inner)
    holder.setLayout(layout)
    return holder


def empty_row(text: str = "none yet", height: int = 30) -> Row:
    """What a card says when there is nothing in it."""
    row = Row(height=height)
    row.body.setContentsMargins(30, 0, 14, 0)
    row.add(label(text, 12.5, EMPTY))
    row.stretch()
    return row
