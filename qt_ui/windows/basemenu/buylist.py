"""A buy list: rows you can read at a glance, and the figures pinned above them.

Buying was three group boxes in a grid -- a name with "2 (2 idle)" beside it, a price,
and a minus/plus pair -- and the numbers that decide whether an order is a good idea
were somewhere else entirely: parking in a paragraph at the top of the window, budget
in the footer. Ordering six aircraft meant scrolling up to see whether they fitted,
then down to the row, then up again to check the money.

So the row carries what the Air Wing list already carries -- the aircraft's own
silhouette, the type, what it flies, the squadron -- and the summary stays fixed above
the scroll, saying what the order leaves you with and turning amber the moment it
cannot be paid for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from qt_ui.widgets.cards import (
    CAPTION,
    CARD_BG,
    CARD_BORDER,
    make_transparent,
    shrinkable,
    shrinkable_widget,
)
from qt_ui.widgets.controls import VALUE, mono

if TYPE_CHECKING:
    from qt_ui.windows.basemenu.UnitTransactionFrame import UnitTransactionFrame

#: The colours the rest of the app already uses for these four meanings.
BRIGHT = "#F2F7FA"
QUIET = "#7C8B99"
AMBER = "#E0A86B"
GREEN = "#86C39A"
ROW_BG_ORDERED = "#182430"
#: The Air Wing list's hover fill, so the two lists behave the same way.
ROW_BG_HOVER = "#1A2A38"
SCROLL_HANDLE = "#2E3F4D"
SCROLL_HANDLE_HOVER = "#3F5D73"

#: Column widths, so every row lines up under the header without a table.
ICON_WIDTH = 91
ICON_HEIGHT = 24
PRESENT_WIDTH = 96
COMPACT_PRESENT_WIDTH = 60
PRICE_WIDTH = 70

#: The stepper: minus, the count, plus. The last column has to be given this width
#: rather than left to stretch, or it shares the slack with the name column and every
#: heading ends up somewhere its column is not.
STEPPER_WIDTH = 28 + 40 + 28
ROW_HEIGHT = 56

#: A ground unit has no silhouette, no cap and no idle count, so its row is one line.
COMPACT_ROW_HEIGHT = 40
SUMMARY_HEIGHT = 40
GROUP_HEADER_HEIGHT = 26

#: A heading sits under the rows it heads rather than over them, and carries the
#: accent so the eye finds the breaks without reading the words.
GROUP_BG = "#101A24"
GROUP_INK = "#8FA3BD"
GROUP_BAR = "#3F5D73"


@dataclass(frozen=True)
class Figure:
    """A number and what it means, for the summary bar."""

    caption: str
    value: str
    note: str = ""
    warn: bool = False


def _text(text: str, size: float, colour: str, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"font-size: {size}px; color: {colour}; background: transparent; border: none;"
        f" font-weight: {'600' if bold else 'normal'};"
    )
    return label


def _mono(text: str, size: int, colour: str) -> QLabel:
    label = QLabel(text)
    label.setFont(mono(size))
    label.setStyleSheet(
        f"color: {colour}; background: transparent; border: none; font-weight: 600;"
    )
    return label


def chip(text: str, fill: str, ink: str) -> QLabel:
    """A task chip, in the Air Wing list's colours."""
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"background: {fill}; color: {ink}; border: none; border-radius: 4px;"
        " padding: 1px 8px; font-size: 10px; font-weight: bold; letter-spacing: 0.8px;"
    )
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return label


def group_header(name: str, count: int) -> QWidget:
    """A class of unit, so twenty identical rows read as five short groups.

    Darker than the rows rather than lighter, with a rule above it and an accent bar
    down its left edge: at one shade off the row colour it read as another row with
    the text greyed out, which is the opposite of a heading.
    """
    label = QLabel(f"{name.upper()}   {count}")
    label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    label.setObjectName(f"buyGroup{id(label)}")
    label.setFixedHeight(GROUP_HEADER_HEIGHT)
    label.setStyleSheet(
        f"#{label.objectName()} {{ background: {GROUP_BG}; color: {GROUP_INK};"
        " font-size: 10.5px; font-weight: bold; letter-spacing: 1.4px;"
        " padding-left: 11px; border: none;"
        f" border-top: 1px solid {CARD_BORDER};"
        f" border-bottom: 1px solid {CARD_BORDER};"
        f" border-left: 3px solid {GROUP_BAR}; }}"
    )
    return label


class OrderSummary(QWidget):
    """What this base's order leaves you with, pinned above the list it applies to.

    It is the arithmetic the player does in his head today by scrolling back up, and
    the one place an order that cannot be paid for can say so before it is placed.
    """

    def __init__(
        self,
        title: str,
        figures: Callable[[], list[Figure]],
        clear: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self._read_figures = figures
        self._clear = clear

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("orderSummary")
        self.setStyleSheet(
            "#orderSummary { background: #1B2732;"
            f" border-bottom: 1px solid {CARD_BORDER}; }}"
        )
        self.setFixedHeight(SUMMARY_HEIGHT)

        self._row = QHBoxLayout()
        self._row.setContentsMargins(14, 0, 14, 0)
        self._row.setSpacing(18)
        self.setLayout(self._row)

        self._title = _text(title.upper(), 10.5, CAPTION, bold=True)
        self._title.setStyleSheet(self._title.styleSheet() + " letter-spacing: 1px;")
        self._title.setParent(self)
        self.refresh()

    def refresh(self) -> None:
        """Rebuilt rather than updated: the cells themselves change with the order."""
        while self._row.count():
            taken = self._row.takeAt(0)
            widget = taken.widget()
            if widget is not None and widget is not self._title:
                widget.deleteLater()

        self._row.addWidget(self._title)
        for figure in self._read_figures():
            self._row.addWidget(self._figure(figure))
        self._row.addStretch()

        if self._clear is not None:
            link = _text("Clear order", 11, "#8FC3F0")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.mousePressEvent = lambda _event: self._clear()  # type: ignore[assignment,misc,union-attr]
            self._row.addWidget(link)

    def _figure(self, figure: Figure) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(_text(figure.caption, 11, QUIET))
        row.addWidget(_mono(figure.value, 12, AMBER if figure.warn else BRIGHT))
        if figure.note:
            row.addWidget(
                shrinkable(_text(figure.note, 11, AMBER if figure.warn else QUIET))
            )

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(row)
        return holder


def scrollbar_width() -> int:
    """How wide this style draws a vertical scrollbar."""
    style = QApplication.style()
    return style.pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)


def scrolling(content: QWidget) -> QScrollArea:
    """A scroll area that always keeps room for its bar, so the columns hold still."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    # Always on, so the columns do not shift by a scrollbar's width when the list
    # grows past the card -- which means it has to be quiet enough to keep company
    # with, rather than the app's default light grey stripe down a dark card.
    area.setStyleSheet(
        "QScrollArea { background: transparent; border: none; }"
        f"QScrollBar:vertical {{ background: {CARD_BG}; width: 12px;"
        f" margin: 0; border-left: 1px solid {CARD_BORDER}; }}"
        f"QScrollBar::handle:vertical {{ background: {SCROLL_HANDLE};"
        " border-radius: 3px; min-height: 30px; margin: 2px; }"
        f"QScrollBar::handle:vertical:hover {{ background: {SCROLL_HANDLE_HOVER}; }}"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
        " height: 0; border: none; background: none; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
        " background: none; }"
    )
    return area


@dataclass(frozen=True)
class Column:
    """One heading, the width the rows give that column, and what it sorts by."""

    label: str
    key: str
    width: Optional[int] = None
    #: Which way the first click sorts. A name wants A first; a count wants the
    #: biggest first, because "which have I none of" is answered by the other end.
    descending_first: bool = False


class ColumnHeaders(QWidget):
    """The words above the rows, at the rows' own widths, and sortable.

    Laid out from the same constants the rows are, because a header that is nearly
    over its column is worse than no header: it reads as a mistake rather than as a
    label. The left offset is the icon column, as a margin rather than as a spacer
    widget -- an empty label there picked up the app's label styling and looked like
    a picture that had failed to load.
    """

    sort_changed = Signal(str)

    def __init__(
        self, columns: list[Column], left_margin: int = 14, current: str = ""
    ) -> None:
        # The rows live inside a scroll area and the header does not, so the header
        # has to give up the same width the scrollbar takes or every column is a
        # scrollbar's width to the right of the figures under it.
        super().__init__()
        self.columns = columns
        self.current = current
        self.ascending = True

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"buyHeaders{id(self)}")
        self.setFixedHeight(24)
        self.setStyleSheet(
            f"#{self.objectName()} {{ background: {CARD_BG}; border: none;"
            f" border-bottom: 1px solid {CARD_BORDER}; }}"
        )

        self._row = QHBoxLayout()
        self._row.setContentsMargins(left_margin, 0, 14 + scrollbar_width(), 0)
        self._row.setSpacing(10)
        self.setLayout(self._row)

        self._labels: dict[str, QLabel] = {}
        for column in self.columns:
            label = QLabel()
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.mousePressEvent = (  # type: ignore[assignment,misc,union-attr]
                lambda _event, key=column.key: self.clicked(key)
            )
            if column.width is not None:
                label.setFixedWidth(column.width)
            self._labels[column.key] = label
            self._row.addWidget(label, 0 if column.width is not None else 1)
        self.repaint_labels()

    def clicked(self, key: str) -> None:
        """The same column again reverses it; a different one starts its own way."""
        if key == self.current:
            self.ascending = not self.ascending
        else:
            self.current = key
            column = next(c for c in self.columns if c.key == key)
            self.ascending = not column.descending_first
        self.repaint_labels()
        self.sort_changed.emit(key)

    def repaint_labels(self) -> None:
        for column in self.columns:
            label = self._labels[column.key]
            active = column.key == self.current
            arrow = (" \u25b2" if self.ascending else " \u25bc") if active else ""
            label.setText(column.label.upper() + arrow)
            label.setStyleSheet(
                "font-size: 10px; font-weight: bold; letter-spacing: 1px;"
                f" color: {VALUE if active else CAPTION};"
                " background: transparent; border: none;"
            )


class PurchaseRow(QWidget):
    """One thing you can buy: what it is, what you have, what it costs, and the order.

    Everything on it comes from the frame that owns it, so this class never learns what
    a squadron is.
    """

    def __init__(
        self, item: object, frame: UnitTransactionFrame, compact: bool = False
    ) -> None:
        super().__init__()
        self.item = item
        self.frame = frame
        self.compact = compact

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName(f"buyRow{id(self)}")
        self.setFixedHeight(COMPACT_ROW_HEIGHT if compact else ROW_HEIGHT)

        self.hovered = False
        if frame.supports_item_dialog():
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout()
        row.setContentsMargins(14, 4 if compact else 8, 14, 4 if compact else 8)
        row.setSpacing(10)
        if not compact:
            row.addWidget(self._icon())
        row.addLayout(self._identity(), 1)
        row.addWidget(self._present())
        row.addWidget(self._price())
        row.addWidget(frame.order_control(item))
        self.setLayout(row)
        self.refresh()

    # -- the whole row is the target, not just the name ----------------------
    #
    # It matched the Air Wing list in every other respect, where a squadron opens from
    # anywhere on its row and lights up under the pointer. Only the underlined name
    # worked here, and nothing said the rest of the row was inert.

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self.frame.supports_item_dialog()
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.frame.on_item_clicked(self.item)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event: QEnterEvent) -> None:
        if self.frame.supports_item_dialog():
            self.hovered = True
            self.paint_background()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        if self.hovered:
            self.hovered = False
            self.paint_background()
        super().leaveEvent(event)

    # -- the pieces ----------------------------------------------------------

    def _icon(self) -> QWidget:
        label = QLabel()
        label.setFixedSize(ICON_WIDTH, ICON_HEIGHT)
        pixmap: Optional[QPixmap] = self.frame.row_icon(self.item)
        if pixmap is not None:
            label.setPixmap(
                pixmap.scaled(
                    ICON_WIDTH,
                    ICON_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        label.setStyleSheet("background: transparent; border: none;")
        return label

    def _identity(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        name, variant = self.frame.row_title(self.item)
        title = QHBoxLayout()
        title.setContentsMargins(0, 0, 0, 0)
        title.setSpacing(8)
        title.addWidget(_text(name, 14, BRIGHT, bold=True))
        if variant:
            title.addWidget(_text(variant, 12, QUIET))
        for text, fill, ink in self.frame.row_chips(self.item):
            title.addWidget(chip(text, fill, ink))
        self._subtitle = _text("", 11.5, QUIET)
        if self.compact:
            title.addWidget(self._subtitle)
        title.addStretch()

        # The pieces keep their own widths and stay packed to the left; it is the box
        # around them that gives up the demand, so a long squadron name is clipped
        # rather than deciding how wide the window has to be.
        packed = QWidget()
        make_transparent(packed)
        packed.setLayout(title)
        column.addWidget(shrinkable_widget(packed))
        if not self.compact:
            column.addWidget(shrinkable_widget(self._subtitle))
        return column

    def _present(self) -> QWidget:
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        first = QHBoxLayout()
        first.setContentsMargins(0, 0, 0, 0)
        first.setSpacing(4)
        self._count = _mono("", 14, BRIGHT)
        self._of = _text("", 11, QUIET)
        self._pending = _text("", 11, AMBER)
        first.addWidget(self._count)
        first.addWidget(self._of)
        first.addWidget(self._pending)
        first.addStretch()
        column.addLayout(first)

        self._idle = _text("", 11, GREEN)
        if self.compact:
            self._idle.setVisible(False)
        else:
            column.addWidget(self._idle)

        holder = QWidget()
        make_transparent(holder)
        holder.setFixedWidth(COMPACT_PRESENT_WIDTH if self.compact else PRESENT_WIDTH)
        holder.setLayout(column)
        return holder

    def _price(self) -> QWidget:
        self._price_label = _mono("", 13, BRIGHT)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._price_label)
        layout.addStretch()

        holder = QWidget()
        make_transparent(holder)
        holder.setFixedWidth(PRICE_WIDTH)
        holder.setLayout(layout)
        return holder

    # -- what changes when an order is placed --------------------------------

    def refresh(self) -> None:
        counts = self.frame.row_counts(self.item)
        self._count.setText(str(counts.present))
        self._of.setText(f"/ {counts.capacity} max" if counts.capacity else "")
        if counts.pending > 0:
            self._pending.setText(f"+{counts.pending}")
        elif counts.pending < 0:
            self._pending.setText(str(counts.pending))
        else:
            self._pending.setText("")
        self._idle.setText("" if counts.idle is None else f"{counts.idle} idle")
        self._price_label.setText(f"${self.frame.price_of(self.item)}M")

        subtitle = self.frame.row_subtitle(self.item)
        warning = self.frame.row_warning(self.item)
        if warning:
            # Amber, and on the row rather than in a tooltip: an order that will be
            # refused should say so before it is placed, not after it fails.
            self._subtitle.setText(
                f"{subtitle} · ▲ {warning}" if subtitle else f"▲ {warning}"
            )
            colour = AMBER
        else:
            self._subtitle.setText(subtitle)
            colour = QUIET
        self.restyle(
            self._subtitle,
            f"font-size: 11.5px; color: {colour}; background: transparent;"
            " border: none;",
        )

        self._ordered = bool(counts.pending)
        self.paint_background()

    def paint_background(self) -> None:
        """An ordered row is tinted and barred amber; the one under the pointer lifts."""
        if self.hovered:
            background = ROW_BG_HOVER
        elif self._ordered:
            background = ROW_BG_ORDERED
        else:
            background = "transparent"
        bar = AMBER if self._ordered else "transparent"
        # Only when it has actually changed: applying a stylesheet re-polishes the
        # widget and its children, and a purchase repaints every row in the list.
        self.restyle(
            self,
            f"#{self.objectName()} {{ background: {background};"
            f" border: none; border-bottom: 1px solid {CARD_BORDER};"
            f" border-left: 3px solid {bar}; }}",
        )

    @staticmethod
    def restyle(widget: QWidget, style: str) -> None:
        if widget.styleSheet() != style:
            widget.setStyleSheet(style)
