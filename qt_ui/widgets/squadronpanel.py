"""Toolbar and column header around the Air Wing squadron list.

The list answers "which squadron flies the E-2C?" by eye now, but at forty rows
the honest answer to "do I have tanker coverage?" is a filter box, so the list
gained one, plus a sort order and a running count of what is on screen.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSettings,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from game.squadrons import Squadron
from qt_ui.uiconstants import app_settings
from qt_ui.models import AirWingModel
from qt_ui.widgets.squadrondelegate import GroupHeaderRole

TOOLBAR_HEIGHT = 54
FIELD_HEIGHT = 30
HEADER_HEIGHT = 26

#: Matches the delegate's columns so the labels sit over what they name.
COL_TYPE_X = 120
COL_BASE_X = 460
COL_CHIP_X = 730
RIGHT_MARGIN = 14

HEADER_FILL = QColor("#26343F")
HEADER_TEXT = QColor("#6B7A87")

GROUPINGS = [
    ("No grouping", None),
    ("Aircraft type", "type"),
    ("Base", "base"),
]

#: Same store as the main window's geometry, so the choice outlives the app.
GROUPING_KEY = "airwing/grouping"
SORT_KEY = "airwing/sort"

SORT_ORDERS = [
    ("Aircraft type", "type"),
    ("Squadron", "squadron"),
    ("Base", "base"),
    ("Aircraft count", "aircraft"),
    ("Cohesion", "cohesion"),
]


class SquadronFilterProxy(QSortFilterProxyModel):
    """Live filter over type, squadron or base, plus the sort order."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.needle = ""
        self.order = "type"
        self.setDynamicSortFilter(True)

    def set_needle(self, needle: str) -> None:
        self.needle = needle.strip().lower()
        self.invalidateFilter()

    def set_order(self, order: str) -> None:
        self.order = order
        self.invalidate()
        self.sort(0, Qt.SortOrder.AscendingOrder)

    def _squadron(self, index: QModelIndex) -> Squadron | None:
        squadron = index.data(AirWingModel.SquadronRole)
        return squadron if isinstance(squadron, Squadron) else None

    def friendship_in_play(self) -> bool:
        """Whether the squadrons in this list have friendship switched on.

        Sorting by cohesion is meaningless without it, and an entry in a menu that
        does nothing is worse than one that is not there.
        """
        source = self.sourceModel()
        if source is None:
            return False
        for row in range(source.rowCount()):
            squadron = self._squadron(source.index(row, 0))
            if squadron is not None:
                return bool(squadron.friendship_in_play)
        return False

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        if not self.needle:
            return True
        source = self.sourceModel()
        squadron = self._squadron(source.index(row, 0, parent))
        if squadron is None:
            return True
        haystack = " ".join(
            [
                squadron.aircraft.display_name,
                squadron.name,
                squadron.nickname or "",
                squadron.location.name,
            ]
        ).lower()
        return self.needle in haystack

    def _key(self, squadron: Squadron) -> Any:
        if self.order == "squadron":
            return (squadron.name.lower(), squadron.aircraft.display_name.lower())
        if self.order == "base":
            return (
                squadron.location.name.lower(),
                squadron.aircraft.display_name.lower(),
            )
        if self.order == "aircraft":
            # Most aircraft first: the question behind this sort is what you have.
            return (-squadron.owned_aircraft, squadron.aircraft.display_name.lower())
        if self.order == "cohesion":
            # The crews first, the lists of names last.
            cohesion = squadron.cohesion
            return (
                -(cohesion if cohesion is not None else 0.0),
                squadron.aircraft.display_name.lower(),
            )
        return (squadron.aircraft.display_name.lower(), squadron.name.lower())

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        first, second = self._squadron(left), self._squadron(right)
        if first is None or second is None:
            return False
        return self._key(first) < self._key(second)


class GroupedSquadronModel(QAbstractListModel):
    """Flattens the filtered list into group headers followed by their members.

    A QSortFilterProxyModel cannot add rows, so grouping needs a model of its
    own. It rebuilds from scratch whenever the proxy changes, which at forty
    rows costs nothing and keeps the two in step without bookkeeping.
    """

    def __init__(self, proxy: SquadronFilterProxy) -> None:
        super().__init__()
        self.proxy = proxy
        self.grouping: str | None = None
        #: ("header", label, count, first proxy row) or ("squadron", proxy row).
        self.entries: list[tuple[Any, ...]] = []
        for signal in (
            proxy.modelReset,
            proxy.layoutChanged,
            proxy.rowsInserted,
            proxy.rowsRemoved,
            proxy.dataChanged,
        ):
            signal.connect(self.rebuild)
        self.rebuild()

    def set_grouping(self, grouping: str | None) -> None:
        self.grouping = grouping
        self.rebuild()

    def _key(self, squadron: Squadron) -> str:
        if self.grouping == "base":
            return squadron.location.name
        return squadron.aircraft.display_name

    def rebuild(self, *_args: Any) -> None:
        self.beginResetModel()
        self.entries = []
        rows = range(self.proxy.rowCount())
        if self.grouping is None:
            self.entries = [("squadron", row) for row in rows]
        else:
            # Groups appear in the order their first member does, so the sort
            # order still decides what you see first.
            members: dict[str, list[int]] = {}
            for row in rows:
                squadron = self.proxy.index(row, 0).data(AirWingModel.SquadronRole)
                if not isinstance(squadron, Squadron):
                    continue
                members.setdefault(self._key(squadron), []).append(row)
            for label, group in members.items():
                self.entries.append(("header", label, len(group), group[0]))
                self.entries.extend(("squadron", row) for row in group)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.entries)

    def proxy_index(self, index: QModelIndex) -> QModelIndex:
        entry = self.entries[index.row()]
        if entry[0] != "squadron":
            return QModelIndex()
        return self.proxy.index(entry[1], 0)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid() or self.entries[index.row()][0] == "header":
            # A header is a label, not something you can select or open.
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        if entry[0] == "header":
            if role == GroupHeaderRole:
                return entry[1], entry[2]
            return None
        if role == GroupHeaderRole:
            return None
        return self.proxy.index(entry[1], 0).data(role)


class ColumnHeader(QWidget):
    """Four labels painted at the delegate's own column offsets."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(HEADER_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), HEADER_FILL)
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(font)
        painter.setPen(HEADER_TEXT)
        baseline = 17
        painter.drawText(COL_TYPE_X, baseline, "AIRCRAFT TYPE / SQUADRON")
        painter.drawText(COL_BASE_X, baseline, "BASE")
        painter.drawText(COL_CHIP_X, baseline, "ROLE")
        painter.drawText(
            self.rect().adjusted(0, 0, -RIGHT_MARGIN, 0),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            "STRENGTH",
        )
        painter.end()


class SquadronPanel(QWidget):
    """The squadron list with its filter, sort order and totals."""

    def __init__(
        self,
        squadron_list: QWidget,
        proxy: SquadronFilterProxy,
        grouped: GroupedSquadronModel,
    ) -> None:
        super().__init__()
        self.proxy = proxy
        self.grouped = grouped

        self.filter_field = QLineEdit()
        self.filter_field.setPlaceholderText("Filter by type, squadron or base...")
        self.filter_field.setClearButtonEnabled(True)
        self.filter_field.setFixedSize(340, FIELD_HEIGHT)
        self.filter_field.textChanged.connect(self.on_filter_changed)

        self.sort_combo = QComboBox()
        self.sort_combo.setFixedHeight(FIELD_HEIGHT)
        cohesion_in_play = proxy.friendship_in_play()
        for label, key in SORT_ORDERS:
            if key == "cohesion" and not cohesion_in_play:
                continue
            self.sort_combo.addItem(f"Sort: {label}", key)
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)

        self.group_combo = QComboBox()
        self.group_combo.setFixedHeight(FIELD_HEIGHT)
        for label, key in GROUPINGS:
            self.group_combo.addItem(f"Group: {label}", key)
        self.group_combo.currentIndexChanged.connect(self.on_group_changed)

        self.totals = QLabel()
        self.totals.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 12, 12, 12)
        toolbar.setSpacing(12)
        toolbar.addWidget(self.filter_field)
        toolbar.addWidget(self.sort_combo)
        toolbar.addWidget(self.group_combo)
        toolbar.addStretch()
        toolbar.addWidget(self.totals)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(toolbar)
        layout.addWidget(ColumnHeader())
        layout.addWidget(squadron_list)
        self.setLayout(layout)

        self.delegate = squadron_list.itemDelegate()
        self.update_totals()
        self.restore_sort()
        self.restore_grouping()

    @staticmethod
    def _settings() -> QSettings:
        return app_settings()

    def on_filter_changed(self, needle: str) -> None:
        self.proxy.set_needle(needle)
        self.update_totals()

    def on_sort_changed(self, _index: int) -> None:
        order = self.sort_combo.currentData()
        self.proxy.set_order(order)
        self._settings().setValue(SORT_KEY, order)

    def restore_sort(self) -> None:
        saved = self._settings().value(SORT_KEY)
        index = self.sort_combo.findData(saved) if saved else -1
        if index < 0 or index == self.sort_combo.currentIndex():
            # Either nothing was saved or the combo already shows it, and
            # setCurrentIndex emits nothing when the index does not change.
            self.on_sort_changed(self.sort_combo.currentIndex())
            return
        self.sort_combo.setCurrentIndex(index)

    def on_group_changed(self, _index: int) -> None:
        grouping = self.group_combo.currentData()
        self.grouped.set_grouping(grouping)
        # The delegate leaves out whichever column the header now names.
        self.delegate.grouping = grouping
        self._settings().setValue(GROUPING_KEY, "" if grouping is None else grouping)

    def restore_grouping(self) -> None:
        """Reopen the dialog the way it was left."""
        grouping = self._settings().value(GROUPING_KEY) or None
        index = self.group_combo.findData(grouping)
        if index < 0:
            return
        if index == self.group_combo.currentIndex():
            # setCurrentIndex emits nothing when the index does not change, so
            # apply it by hand rather than trusting the signal.
            self.on_group_changed(index)
            return
        self.group_combo.setCurrentIndex(index)

    def update_totals(self) -> None:
        shown = self.proxy.rowCount()
        total = self.proxy.sourceModel().rowCount()
        aircraft = 0
        for row in range(shown):
            squadron = self.proxy.index(row, 0).data(AirWingModel.SquadronRole)
            if isinstance(squadron, Squadron):
                aircraft += squadron.owned_aircraft
        counted = f"{shown} of {total}" if shown != total else str(total)
        self.totals.setText(f"{counted} squadrons · {aircraft} aircraft")
