"""The two lists the window is: the aircraft, and one aircraft's points.

Both are drawn by a delegate rather than stacked out of widgets, so a row is one
paint call and eight aircraft with twenty points each cost what one does.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QAbstractTableModel,
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
#: And where the elevation goes, after the longest coordinate string.
ELEVATION_LEFT = 390

#: The room the divider between the type and the flight name takes.
DIVIDER_GAP = 15
#: What the squadron name keeps even when the aircraft type is cut.
MINIMUM_LINK = 60

AIRCRAFT_ROW = 74
POINT_ROW = 36
GROUP_ROW = 26
BANNER = QSize(91, 24)
TEXT_LEFT = 116
MENU_BUTTON = 18
#: How much of the name column the glyph and its margin take.
GLYPH_WIDTH = 28


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
                line.append(f"· {one.flight_name} · {one.package_summary}")
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
        #: Where each link was drawn on each row, to know what was clicked. The
        #: squadron goes to the air wing and the package summary to the package, so
        #: they are two zones rather than one.
        self._squadrons: dict[int, QRect] = {}
        self._packages: dict[int, QRect] = {}

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
            rect.left() + 14, rect.top() + 25, BANNER.width(), BANNER.height()
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
        baseline = rect.top() + 20
        x = _draw(
            painter, x, baseline, one.title, _font(14, QFont.Weight.DemiBold), TITLE_INK
        )
        if one.subtitle:
            _draw(painter, x + 6, baseline, one.subtitle, _font(11), QUIET_INK)

    def _flight_line(
        self, painter: QPainter, rect: QRect, one: Aircraft, row: int
    ) -> None:
        """Two lines under the name: the aeroplane and its squadron, then its package.

        The package gets a line of its own because it never fitted beside the other
        two -- "F/A-18C Hornet (Lot 20)" and a squadron called "Capullos de Alien"
        fill the row on their own -- and it is a link, so a link that is sometimes
        not drawn at all is a link nobody learns to use.
        """
        x = rect.left() + TEXT_LEFT
        baseline = rect.top() + 41
        limit = rect.right() - 90

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
            self._squadrons.pop(row, None)
            self._packages.pop(row, None)
            return

        link_font = _font(12)
        link_font.setUnderline(True)

        def width(font: QFont, text: str) -> int:
            return QFontMetrics(font).horizontalAdvance(text)

        type_text = one.aircraft_name
        squadron_text = one.flight_name
        budget = limit - x - DIVIDER_GAP
        if width(type_font, type_text) + width(link_font, squadron_text) > budget:
            room = min(
                width(link_font, squadron_text),
                max(MINIMUM_LINK, budget - width(type_font, type_text)),
            )
            type_text = _elide(type_font, type_text, budget - room)
            squadron_text = _elide(link_font, squadron_text, room)

        x = _draw(painter, x, baseline, type_text, type_font, TYPE_INK)
        painter.setPen(QColor(DIVIDER))
        painter.drawLine(x + 7, baseline - 10, x + 7, baseline + 2)
        x += DIVIDER_GAP

        start = x
        x = _draw(painter, x, baseline, squadron_text, link_font, WAYPOINT)
        self._squadrons[row] = QRect(start, rect.top() + 28, x - start, 18)

        package_font = _font(11)
        package_font.setUnderline(True)
        package = _elide(
            package_font,
            one.package_summary,
            limit - (rect.left() + TEXT_LEFT),
        )
        start = rect.left() + TEXT_LEFT
        end = _draw(painter, start, rect.top() + 60, package, package_font, WAYPOINT)
        self._packages[row] = QRect(start, rect.top() + 47, end - start, 18)

    def _count(
        self, painter: QPainter, rect: QRect, one: Aircraft, selected: bool
    ) -> None:
        used = one.total_used
        ceiling = one.ceiling
        full = one.total_room <= 0
        right = rect.right() - 14
        baseline = rect.top() + 20
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

        bar = QRect(right - 60, rect.top() + 30, 60, 3)
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

    def clicked_link(self, row: int, point: QPoint, row_top: int) -> Optional[str]:
        """Which link this point landed on, if any: the squadron or the package."""
        for name, zones in (("squadron", self._squadrons), ("package", self._packages)):
            zone = zones.get(row)
            if zone is not None and zone.adjusted(0, row_top, 0, row_top).contains(
                point
            ):
                return name
        return None


# ----------------------------------------------------------------- the points

#: The columns, which the player can widen. A coordinate string is longer in some
#: formats than in others and cutting it makes the number unreadable, so this is a
#: table with a header rather than a list drawn to fixed positions.
NAME, POSITION, ELEVATION, ACTIONS = range(4)
COLUMN_NAMES = ("Point", "Position", "Elev", "")


class PointRow:
    """One line of the points pane: a group header or a point."""

    def __init__(
        self,
        kind: PointKind,
        index: Optional[int] = None,
        point: Optional[Any] = None,
        used: int = 0,
        maximum: int = 0,
        number: int = 0,
    ) -> None:
        self.kind = kind
        self.index = index
        self.point = point
        self.used = used
        self.maximum = maximum
        #: Its place among its own kind, which is what the cockpit shows.
        self.number = number

    @property
    def is_header(self) -> bool:
        return self.point is None


class PointsModel(QAbstractTableModel):
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
                for number, (index, point) in enumerate(held, start=1):
                    self._rows.append(
                        PointRow(kind, index=index, point=point, number=number)
                    )
        self.endResetModel()

    @property
    def aircraft(self) -> Optional[Aircraft]:
        return self._aircraft

    def coordinates_of(self, point: Any) -> str:
        return self._format(point) if self._format is not None else ""

    def header_rows(self) -> list[int]:
        return [row for row, entry in enumerate(self._rows) if entry.is_header]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMN_NAMES)

    def at(self, index: QModelIndex) -> Optional[PointRow]:
        row = index.row()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation is not Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMN_NAMES[section]
        return None

    def _header_text(self, row: PointRow) -> str:
        # A kind the aircraft cannot be given says so rather than reading "2 / 0".
        count = (
            f"{row.used} / {row.maximum}"
            if row.maximum
            else f"{row.used} · kneeboard only"
        )
        return f"{row.kind.label.upper()}S     {count}"

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        row = self.at(index)
        if row is None:
            return None
        column = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return row

        if row.is_header:
            if role == Qt.ItemDataRole.DisplayRole and column == NAME:
                return self._header_text(row)
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(kind_colour(row.kind))
            if role == Qt.ItemDataRole.FontRole:
                font = _font(10, QFont.Weight.Bold)
                font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
                return font
            return None

        letter = "W" if row.kind is PointKind.WAYPOINT else "MK"
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if column == NAME:
                if role == Qt.ItemDataRole.EditRole:
                    return row.point.name
                name = row.point.name or "Unnamed — click to name"
                return f"{letter}{row.number}   {name}"
            if column == POSITION:
                return self.coordinates_of(row.point)
            if column == ELEVATION:
                if role == Qt.ItemDataRole.EditRole:
                    return str(row.point.altitude_ft or "")
                return f"{row.point.altitude_ft} ft" if row.point.altitude_ft else "—"
            return ""
        if role == Qt.ItemDataRole.FontRole:
            if column == NAME:
                font = _font(13, QFont.Weight.DemiBold)
                font.setItalic(not row.point.name)
                return font
            return _mono(11)
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == NAME:
                return QColor(TITLE_INK if row.point.name else FAINT_INK)
            if column == ELEVATION and not row.point.altitude_ft:
                return QColor(FAINT_INK)
            return QColor(QUIET_INK)
        if role == Qt.ItemDataRole.ToolTipRole and column == ELEVATION:
            return (
                "Above sea level, and typed in: nothing outside a running mission"
                " tells the application how high the ground is. A weapon aimed at a"
                " point from the wrong elevation lands short or long."
            )
        return None

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        row = self.at(index)
        if row is None or row.is_header or role != Qt.ItemDataRole.EditRole:
            return False
        if index.column() == NAME:
            name = str(value).strip()[:NAME_LENGTH]
            if name:
                row.point.name = name
                self.dataChanged.emit(index, index)
            return True
        if index.column() == ELEVATION:
            text = str(value).strip().replace(",", ".")
            try:
                row.point.altitude_ft = max(0, round(float(text))) if text else 0
            except ValueError:
                return False
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        row = self.at(index)
        if row is None or row.is_header:
            return Qt.ItemFlag.ItemIsEnabled
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() in (NAME, ELEVATION):
            return base | Qt.ItemFlag.ItemIsEditable
        return base


def kind_colour(kind: PointKind) -> str:
    return WAYPOINT if kind is PointKind.WAYPOINT else MARKPOINT


class PointDelegate(QStyledItemDelegate):
    """The row's background, its glyph and its button.

    The text is drawn here too, but from what the model says rather than at fixed
    positions, so each column elides at whatever width the player has dragged it to.
    """

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
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        if row.is_header:
            painter.fillRect(option.rect, QColor(HEADER_BG))
        else:
            background = SELECTED_BG if selected else (HOVER_BG if hovered else ROW_BG)
            painter.fillRect(option.rect, QColor(background))
            painter.setPen(QColor(DIVIDER))
            painter.drawLine(
                option.rect.left(),
                option.rect.bottom(),
                option.rect.right(),
                option.rect.bottom(),
            )
        painter.restore()

        if row.is_header:
            self._text(painter, option, index, indent=12)
            return
        if index.column() == NAME:
            self._glyph(painter, option.rect, row)
            self._text(painter, option, index, indent=GLYPH_WIDTH)
        elif index.column() == ACTIONS:
            _draw(
                painter,
                option.rect.right() - 12 - MENU_BUTTON,
                option.rect.top() + 23,
                "···",
                _font(14),
                FAINT_INK,
            )
        else:
            self._text(painter, option, index, indent=8)

    def _glyph(self, painter: QPainter, rect: QRect, row: PointRow) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = QPoint(rect.left() + 14, rect.top() + 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(kind_colour(row.kind)))
        if row.kind is PointKind.WAYPOINT:
            painter.drawEllipse(centre, 4, 4)
        else:
            painter.translate(centre)
            painter.rotate(45)
            painter.drawRect(QRect(-4, -4, 8, 8))
        painter.restore()

    def _text(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        indent: int,
    ) -> None:
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return
        font = index.data(Qt.ItemDataRole.FontRole) or _font(12)
        ink = index.data(Qt.ItemDataRole.ForegroundRole) or QColor(BODY_INK)
        room = option.rect.adjusted(indent, 0, -8, 0)
        painter.save()
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(
            room,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            QFontMetrics(font).elidedText(
                str(text), Qt.TextElideMode.ElideRight, room.width()
            ),
        )
        painter.restore()

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        editor = QLineEdit(parent)
        if index.column() == NAME:
            editor.setMaxLength(NAME_LENGTH)
        editor.setFont(_mono(13))
        editor.setStyleSheet(
            f"QLineEdit {{ background: #0F1922; color: {TITLE_INK};"
            f" border: 1px solid {WAYPOINT}; padding: 1px 4px; }}"
        )
        return editor

    @staticmethod
    def on_menu_button(rect: QRect, point: QPoint) -> bool:
        """Whether this point of the row is on its button."""
        return point.x() >= rect.right() - 12 - MENU_BUTTON - 6
