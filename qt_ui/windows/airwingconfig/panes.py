"""The two side panes: what this coalition flies, and where it all fits.

The types list answers "what do we fly, and how much of it" without opening a page per
type, and marks the ones the campaign gave no squadron. The bases pane is the one the
old form did not have at all: parking was a grey line at the bottom of one group box,
and going over it was the commonest mistake in this window.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from game.dcs.aircrafttype import AircraftType
from game.squadrons import AirWing, Squadron
from game.theater import ControlPoint, ParkingType
from qt_ui.uiconstants import AIRCRAFT_ICONS
from .common import (
    ACCENT,
    AMBER,
    BAR_OTHERS,
    BAR_TRACK,
    GREEN,
    RED,
    AirWingConfigParkingTracker,
)

DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1

TYPE_ROW_HEIGHT = 48
BASE_ROW_HEIGHT = 60

HOVER_FILL = QColor("#1A2A38")
SELECTED_FILL = QColor("#1E3A52")
SEPARATOR = QColor("#1D2731")
TEXT_PRIMARY = QColor("#F2F7FA")
TEXT_SECONDARY = QColor("#B7C6D2")
TEXT_LABEL = QColor("#7C8B99")
TEXT_MUTED = QColor("#6B7A87")
TEXT_TERTIARY = QColor("#8E9DAA")
DIMMED_NAME = QColor("#A9B7C3")


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


def _mono(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Consolas")
    font.setPointSizeF(size)
    font.setWeight(weight)
    return font


def _paint_row_background(
    painter: QPainter, option: QStyleOptionViewItem, height: int
) -> None:
    rect = option.rect
    if option.state & QStyle.StateFlag.State_Selected:
        painter.fillRect(rect, SELECTED_FILL)
    elif option.state & QStyle.StateFlag.State_MouseOver:
        painter.fillRect(rect, HOVER_FILL)
    painter.setPen(SEPARATOR)
    painter.drawLine(
        rect.left(), rect.top() + height - 1, rect.right(), rect.top() + height - 1
    )


class AircraftTypeDelegate(QStyledItemDelegate):
    """One aircraft type: its banner, how many squadrons, how many aircraft."""

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), TYPE_ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_row_background(painter, option, TYPE_ROW_HEIGHT)
        rect = option.rect
        data = index.data(DATA_ROLE) or {}
        aircraft: Optional[AircraftType] = data.get("aircraft")
        squadrons = data.get("squadrons", 0)
        planes = data.get("aircraft_count", 0)

        if aircraft is not None:
            name = aircraft.dcs_id.replace("/", "_")
            if name in AIRCRAFT_ICONS:
                pixmap = QPixmap(AIRCRAFT_ICONS[name]).scaled(
                    91,
                    24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not squadrons:
                    painter.setOpacity(0.4)
                painter.drawPixmap(rect.left() + 14, rect.top() + 12, pixmap)
                painter.setOpacity(1.0)

        painter.setFont(_font(9.5, QFont.Weight.DemiBold))
        painter.setPen(TEXT_PRIMARY if squadrons else DIMMED_NAME)
        text = aircraft.display_name if aircraft is not None else ""
        room = rect.width() - 116 - 10
        text = QFontMetrics(_font(9.5, QFont.Weight.DemiBold)).elidedText(
            text, Qt.TextElideMode.ElideRight, room
        )
        painter.drawText(rect.left() + 116, rect.top() + 20, text)

        painter.setFont(_font(8.5))
        if squadrons:
            painter.setPen(TEXT_SECONDARY)
            plural = "sqn" if squadrons == 1 else "sqns"
            painter.drawText(
                rect.left() + 116,
                rect.top() + 38,
                f"{squadrons} {plural} · {planes} aircraft",
            )
        else:
            painter.setPen(QColor(AMBER))
            painter.drawText(rect.left() + 116, rect.top() + 38, "▲ no squadron yet")
        painter.restore()


class AircraftTypeList(QListView):
    """Every type the coalition can field, the ones it flies first."""

    type_selected = Signal(object)

    def __init__(self, air_wing: AirWing) -> None:
        super().__init__()
        self.air_wing = air_wing
        self.setItemDelegate(AircraftTypeDelegate())
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setFixedWidth(300)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.refresh()

    def refresh(self, keep: Optional[AircraftType] = None) -> None:
        keep = keep or self.selected_type()
        self.item_model.clear()
        for aircraft in sorted(self.air_wing.squadrons, key=lambda a: a.display_name):
            squadrons = self.air_wing.squadrons[aircraft]
            item = QStandardItem()
            item.setEditable(False)
            item.setData(
                {
                    "aircraft": aircraft,
                    "squadrons": len(squadrons),
                    "aircraft_count": sum(s.max_size for s in squadrons),
                },
                DATA_ROLE,
            )
            self.item_model.appendRow(item)
        if self.item_model.rowCount():
            row = 0
            if keep is not None:
                for candidate in range(self.item_model.rowCount()):
                    data = self.item_model.item(candidate).data(DATA_ROLE)
                    if data and data.get("aircraft") == keep:
                        row = candidate
                        break
            self.setCurrentIndex(self.item_model.index(row, 0))

    def selected_type(self) -> Optional[AircraftType]:
        index = self.currentIndex()
        if not index.isValid():
            return None
        item = self.item_model.item(index.row())
        data = item.data(DATA_ROLE) if item is not None else None
        return data.get("aircraft") if data else None

    def _on_selection_changed(self) -> None:
        self.type_selected.emit(self.selected_type())


class BaseDelegate(QStyledItemDelegate):
    """One base: how many squadrons, how much parking, how close to full."""

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), BASE_ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_row_background(painter, option, BASE_ROW_HEIGHT)
        rect = option.rect
        data = index.data(DATA_ROLE) or {}
        name = data.get("name", "")
        squadrons = data.get("squadrons", 0)
        used = data.get("used", 0)
        total = data.get("total", 0)
        mine = data.get("mine", 0)
        note = data.get("note", "")
        empty = squadrons == 0

        painter.setFont(_font(9.5, QFont.Weight.DemiBold))
        painter.setPen(TEXT_MUTED if empty else TEXT_PRIMARY)
        painter.drawText(rect.left() + 12, rect.top() + 20, name)

        painter.setFont(_font(8))
        painter.setPen(TEXT_MUTED if empty else TEXT_LABEL)
        offset = QFontMetrics(_font(9.5, QFont.Weight.DemiBold)).horizontalAdvance(name)
        plural = "sqn" if squadrons == 1 else "sqns"
        painter.drawText(
            rect.left() + 20 + offset,
            rect.top() + 20,
            "empty" if empty else f"{squadrons} {plural}",
        )

        over = used - total
        used_colour = (
            QColor(RED)
            if over > 0
            else (QColor(AMBER) if total and used / total >= 0.85 else TEXT_SECONDARY)
        )
        painter.setFont(_mono(9.5, QFont.Weight.DemiBold))
        used_text = str(used)
        total_text = f" / {total}"
        total_width = QFontMetrics(_font(8)).horizontalAdvance(total_text)
        used_width = QFontMetrics(_mono(9.5, QFont.Weight.DemiBold)).horizontalAdvance(
            used_text
        )
        right = rect.right() - 12
        painter.setPen(used_colour)
        painter.drawText(right - total_width - used_width, rect.top() + 20, used_text)
        painter.setFont(_font(8))
        painter.setPen(TEXT_LABEL)
        painter.drawText(right - total_width, rect.top() + 20, total_text)

        # The bar: everyone else, then this type's squadrons on top of them.
        bar = QRect(rect.left() + 12, rect.top() + 32, rect.width() - 24, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillRect(bar, QColor(BAR_TRACK))
        if total > 0:
            others = max(0, used - mine)
            others_w = int(bar.width() * min(1.0, others / total))
            mine_w = int(bar.width() * min(1.0, mine / total))
            fill = QColor(RED) if over > 0 else QColor(BAR_OTHERS)
            painter.fillRect(QRect(bar.left(), bar.top(), others_w, 6), fill)
            painter.fillRect(
                QRect(
                    bar.left() + others_w,
                    bar.top(),
                    min(mine_w, bar.width() - others_w),
                    6,
                ),
                QColor(RED) if over > 0 else QColor(ACCENT),
            )
        if over > 0:
            painter.fillRect(
                QRect(rect.left(), rect.top(), 3, BASE_ROW_HEIGHT), QColor(RED)
            )

        painter.setFont(_font(8))
        if over > 0:
            painter.setPen(QColor(RED))
        elif empty:
            painter.setPen(TEXT_MUTED)
        else:
            painter.setPen(TEXT_TERTIARY)
        painter.drawText(rect.left() + 12, rect.top() + 52, note)
        painter.restore()


class BasesPane(QListView):
    """Every base this coalition has, and how full each one is."""

    base_selected = Signal(object)

    def __init__(
        self,
        control_points: Iterable[ControlPoint],
        parking_tracker: AirWingConfigParkingTracker,
        ground_start_ai_planes: bool,
    ) -> None:
        super().__init__()
        self.control_points = list(control_points)
        self.parking_tracker = parking_tracker
        self.ground_start_ai_planes = ground_start_ai_planes
        self.highlight_type: Optional[AircraftType] = None
        self.setItemDelegate(BaseDelegate())
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setFixedWidth(300)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.item_model = QStandardItemModel(self)
        self.setModel(self.item_model)
        self.clicked.connect(self._on_clicked)
        self.parking_tracker.allocation_changed.connect(self.refresh)
        self.refresh()

    def total_parking(self, control_point: ControlPoint) -> int:
        """Every slot the base has, of any shape.

        The pane answers "does the wing fit here", which is a question about the base;
        whether a particular airframe fits a particular slot is answered in the
        squadron card, against that squadron's own type.
        """
        return control_point.total_aircraft_parking(
            ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
        )

    def bases_over_capacity(self) -> int:
        return sum(
            1
            for cp in self.control_points
            if self.parking_tracker.used_parking_at(cp) > self.total_parking(cp)
        )

    def refresh(self) -> None:
        selected = self.selected_base()
        self.item_model.clear()
        rows = []
        for cp in self.control_points:
            squadrons = self.parking_tracker.squadrons_at(cp)
            used = sum(s.max_size for s in squadrons)
            total = self.total_parking(cp)
            mine = sum(
                s.max_size
                for s in squadrons
                if self.highlight_type is not None and s.aircraft == self.highlight_type
            )
            over = used - total
            if over > 0:
                note = f"{over} over — move a squadron or lower a max size"
            elif not squadrons:
                note = "no squadrons based here"
            elif total and used / total >= 0.85:
                note = f"{total - used} free — nearly full"
            else:
                note = f"{total - used} free"
            rows.append(
                {
                    "cp": cp,
                    "name": cp.name,
                    "squadrons": len(squadrons),
                    "used": used,
                    "total": total,
                    "mine": mine,
                    "note": note,
                    "over": over,
                }
            )
        # The ones in trouble first, then the busiest: the pane is there to be glanced
        # at, and an empty base is never the answer to a question.
        rows.sort(key=lambda row: (0 if row["over"] > 0 else 1, -row["used"]))
        for row in rows:
            item = QStandardItem()
            item.setEditable(False)
            item.setData(row, DATA_ROLE)
            self.item_model.appendRow(item)
        if selected is not None:
            for candidate in range(self.item_model.rowCount()):
                data = self.item_model.item(candidate).data(DATA_ROLE)
                if data and data.get("cp") == selected:
                    self.setCurrentIndex(self.item_model.index(candidate, 0))
                    break

    def selected_base(self) -> Optional[ControlPoint]:
        index = self.currentIndex()
        if not index.isValid():
            return None
        item = self.item_model.item(index.row())
        data = item.data(DATA_ROLE) if item is not None else None
        return data.get("cp") if data else None

    def set_highlight_type(self, aircraft: Optional[AircraftType]) -> None:
        self.highlight_type = aircraft
        self.refresh()

    def _on_clicked(self, index: QModelIndex) -> None:
        item = self.item_model.item(index.row())
        data = item.data(DATA_ROLE) if item is not None else None
        self.base_selected.emit(data.get("cp") if data else None)
