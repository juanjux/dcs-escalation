"""The Intelligence lists, painted.

Three different lists -- money, aircraft, vehicles -- share one painter, because what
they have in common is the shape: a caption band, rows under it, one number per row on
a single right-hand edge, and a bar saying how much of the whole that row is. Drawing
them rather than stacking labels is what puts every count on the same vertical line
however long the names are, and is what lets a base fold.

A flat list rather than a QTreeView: the model already sorts and filters, so folding a
group is one recomputation of which lines exist, and nothing has to argue with Qt about
branch indicators and indentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Union

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from qt_ui.widgets.controls import mono
from qt_ui.windows.intel.model import (
    EconomyRow,
    EconomySection,
    ForceGroup,
    ForceRow,
    money,
)

#: The side colour. Own is the accent the rest of the rebuilt windows use; enemy is a
#: rust rather than a red, because red in this app means destroyed.
OWN_ACCENT = QColor("#8FC3F0")
ENEMY_ACCENT = QColor("#C08A72")

TEXT = QColor("#F2F7FA")
BODY = QColor("#D3DFE8")
MUTED = QColor("#7C8B99")
FAINT = QColor("#6B7A87")
NAME_DIMMED = QColor("#A9B7C3")
DAMAGE = QColor("#C08A72")
INCOME = QColor("#86C39A")
INCOME_BAR = QColor("#5F8A6C")
#: Neutral, so the side colour stays on the group headers and these do not compete.
TYPE_BAR = QColor("#3F5D73")
BAND = QColor("#182734")
SEPARATOR = QColor("#1D2731")
HOVER_ROW = QColor("#1A2A38")
HOVER_HEADER = QColor("#1E3A52")
HIGHLIGHT = QColor("#2B4A66")

HEADER_HEIGHT = 34
ROW_HEIGHT = 30
NOTE_HEIGHT = 26
SECTION_HEIGHT = 26
ECONOMY_HEIGHT = 36

RIGHT_MARGIN = 16
SHARE_COLUMN = 60
NAME_INDENT = 44
TYPE_BAR_WIDTH = 120
ECONOMY_BAR_WIDTH = 200
ECONOMY_DETAIL_X = 170


@dataclass(frozen=True)
class HeaderLine:
    group: ForceGroup
    folded: bool


@dataclass(frozen=True)
class TypeLine:
    row: ForceRow
    #: The biggest count in this group, so the bar is relative to its own base.
    biggest: int


@dataclass(frozen=True)
class NoteLine:
    text: str


@dataclass(frozen=True)
class SectionLine:
    section: EconomySection


@dataclass(frozen=True)
class EconomyLine:
    row: EconomyRow


Line = Union[HeaderLine, TypeLine, NoteLine, SectionLine, EconomyLine]


def force_lines(groups: Sequence[ForceGroup], folded: set[str]) -> list[Line]:
    """The groups as a flat list, with the folded ones showing only their header."""
    lines: list[Line] = []
    for group in groups:
        shut = group.name in folded or group.no_match
        lines.append(HeaderLine(group, shut))
        if shut:
            continue
        biggest = group.biggest_row
        for row in group.rows:
            lines.append(TypeLine(row, biggest))
        if group.hidden:
            plural = "types" if group.hidden != 1 else "type"
            lines.append(NoteLine(f"{group.hidden} more {plural} hidden by filter"))
    return lines


def economy_lines(sections: Sequence[EconomySection]) -> list[Line]:
    lines: list[Line] = []
    for section in sections:
        if not section.rows:
            continue
        lines.append(SectionLine(section))
        for row in section.rows:
            lines.append(EconomyLine(row))
    return lines


class IntelListModel(QAbstractListModel):
    """A list of lines. Nothing is stored in roles: the delegate reads the line."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lines: list[Line] = []

    def set_lines(self, lines: Sequence[Line]) -> None:
        self.beginResetModel()
        self._lines = list(lines)
        self.endResetModel()

    def line(self, index: QModelIndex) -> Optional[Line]:
        if not index.isValid() or index.row() >= len(self._lines):
            return None
        return self._lines[index.row()]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._lines)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        # Everything is painted, so the only role worth answering is the one that
        # decides whether a line can be clicked.
        if role == Qt.ItemDataRole.UserRole:
            return self.line(index)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        line = self.line(index)
        if isinstance(line, HeaderLine):
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        return Qt.ItemFlag.ItemIsEnabled


def _font(size: float, demi: bool = False) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(round(size))
    if demi:
        font.setWeight(QFont.Weight.DemiBold)
    return font


def _elided(painter: QPainter, text: str, width: int) -> str:
    return QFontMetrics(painter.font()).elidedText(
        text, Qt.TextElideMode.ElideRight, max(width, 0)
    )


class IntelDelegate(QStyledItemDelegate):
    """Paints every kind of line in all three tabs."""

    def __init__(self, accent: QColor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.accent = accent

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        line = index.data(Qt.ItemDataRole.UserRole)
        heights = {
            HeaderLine: HEADER_HEIGHT,
            TypeLine: ROW_HEIGHT,
            NoteLine: NOTE_HEIGHT,
            SectionLine: SECTION_HEIGHT,
            EconomyLine: ECONOMY_HEIGHT,
        }
        return QSize(option.rect.width(), heights.get(type(line), ROW_HEIGHT))

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        line = index.data(Qt.ItemDataRole.UserRole)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = option.rect
        if isinstance(line, HeaderLine):
            self._header(painter, rect, line, hovered)
        elif isinstance(line, TypeLine):
            self._type_row(painter, rect, line, hovered)
        elif isinstance(line, NoteLine):
            self._note(painter, rect, line)
        elif isinstance(line, SectionLine):
            self._section(painter, rect, line)
        elif isinstance(line, EconomyLine):
            self._economy_row(painter, rect, line, hovered)
        painter.restore()

    # ------------------------------------------------------------- force rows

    def _header(
        self, painter: QPainter, rect: QRect, line: HeaderLine, hovered: bool
    ) -> None:
        group = line.group
        # A base the filter did not match is still listed -- that is an answer -- but
        # it steps back rather than competing with the ones that did.
        painter.setOpacity(0.55 if group.no_match else 1.0)
        painter.fillRect(rect, HOVER_HEADER if hovered else BAND)
        painter.fillRect(rect.left(), rect.bottom(), rect.width(), 1, SEPARATOR)

        painter.setPen(QColor("#8E9DAA"))
        self._chevron(painter, rect, line.folded)

        x = rect.left() + 30
        if group.afloat:
            self._diamond(painter, rect.left() + 30, rect.top() + 14)
            x = rect.left() + 44

        painter.setFont(_font(13, demi=True))
        painter.setPen(QColor("#FFFFFF") if hovered else TEXT)
        name_room = rect.width() - (x - rect.left()) - SHARE_COLUMN - 80
        name = _elided(painter, group.name, name_room)
        painter.drawText(
            QRect(x, rect.top(), name_room, rect.height() - 3),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )
        used = QFontMetrics(painter.font()).horizontalAdvance(name)

        kind = group.kind + (" · no match" if group.no_match else "")
        painter.setFont(_font(11))
        painter.setPen(MUTED)
        painter.drawText(
            QRect(x + used + 10, rect.top(), name_room, rect.height() - 3),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            kind,
        )

        self._right_numbers(
            painter,
            rect,
            share=group.share,
            count=str(group.count),
            count_size=15,
            ink=QColor("#FFFFFF") if hovered else TEXT,
        )
        # The proportion, along the bottom of the header: at forty bases this says
        # where the air force is without a single count being read.
        width = round((rect.width() - 1) * group.share)
        painter.fillRect(rect.left(), rect.bottom() - 2, width, 3, self.accent)
        painter.setOpacity(1.0)

    def _type_row(
        self, painter: QPainter, rect: QRect, line: TypeLine, hovered: bool
    ) -> None:
        row = line.row
        if hovered:
            painter.fillRect(rect, HOVER_ROW)
        x = rect.left() + NAME_INDENT
        room = rect.width() - NAME_INDENT - SHARE_COLUMN - TYPE_BAR_WIDTH - 20

        painter.setFont(_font(12.5))
        painter.setPen(QColor("#FFFFFF") if hovered else BODY)
        name = _elided(painter, row.name, room)
        painter.drawText(
            QRect(x, rect.top(), room, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )
        used = QFontMetrics(painter.font()).horizontalAdvance(name)
        if row.variant:
            painter.setFont(_font(11.5))
            painter.setPen(MUTED)
            painter.drawText(
                QRect(x + used + 6, rect.top(), room, rect.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                row.variant,
            )

        # Relative to the biggest type at this base, grown from the right so it points
        # at its own count: "this base is mostly Hornets", without a second scale.
        right = rect.right() - RIGHT_MARGIN - SHARE_COLUMN + 4
        track = QRect(right - TYPE_BAR_WIDTH, rect.top() + 14, TYPE_BAR_WIDTH, 3)
        painter.fillRect(track, SEPARATOR)
        share = row.count / line.biggest if line.biggest else 0.0
        fill = round(TYPE_BAR_WIDTH * share)
        painter.fillRect(right - fill, track.top(), fill, 3, TYPE_BAR)

        painter.setFont(mono(13))
        painter.setPen(QColor("#FFFFFF") if hovered else TEXT)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width() - RIGHT_MARGIN, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(row.count),
        )

    def _note(self, painter: QPainter, rect: QRect, line: NoteLine) -> None:
        painter.setFont(_font(11))
        painter.setPen(FAINT)
        painter.drawText(
            QRect(
                rect.left() + NAME_INDENT,
                rect.top(),
                rect.width() - NAME_INDENT,
                rect.height(),
            ),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            line.text,
        )

    # ----------------------------------------------------------- economy rows

    def _section(self, painter: QPainter, rect: QRect, line: SectionLine) -> None:
        section = line.section
        painter.fillRect(rect, BAND)
        font = _font(10, demi=True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        painter.setFont(font)
        painter.setPen(self.accent)
        painter.drawText(
            QRect(rect.left() + 16, rect.top(), rect.width(), rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            section.caption,
        )
        painter.setFont(mono(11))
        painter.setPen(MUTED)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width() - RIGHT_MARGIN, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{money(section.subtotal, signed=True)} · {round(section.share * 100)}%",
        )

    def _economy_row(
        self, painter: QPainter, rect: QRect, line: EconomyLine, hovered: bool
    ) -> None:
        row = line.row
        if hovered:
            painter.fillRect(rect, HOVER_ROW)
            painter.fillRect(rect.left(), rect.top(), 2, rect.height(), self.accent)

        painter.setFont(_font(13, demi=True))
        # Damage recedes the name a step rather than shouting: the same rule the air
        # wing uses for a depleted squadron.
        painter.setPen(NAME_DIMMED if row.damage else TEXT)
        painter.drawText(
            QRect(rect.left() + 16, rect.top(), ECONOMY_DETAIL_X - 26, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            _elided(painter, row.name, ECONOMY_DETAIL_X - 26),
        )

        self._detail(painter, rect, row)

        painter.setFont(mono(14))
        painter.setPen(DAMAGE if row.income == 0 else INCOME)
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width() - RIGHT_MARGIN, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            money(row.income, signed=True),
        )

        right = rect.right() - RIGHT_MARGIN
        fill = round(ECONOMY_BAR_WIDTH * row.share)
        painter.fillRect(right - fill, rect.top() + 28, fill, 3, INCOME_BAR)

    def _detail(self, painter: QPainter, rect: QRect, row: EconomyRow) -> None:
        """The grey line, with the damaged fragment in rust. Damage is the only
        coloured text in a row, and it is the reason the row pays what it pays."""
        x = rect.left() + ECONOMY_DETAIL_X
        room = rect.width() - ECONOMY_DETAIL_X - ECONOMY_BAR_WIDTH - 40
        painter.setFont(_font(11.5))
        metrics = QFontMetrics(painter.font())
        pieces = [(row.before, MUTED), (row.damage, DAMAGE), (row.after, MUTED)]

        for text, colour in pieces:
            if not text:
                continue
            if room <= 0:
                break
            painter.setPen(colour)
            drawn = metrics.elidedText(text, Qt.TextElideMode.ElideRight, room)
            painter.drawText(
                QRect(x, rect.top(), room, rect.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                drawn,
            )
            used = metrics.horizontalAdvance(drawn)
            x += used
            room -= used

    # ------------------------------------------------------------------ parts

    def _right_numbers(
        self,
        painter: QPainter,
        rect: QRect,
        share: float,
        count: str,
        count_size: int,
        ink: QColor,
    ) -> None:
        painter.setFont(mono(11))
        painter.setPen(MUTED)
        painter.drawText(
            QRect(
                rect.left(),
                rect.top(),
                rect.width() - RIGHT_MARGIN - SHARE_COLUMN,
                rect.height() - 3,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{round(share * 100)}%",
        )
        painter.setFont(mono(count_size))
        painter.setPen(ink)
        painter.drawText(
            QRect(
                rect.left(),
                rect.top(),
                rect.width() - RIGHT_MARGIN,
                rect.height() - 3,
            ),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            count,
        )

    def _chevron(self, painter: QPainter, rect: QRect, folded: bool) -> None:
        painter.setFont(_font(9))
        painter.drawText(
            QRect(rect.left() + 10, rect.top(), 16, rect.height() - 3),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "▶" if folded else "▼",
        )

    def _diamond(self, painter: QPainter, x: int, y: int) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(self.accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.translate(x + 3, y)
        painter.rotate(45)
        painter.drawRect(-3, -3, 6, 6)
        painter.restore()
