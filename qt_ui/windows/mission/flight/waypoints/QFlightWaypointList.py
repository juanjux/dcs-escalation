from typing import Optional, Sequence

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QHeaderView,
    QTableView,
    QStyledItemDelegate,
    QWidget,
    QStyleOptionViewItem,
    QDoubleSpinBox,
)

from game.ato.flight import Flight
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.package import Package
from game.utils import Distance, meters
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointItem import QWaypointItem

HEADER_LABELS = ["Name", "Alt (ft)", "Alt Type", "TOT/DEPART", "Leg (nm)"]

#: Set on a group header row: the index of the first waypoint it stands for.
GroupStartRole = Qt.ItemDataRole.UserRole + 7

#: The dot in front of a waypoint's name, and whether it is drawn hollow.
DotColourRole = Qt.ItemDataRole.UserRole + 8
DotOutlineRole = Qt.ItemDataRole.UserRole + 9

#: Targets are the one thing on the route you are there for.
TARGET_AMBER = "#E0A86B"

#: Not on the ground track, so they neither start a leg nor end one: a map reference,
#: an alternate field, and the target points, which are engaged from the ingress
#: rather than overflown.
#: Consecutive waypoints of these types are one thing you attack, not a dozen
#: places you fly to, so the table folds them into a single row you can open. A DEAD
#: run on a Patriot site was thirteen rows reading "STRIKE Patriot ln #6".
TARGET_TYPES = frozenset(
    {
        FlightWaypointType.TARGET_POINT,
        FlightWaypointType.TARGET_GROUP_LOC,
        FlightWaypointType.TARGET_SHIP,
    }
)

NOT_FLOWN = frozenset(
    {
        FlightWaypointType.BULLSEYE,
        FlightWaypointType.DIVERT,
        FlightWaypointType.TARGET_POINT,
        FlightWaypointType.TARGET_GROUP_LOC,
        FlightWaypointType.TARGET_SHIP,
    }
)


class AltitudeEditorDelegate(QStyledItemDelegate):
    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QDoubleSpinBox:
        editor = QDoubleSpinBox(parent)
        editor.setMinimum(0)
        editor.setMaximum(40000)
        editor.setDecimals(0)
        editor.setSingleStep(1000)
        return editor


def leg_distances(
    waypoints: Sequence[FlightWaypoint],
) -> tuple[list[Optional[float]], float]:
    """Nautical miles from the previous flown waypoint, and the route total.

    ``None`` for a waypoint that is not part of the ground track, and for the first
    one, which has nothing before it. Straight legs: a racetrack's laps are time
    spent at a place, not distance along the route.
    """
    legs: list[Optional[float]] = []
    previous: Optional[FlightWaypoint] = None
    total = 0.0
    for waypoint in waypoints:
        if waypoint.waypoint_type in NOT_FLOWN:
            legs.append(None)
            continue
        if previous is None:
            legs.append(None)
        else:
            leg = meters(
                previous.position.distance_to_point(waypoint.position)
            ).nautical_miles
            legs.append(leg)
            total += leg
        previous = waypoint
    return legs, total


#: What kind of thing each waypoint is, as a colour. A route is read by shape -- out,
#: hit, home -- and a column of identical text does not have one.
TYPE_DOTS = {
    FlightWaypointType.TAKEOFF: "#8E9DAA",
    FlightWaypointType.LANDING_POINT: "#8E9DAA",
    FlightWaypointType.DIVERT: "#8E9DAA",
    FlightWaypointType.NAV: "#6E93B0",
    FlightWaypointType.LOITER: "#6E93B0",
    FlightWaypointType.JOIN: "#6E93B0",
    FlightWaypointType.SPLIT: "#6E93B0",
    FlightWaypointType.PATROL: "#6E93B0",
    FlightWaypointType.PATROL_TRACK: "#6E93B0",
    FlightWaypointType.REFUEL: "#86C39A",
    FlightWaypointType.BULLSEYE: None,  # outline only: a reference, not a place you go
}

#: Everything that is an attack -- the run in and what it is run in on.
INGRESS_AMBER = "#E0A86B"

DOT = 6
DOT_X = 8
TEXT_X = 22


class WaypointNameDelegate(QStyledItemDelegate):
    """Paints the type dot in front of the waypoint's name."""

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        colour = index.data(DotColourRole)
        outline = index.data(DotOutlineRole)
        shifted = QStyleOptionViewItem(option)
        shifted.rect = option.rect.adjusted(TEXT_X - 4, 0, 0, 0)
        super().paint(painter, shifted, index)
        if colour is None and not outline:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = option.rect.center().y()
        circle = QRect(option.rect.left() + DOT_X, centre - DOT // 2, DOT, DOT)
        if outline:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor("#4F6070"))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colour))
        painter.drawEllipse(circle)
        painter.restore()


class QFlightWaypointList(QTableView):
    #: Total ground track in nautical miles, emitted whenever the list is rebuilt.
    route_length_changed = Signal(float)

    #: Delete was pressed over the list. The tab owns the rule about what may go,
    #: so it decides whether to honour it -- the same rule the button is greyed by.
    delete_requested = Signal()

    def __init__(self, package: Package, flight: Flight):
        super().__init__()
        self._last_waypoint: Optional[FlightWaypoint] = None
        self.package = package
        self.flight = flight

        #: Display row -> index into flight_plan.waypoints, or None for the header of
        #: a collapsed target group. Everything that acts on a selected row goes
        #: through waypoint_at_row rather than assuming the two line up, because with
        #: a group folded they do not.
        self._row_waypoints: list[Optional[int]] = []
        #: The first waypoint index of each group the player has opened.
        self._expanded: set[int] = set()

        self.model = QStandardItemModel(self)
        self.model.itemChanged.connect(self.on_changed)
        self.setModel(self.model)
        self.model.setHorizontalHeaderLabels(HEADER_LABELS)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.update_list()

        self.selectionModel().setCurrentIndex(
            self.indexAt(QPoint(1, 1)), QItemSelectionModel.SelectionFlag.Select
        )

        self.altitude_editor_delegate = AltitudeEditorDelegate(self)
        self.setItemDelegateForColumn(1, self.altitude_editor_delegate)
        self.name_delegate = WaypointNameDelegate(self)
        self.setItemDelegateForColumn(0, self.name_delegate)

    def update_list(self) -> None:
        # ignore signals when updating list so on_changed does not fire
        self.model.blockSignals(True)
        try:
            # We need to keep just the row and rebuild the index later because the
            # QModelIndex will not be valid after the model is cleared.
            current_index = self.currentIndex().row()
            self.model.clear()

            self.model.setHorizontalHeaderLabels(HEADER_LABELS)

            waypoints = self.flight.flight_plan.waypoints
            legs, total = leg_distances(waypoints)
            self._row_waypoints = []
            index = 0
            while index < len(waypoints):
                group = self._group_at(waypoints, index)
                if group > 1 and index not in self._expanded:
                    self._add_group_row(
                        len(self._row_waypoints), waypoints, index, group
                    )
                    self._row_waypoints.append(None)
                    index += group
                    continue
                if group > 1:
                    self._add_group_row(
                        len(self._row_waypoints), waypoints, index, group
                    )
                    self._row_waypoints.append(None)
                for offset in range(max(1, group)):
                    at = index + offset
                    self._add_waypoint_row(
                        len(self._row_waypoints), self.flight, waypoints[at], legs[at]
                    )
                    self._row_waypoints.append(at)
                index += max(1, group)
            self.route_length_changed.emit(total)
            self.selectionModel().setCurrentIndex(
                self.model.index(current_index, 0),
                QItemSelectionModel.SelectionFlag.Select,
            )
            self.model.setVerticalHeaderLabels(
                ["" if at is None else str(at) for at in self._row_waypoints]
            )
            self.verticalHeader().setMaximumWidth(25)

            self.resizeColumnsToContents()
            # The name column takes whatever the tab gives the table. It used to be
            # pinned to the width of its contents, which meant the last column was cut
            # off whenever a waypoint had a long name.
            self.horizontalHeader().setStretchLastSection(False)
            self.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
        finally:
            # stop ignoring signals
            self.model.blockSignals(False)
            self.update(self.currentIndex())

    def _add_waypoint_row(
        self,
        row: int,
        flight: Flight,
        waypoint: FlightWaypoint,
        leg: Optional[float],
    ) -> None:
        self.model.insertRow(self.model.rowCount())

        name_item = QWaypointItem(waypoint, row)
        kind = waypoint.waypoint_type
        if kind is FlightWaypointType.BULLSEYE:
            name_item.setData(True, DotOutlineRole)
        elif kind in TARGET_TYPES or "INGRESS" in kind.name:
            name_item.setData(INGRESS_AMBER, DotColourRole)
        else:
            name_item.setData(TYPE_DOTS.get(kind, "#6E93B0"), DotColourRole)
        self.model.setItem(row, 0, name_item)

        altitude = round(waypoint.alt.feet)
        altitude_item = QStandardItem(f"{altitude}")
        altitude_item.setEditable(True)
        self.model.setItem(row, 1, altitude_item)

        altitude_type = "AGL" if waypoint.alt_type == "RADIO" else "MSL"
        altitude_type_item = QStandardItem(f"{altitude_type}")
        altitude_type_item.setEditable(False)
        self.model.setItem(row, 2, altitude_type_item)

        tot = self.tot_text(flight, waypoint)
        tot_item = QStandardItem(tot)
        tot_item.setEditable(False)
        self.model.setItem(row, 3, tot_item)

        leg_item = QStandardItem("0" if leg is None else f"{leg:.0f}")
        leg_item.setEditable(False)
        leg_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.model.setItem(row, 4, leg_item)

    @staticmethod
    def _group_at(waypoints: Sequence[FlightWaypoint], index: int) -> int:
        """How many consecutive target waypoints start at ``index`` (0 if none)."""
        if waypoints[index].waypoint_type not in TARGET_TYPES:
            return 0
        end = index
        while end < len(waypoints) and waypoints[end].waypoint_type in TARGET_TYPES:
            end += 1
        return end - index

    def _add_group_row(
        self,
        row: int,
        waypoints: Sequence[FlightWaypoint],
        index: int,
        count: int,
    ) -> None:
        """One row standing for a whole target set, with its own TOT."""
        self.model.insertRow(self.model.rowCount())
        opened = index in self._expanded
        first = waypoints[index]
        arrow = "v" if opened else ">"
        name = QStandardItem(f"{arrow}  {first.name}  ·  {count} targets")
        name.setEditable(False)
        name.setData(index, GroupStartRole)
        font = name.font()
        font.setWeight(QFont.Weight.DemiBold)
        name.setFont(font)
        name.setForeground(QColor(TARGET_AMBER))
        name.setData(TARGET_AMBER, DotColourRole)
        self.model.setItem(row, 0, name)
        for column in (1, 2):
            blank = QStandardItem("")
            blank.setEditable(False)
            self.model.setItem(row, column, blank)
        tot = QStandardItem(self.tot_text(self.flight, first))
        tot.setEditable(False)
        tot.setForeground(QColor(TARGET_AMBER))
        self.model.setItem(row, 3, tot)
        leg = QStandardItem("")
        leg.setEditable(False)
        self.model.setItem(row, 4, leg)

    def waypoint_at_row(self, row: int) -> Optional[FlightWaypoint]:
        """The waypoint a display row stands for, or None for a group header."""
        if row < 0 or row >= len(self._row_waypoints):
            return None
        at = self._row_waypoints[row]
        if at is None:
            return None
        waypoints = self.flight.flight_plan.waypoints
        return waypoints[at] if at < len(waypoints) else None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt naming)
        """A click on a group row opens or closes it."""
        index = self.indexAt(event.pos())
        if index.isValid():
            item = self.model.item(index.row(), 0)
            start = None if item is None else item.data(GroupStartRole)
            if start is not None:
                if start in self._expanded:
                    self._expanded.discard(start)
                else:
                    self._expanded.add(start)
                self.update_list()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt naming)
        """Delete removes the selection, as it does in the package and flight lists.

        Not while a cell is being edited: there Delete belongs to the text.
        """
        if (
            event.key() == Qt.Key.Key_Delete
            and self.state() != QTableView.State.EditingState
        ):
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def on_changed(self) -> None:
        for i in range(self.model.rowCount()):
            # Through waypoint_at_row rather than indexing the list by row: a folded
            # target group is one row standing for several, so the two no longer line
            # up and editing row 5 would have written to the wrong waypoint.
            waypoint = self.waypoint_at_row(i)
            if waypoint is None:
                continue
            altitude_item = self.model.item(i, 1)
            if altitude_item is None:
                continue
            altitude_feet = float(altitude_item.text())
            waypoint.alt = Distance.from_feet(altitude_feet)
            waypoint.apply_name_edit(self.model.item(i, 0).text())

    def tot_text(
        self,
        flight: Flight,
        waypoint: FlightWaypoint,
    ) -> str:
        if waypoint.waypoint_type == FlightWaypointType.TAKEOFF:
            self.update_last_tot(flight.flight_plan.takeoff_time())
            self._last_waypoint = waypoint
            return self.takeoff_text(flight)
        prefix = ""
        time = flight.flight_plan.tot_for_waypoint(waypoint)
        if time is None:
            prefix = "Depart "
            time = flight.flight_plan.depart_time_for_waypoint(waypoint)
        if time is None and self._last_waypoint is not None:
            prefix = ""
            timedelta = flight.flight_plan.travel_time_between_waypoints(
                self._last_waypoint, waypoint
            )
            time = self._last_tot + timedelta
        elif time is None:
            return ""
        self.update_last_tot(time)
        self._last_waypoint = waypoint
        return f"{prefix}{time:%H:%M:%S}"

    @staticmethod
    def takeoff_text(flight: Flight) -> str:
        return f"{flight.flight_plan.takeoff_time():%H:%M:%S}"

    def update_last_tot(self, time) -> None:
        if time is not None:
            self._last_tot = time
