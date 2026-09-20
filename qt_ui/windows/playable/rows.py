"""The two lists the window is: the aircraft, and one aircraft's points.

Both are drawn by a delegate rather than stacked out of widgets, so a row is one
paint call and eight aircraft with twenty points each cost what one does.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from game.ato.savedpoints import PointKind
from qt_ui.uiconstants import AIRCRAFT_ICONS
from qt_ui.widgets.controls import mono
from qt_ui.windows.playable.model import Aircraft, NAME_LENGTH

# The window's palette. Everything but the first three is the shared one.
WAYPOINT = "#8FC3F0"
MARKPOINT = "#E0A86B"
HELICOPTER = "#86C39A"
DANGER_TEXT = "#E08A7A"

ROW_BG = "#14202B"
HOVER_BG = "#1A2A38"
SELECTED_BG = "#1E3A52"
HEADER_BG = "#182734"
DIVIDER = "#1D2731"
IDLE_BAR = "#3F5D73"

TITLE_INK = "#F2F7FA"
BODY_INK = "#D3DFE8"
TYPE_INK = "#B7C6D2"
QUIET_INK = "#7C8B99"
FAINT_INK = "#6B7A87"

#: Where the coordinates column starts, which is also where a name is cut.
COORDINATES_LEFT = 210

#: The room the divider between the type and the flight name takes.
DIVIDER_GAP = 15
#: What the flight name keeps even when the type is cut, and what the context needs
#: before it is shown at all.
MINIMUM_LINK = 60
MINIMUM_CONTEXT = 30

AIRCRAFT_ROW = 56
POINT_ROW = 36
GROUP_ROW = 26
BANNER = QSize(91, 24)
TEXT_LEFT = 116
MENU_BUTTON = 18


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The application's face, named the way the rest of the redesigned windows name
    it: a bare QFont() resolves to whatever Qt finds first, which on a machine
    without it is a face with no glyphs at all."""
    font = QFont("Segoe UI")
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _mono(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = mono(size)
    font.setWeight(weight)
    return font


def _elide(font: QFont, text: str, room: int) -> str:
    """The text, cut to fit. Nothing at all when there is no room to cut it to."""
    if room <= 0:
        return ""
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, room)


def _draw(
    painter: QPainter, x: int, baseline: int, text: str, font: QFont, ink: str
) -> int:
    """Write one run and return where the next one starts."""
    painter.setFont(font)
    painter.setPen(QColor(ink))
    painter.drawText(QPoint(x, baseline), text)
    return x + QFontMetrics(font).horizontalAdvance(text)


# --------------------------------------------------------------- the aircraft


class AircraftModel(QAbstractListModel):
    """The aircraft the player is flying, one per row."""

    def __init__(self, aircraft: list[Aircraft]) -> None:
        super().__init__()
        self._aircraft = aircraft

    def set_aircraft(self, aircraft: list[Aircraft]) -> None:
        self.beginResetModel()
        self._aircraft = aircraft
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._aircraft)

    def at(self, index: QModelIndex) -> Optional[Aircraft]:
        row = index.row()
        if 0 <= row < len(self._aircraft):
            return self._aircraft[row]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        one = self.at(index)
        if one is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return one.title
        if role == Qt.ItemDataRole.EditRole:
            return one.alias or ""
        if role == Qt.ItemDataRole.UserRole:
            return one
        if role == Qt.ItemDataRole.ToolTipRole:
            # The row cuts the type and the flight name to fit; this is the whole
            # sentence, for the aircraft whose squadron has a long name.
            line = [one.title]
            if one.subtitle:
                line.append(f"({one.subtitle})")
            line.append("·")
            line.append(one.aircraft_name)
            if one.assigned:
                line.append(f"· {one.flight_name} · {one.task}")
                if one.target:
                    line.append(f"· {one.target}")
                if one.tot:
                    line.append(f"· {one.tot}")
            else:
                line.append("· no flight this turn")
            return " ".join(line)
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        one = self.at(index)
        if one is None or role != Qt.ItemDataRole.EditRole:
            return False
        one.rename(str(value))
        self.dataChanged.emit(index, index)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )


class AircraftDelegate(QStyledItemDelegate):
    """A row: banner, name over flight, and how full it is."""

    #: Emitted when the flight name itself was clicked, as opposed to the row.
    flight_clicked = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        #: Where the flight name was drawn on each row, to know what was clicked.
        self._links: dict[int, QRect] = {}

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), AIRCRAFT_ROW)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        one = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(one, Aircraft):
            return
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = SELECTED_BG if selected else (HOVER_BG if hovered else ROW_BG)
        painter.fillRect(rect, QColor(background))
        if selected or hovered:
            painter.fillRect(
                QRect(rect.left(), rect.top(), 3, rect.height()),
                QColor(WAYPOINT if selected else IDLE_BAR),
            )
        painter.setPen(QColor(DIVIDER))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        self._banner(painter, rect, one)
        self._title(painter, rect, one)
        self._flight_line(painter, rect, one, index.row())
        self._count(painter, rect, one, selected)
        painter.restore()

    def _banner(self, painter: QPainter, rect: QRect, one: Aircraft) -> None:
        pixmap = AIRCRAFT_ICONS.get(one.dcs_id)
        where = QRect(
            rect.left() + 14, rect.top() + 16, BANNER.width(), BANNER.height()
        )
        if pixmap is None:
            painter.setPen(QColor(DIVIDER))
            painter.drawRect(where)
            return
        # An aircraft with no flight this turn recedes rather than looking broken.
        painter.setOpacity(1.0 if one.assigned else 0.5)
        painter.drawPixmap(
            where,
            pixmap.scaled(
                BANNER,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )
        painter.setOpacity(1.0)

    def _title(self, painter: QPainter, rect: QRect, one: Aircraft) -> None:
        x = rect.left() + TEXT_LEFT
        baseline = rect.top() + 21
        x = _draw(
            painter, x, baseline, one.title, _font(14, QFont.Weight.DemiBold), TITLE_INK
        )
        if one.subtitle:
            _draw(painter, x + 6, baseline, one.subtitle, _font(11), QUIET_INK)

    def _flight_line(
        self, painter: QPainter, rect: QRect, one: Aircraft, row: int
    ) -> None:
        """Type · flight · task · target · time, in one line that always fits.

        The time is pinned to the right and never shrinks. What gives way, in order,
        is the task and target, then the flight name, then the aircraft type: a 400 px
        pane cannot hold "F/A-18C Hornet (Lot 20)" and a squadron called "Capullos de
        Alien" and a target as well, and of the three the aeroplane is what a player
        scanning the list is looking for.
        """
        x = rect.left() + TEXT_LEFT
        baseline = rect.top() + 43
        right = rect.right() - 90

        tot_font = _mono(11)
        tot_width = (
            QFontMetrics(tot_font).horizontalAdvance(one.tot) + 8 if one.tot else 0
        )
        if one.tot:
            _draw(
                painter, right - tot_width + 8, baseline, one.tot, tot_font, QUIET_INK
            )
        limit = right - tot_width

        if one.is_helicopter:
            painter.setPen(QPen(QColor(HELICOPTER), 1.5))
            painter.drawEllipse(QPoint(x + 3, baseline - 4), 3, 3)
            x += 12

        type_font = _font(12)
        if not one.assigned:
            italic = _font(12)
            italic.setItalic(True)
            note = " No flight this turn"
            note_width = QFontMetrics(italic).horizontalAdvance(note)
            x = _draw(
                painter,
                x,
                baseline,
                _elide(type_font, one.aircraft_name, limit - x - note_width),
                type_font,
                TYPE_INK,
            )
            _draw(painter, x, baseline, note, italic, QUIET_INK)
            self._links.pop(row, None)
            return

        link_font = _font(12)
        link_font.setUnderline(True)
        context_font = _font(11)

        def width(font: QFont, text: str) -> int:
            return QFontMetrics(font).horizontalAdvance(text)

        context = f" · {one.task}"
        if one.target:
            context += f" · {one.target}"
        available = limit - x - DIVIDER_GAP

        type_text = one.aircraft_name
        link_text = one.flight_name
        type_natural = width(type_font, type_text)
        link_natural = width(link_font, link_text)

        # The task and the target are shown only out of what is left over.
        spare = available - type_natural - link_natural
        context = (
            _elide(context_font, context, spare) if spare >= MINIMUM_CONTEXT else ""
        )
        budget = available - width(context_font, context)

        if type_natural + link_natural > budget:
            # The flight name keeps enough to be read and clicked; the type takes
            # whatever remains, which is still the more useful of the two cut.
            link_room = min(link_natural, max(MINIMUM_LINK, budget - type_natural))
            type_text = _elide(type_font, type_text, budget - link_room)
            link_text = _elide(link_font, link_text, link_room)

        x = _draw(painter, x, baseline, type_text, type_font, TYPE_INK)
        painter.setPen(QColor(DIVIDER))
        painter.drawLine(x + 7, baseline - 10, x + 7, baseline + 2)
        x += DIVIDER_GAP

        start = x
        x = _draw(painter, x, baseline, link_text, link_font, WAYPOINT)
        self._links[row] = QRect(start, rect.top() + 30, x - start, 18)
        if context:
            _draw(painter, x, baseline, context, context_font, QUIET_INK)

    def _count(
        self, painter: QPainter, rect: QRect, one: Aircraft, selected: bool
    ) -> None:
        used = one.total_used
        ceiling = one.ceiling
        full = one.total_room <= 0
        right = rect.right() - 14
        baseline = rect.top() + 21
        used_font = _mono(15, QFont.Weight.DemiBold)

        if ceiling == 0:
            # Nothing loads a point into this airframe, so there is no ceiling to
            # count against: what it has is what is written on its kneeboard.
            _draw(
                painter,
                right - QFontMetrics(used_font).horizontalAdvance(str(used)),
                baseline,
                str(used),
                used_font,
                FAINT_INK,
            )
            return

        ink = FAINT_INK if used == 0 else (MARKPOINT if full else TITLE_INK)
        rest = f" / {ceiling}"
        rest_font = _mono(11)
        rest_width = QFontMetrics(rest_font).horizontalAdvance(rest)
        _draw(painter, right - rest_width, baseline, rest, rest_font, QUIET_INK)

        used_width = QFontMetrics(used_font).horizontalAdvance(str(used))
        _draw(
            painter,
            right - rest_width - used_width,
            baseline,
            str(used),
            used_font,
            ink,
        )

        bar = QRect(right - 60, rect.top() + 33, 60, 3)
        painter.fillRect(bar, QColor(DIVIDER))
        if used > 0:
            filled = max(2, int(60 * min(used / ceiling, 1.0)))
            colour = MARKPOINT if full else (WAYPOINT if selected else IDLE_BAR)
            painter.fillRect(QRect(bar.left(), bar.top(), filled, 3), QColor(colour))

    # ------------------------------------------------------- renaming in place

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QLineEdit(parent)
        editor.setMaxLength(NAME_LENGTH)
        editor.setFont(_font(14, QFont.Weight.DemiBold))
        editor.setStyleSheet(
            f"QLineEdit {{ background: #0F1922; color: {TITLE_INK};"
            f" border: 1px solid {WAYPOINT}; padding: 1px 4px; }}"
        )
        return editor

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        rect = option.rect
        editor.setGeometry(QRect(rect.left() + TEXT_LEFT - 4, rect.top() + 6, 150, 22))

    def link_at(self, row: int, point: QPoint, row_top: int) -> bool:
        """Whether this point is on the flight name of that row."""
        link = self._links.get(row)
        if link is None:
            return False
        return link.adjusted(0, row_top, 0, row_top).contains(point)


# ----------------------------------------------------------------- the points


class PointRow:
    """One line of the points pane: a group header or a point."""

    def __init__(
        self,
        kind: PointKind,
        index: Optional[int] = None,
        point: Optional[Any] = None,
        used: int = 0,
        maximum: int = 0,
    ) -> None:
        self.kind = kind
        self.index = index
        self.point = point
        self.used = used
        self.maximum = maximum

    @property
    def is_header(self) -> bool:
        return self.point is None


class PointsModel(QAbstractListModel):
    """One aircraft's points, grouped by kind."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[PointRow] = []
        self._aircraft: Optional[Aircraft] = None
        self._format: Any = None

    def show(self, aircraft: Optional[Aircraft], coordinates: Any) -> None:
        self.beginResetModel()
        self._aircraft = aircraft
        self._format = coordinates
        self._rows = []
        if aircraft is not None:
            for kind in aircraft.kinds:
                held = aircraft.of_kind(kind)
                self._rows.append(
                    PointRow(kind, used=len(held), maximum=aircraft.maximum(kind))
                )
                for index, point in held:
                    self._rows.append(PointRow(kind, index=index, point=point))
        self.endResetModel()

    @property
    def aircraft(self) -> Optional[Aircraft]:
        return self._aircraft

    def coordinates_of(self, point: Any) -> str:
        return self._format(point) if self._format is not None else ""

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def at(self, index: QModelIndex) -> Optional[PointRow]:
        row = index.row()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        row = self.at(index)
        if row is None:
            return None
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return "" if row.is_header else row.point.name
        if role == Qt.ItemDataRole.EditRole:
            return "" if row.is_header else row.point.name
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        row = self.at(index)
        if row is None or row.is_header or self._aircraft is None:
            return False
        name = str(value).strip()[:NAME_LENGTH]
        if name:
            row.point.name = name
            self.dataChanged.emit(index, index)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        row = self.at(index)
        if row is None or row.is_header:
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )


def kind_colour(kind: PointKind) -> str:
    return WAYPOINT if kind is PointKind.WAYPOINT else MARKPOINT


class PointDelegate(QStyledItemDelegate):
    """A point: its glyph, its index, its name and its coordinates."""

    def __init__(self, model: PointsModel, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._model = model

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        row = index.data(Qt.ItemDataRole.UserRole)
        height = GROUP_ROW if isinstance(row, PointRow) and row.is_header else POINT_ROW
        return QSize(option.rect.width(), height)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        row = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row, PointRow):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if row.is_header:
            self._header(painter, option.rect, row)
        else:
            self._point(painter, option, row)
        painter.restore()

    def _header(self, painter: QPainter, rect: QRect, row: PointRow) -> None:
        painter.fillRect(rect, QColor(HEADER_BG))
        font = _font(10, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
        _draw(
            painter,
            rect.left() + 12,
            rect.top() + 17,
            f"{row.kind.label.upper()}S",
            font,
            kind_colour(row.kind),
        )
        # A kind the aircraft cannot be given says so rather than reading "2 / 0".
        count = (
            f"{row.used} / {row.maximum}"
            if row.maximum
            else f"{row.used} · kneeboard only"
        )
        counter = _mono(11)
        width = QFontMetrics(counter).horizontalAdvance(count)
        _draw(
            painter,
            rect.right() - 12 - width,
            rect.top() + 17,
            count,
            counter,
            MARKPOINT if row.maximum and row.used >= row.maximum else QUIET_INK,
        )

    def _point(
        self, painter: QPainter, option: QStyleOptionViewItem, row: PointRow
    ) -> None:
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.fillRect(
            rect, QColor(SELECTED_BG if selected else (HOVER_BG if hovered else ROW_BG))
        )
        painter.setPen(QColor(DIVIDER))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        colour = kind_colour(row.kind)
        centre = QPoint(rect.left() + 16, rect.top() + 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        if row.kind is PointKind.WAYPOINT:
            painter.drawEllipse(centre, 4, 4)
        else:
            painter.save()
            painter.translate(centre)
            painter.rotate(45)
            painter.drawRect(QRect(-4, -4, 8, 8))
            painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)

        letter = "W" if row.kind is PointKind.WAYPOINT else "M"
        number = self._numbering(row)
        _draw(
            painter,
            rect.left() + 30,
            rect.top() + 22,
            f"{letter}{number}",
            _mono(11),
            QUIET_INK,
        )

        name = row.point.name
        font = _font(13, QFont.Weight.DemiBold)
        ink = TITLE_INK
        if not name:
            name = "Unnamed — click to name"
            font = _font(13)
            font.setItalic(True)
            ink = FAINT_INK
        # The coordinates keep their column: a long name is cut rather than running
        # into them.
        room = COORDINATES_LEFT - 56 - 10
        _draw(
            painter,
            rect.left() + 56,
            rect.top() + 22,
            QFontMetrics(font).elidedText(name, Qt.TextElideMode.ElideRight, room),
            font,
            ink,
        )

        coordinates = self._model.coordinates_of(row.point)
        if coordinates:
            _draw(
                painter,
                rect.left() + COORDINATES_LEFT,
                rect.top() + 22,
                coordinates,
                _mono(11),
                QUIET_INK,
            )

        _draw(
            painter,
            rect.right() - 12 - MENU_BUTTON,
            rect.top() + 23,
            "···",
            _font(14),
            FAINT_INK,
        )

    def _numbering(self, row: PointRow) -> int:
        """The point's place among its own kind, which is what the cockpit shows."""
        aircraft = self._model.aircraft
        if aircraft is None or row.index is None:
            return 1
        for place, (index, _point) in enumerate(aircraft.of_kind(row.kind), start=1):
            if index == row.index:
                return place
        return 1

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QLineEdit(parent)
        editor.setMaxLength(NAME_LENGTH)
        editor.setFont(_mono(13))
        editor.setStyleSheet(
            f"QLineEdit {{ background: #0F1922; color: {TITLE_INK};"
            f" border: 1px solid {WAYPOINT}; padding: 1px 4px; }}"
        )
        return editor

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        rect = option.rect
        editor.setGeometry(QRect(rect.left() + 52, rect.top() + 6, 150, 24))

    @staticmethod
    def on_menu_button(rect: QRect, point: QPoint) -> bool:
        """Whether this point of the row is on its ··· button."""
        return point.x() >= rect.right() - 12 - MENU_BUTTON - 6
