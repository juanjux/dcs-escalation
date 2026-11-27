from functools import partial
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from game.ato import prerequisites
from game.ato.package import Package
from qt_ui.models import PackageModel
from qt_ui.widgets.atodelegates import FLIGHT_ROW_HEIGHT, FlightRowDelegate
from qt_ui.widgets.cards import CARD_BG, CARD_BORDER
from qt_ui.widgets.controls import button


class PrerequisiteList(QTreeWidget):
    """Flight cards whose actions operate on a dependency or its package."""

    remove_requested = Signal(object)
    open_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(3)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setStyleSheet(
            f"QTreeWidget {{ background: {CARD_BG}; border: 1px solid {CARD_BG}; }}"
            f"QTreeWidget::item {{ border-bottom: 1px solid {CARD_BORDER}; }}"
        )
        self.setMouseTracking(True)
        self.setItemDelegateForColumn(0, FlightRowDelegate(self))
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(2, 50)
        self.itemDoubleClicked.connect(self.open_package)

    def refresh(self, package: Package, editable: bool) -> None:
        keys = package.prerequisite_flights
        if keys != [
            self.key(self.topLevelItem(i)) for i in range(self.topLevelItemCount())
        ]:
            current = self.key(self.currentItem()) if self.currentItem() else None
            self.clear()
            for key in keys:
                item = QTreeWidgetItem(self)
                item.setData(1, Qt.ItemDataRole.UserRole, key)
                remove = button("×", "danger", partial(self.remove_requested.emit, key))
                remove.setFixedSize(38, remove.sizeHint().height())
                remove.setAutoDefault(False)
                remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                remove.setAccessibleName("Remove prerequisite")
                cell = QWidget()
                controls = QHBoxLayout(cell)
                controls.setContentsMargins(0, 0, 0, 0)
                controls.addWidget(remove, alignment=Qt.AlignmentFlag.AlignCenter)
                self.setItemWidget(item, 2, cell)
                if key == current:
                    self.setCurrentItem(item)
        for row, key in enumerate(keys):
            item = self.topLevelItem(row)
            flight = package.prerequisite_flight(key)
            label = prerequisites.describe(package, key)
            item.setData(0, PackageModel.FlightRole, flight)
            item.setText(1, label)
            tip = label
            if flight is not None:
                if flight.flight_type in prerequisites.OBJECTIVE_FLIGHTS:
                    tip += (
                        " — DCS checks the objective and flight status automatically."
                    )
                else:
                    tip += f" — {prerequisites.outcome_flag(key)} (1 = success, 2 = failure)"
            item.setToolTip(0, tip)
            item.setToolTip(1, tip)
            remove = self.itemWidget(item, 2)
            remove.setEnabled(editable)
            remove.setToolTip(f"Remove prerequisite: {label}")
        self.setVisible(bool(keys))
        if keys:
            height = sum(self.sizeHintForRow(i) for i in range(min(2, len(keys))))
            self.setFixedHeight(max(FLIGHT_ROW_HEIGHT, height) + 2 * self.frameWidth())

    @staticmethod
    def key(item: QTreeWidgetItem) -> UUID:
        return item.data(1, Qt.ItemDataRole.UserRole)

    def open_package(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 2:
            self.open_requested.emit(self.key(item))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            for item in self.selectedItems():
                if self.itemWidget(item, 2).isEnabled():
                    self.remove_requested.emit(self.key(item))
            event.accept()
            return
        super().keyPressEvent(event)
