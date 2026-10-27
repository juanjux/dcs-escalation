from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Tuple, Type

from PySide6.QtCore import Qt, Signal, SignalInstance
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
    QApplication,
)
from dcs.unittype import UnitType

from game import Game
from dcs import Point
from game.coordinates import parse_latlng
from game.groundmovement.base import (
    BaseMovementPreview,
    available_stock,
    preview_base_movement,
)
from game.groundmovement.orders import DestinationKind, GroundPosition
from game.groundmovement.report import preview_token
from game.groundmovement.settings import enabled as movement_enabled
from game.dcs.groundunittype import GroundUnitType
from game.theater import ControlPoint, Player
from game.transfers import submit_transfer
from qt_ui.models import GameModel
from qt_ui.widgets.QLabeledWidget import QLabeledWidget
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.pilot.common import AMBER, RED


class TransferDestinationComboBox(QComboBox):
    def __init__(self, game: Game, origin: ControlPoint) -> None:
        super().__init__()
        self.game = game
        self.origin = origin
        owner = origin.captured

        for cp in self.game.theater.controlpoints:
            if (
                cp != self.origin
                and cp.is_friendly(to_player=owner)
                and cp.can_deploy_ground_units
                and self.game.transit_network_for(owner).has_path_between(origin, cp)
            ):
                self.addItem(cp.name, cp)
        self.model().sort(0)
        self.setCurrentIndex(0)
        if movement_enabled(game.settings) and not origin.is_fleet:
            self.addItem("GPS — create Reserve Armor Group", DestinationKind.POSITION)


class UnitTransferList(QFrame):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super().__init__(self)
        self.cp = cp
        self.game_model = game_model

        self.bought_amount_labels = {}
        self.existing_units_labels = {}

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        scroll_content = QWidget()
        task_box_layout = QGridLayout()
        scroll_content.setLayout(task_box_layout)

        units_column = sorted(cp.base.armor, key=lambda u: u.display_name)

        count = 0
        for count, unit_type in enumerate(units_column):
            self.add_purchase_row(unit_type, task_box_layout, count)
        stretch = QVBoxLayout()
        stretch.addStretch()
        task_box_layout.addLayout(stretch, count, 0)

        scroll_content.setLayout(task_box_layout)
        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)


class TransferOptionsPanel(QVBoxLayout):
    def __init__(self, game: Game, origin: ControlPoint) -> None:
        super().__init__()

        self.source_combo_box = TransferDestinationComboBox(game, origin)
        self.transport_type = QComboBox()
        self.transport_type.addItem("Auto", "auto")
        self.transport_type.addItem("Airlift", "airlift")
        self.addLayout(QLabeledWidget("Destination:", self.source_combo_box))
        self.addLayout(QLabeledWidget("Requested transport type:", self.transport_type))

    @property
    def changed(self) -> SignalInstance:
        return self.source_combo_box.currentIndexChanged

    @property
    def current(self) -> ControlPoint | None:
        value = self.source_combo_box.currentData()
        return value if isinstance(value, ControlPoint) else None

    @property
    def gps_selected(self) -> bool:
        return self.source_combo_box.currentData() is DestinationKind.POSITION

    @property
    def request_airlift(self) -> bool:
        return self.transport_type.currentData() == "airlift"


class TransferControls(QGroupBox):
    def __init__(
        self,
        increase_text: str,
        on_increase: Callable[[TransferControls], None],
        decrease_text: str,
        on_decrease: Callable[[TransferControls], None],
        initial_amount: int = 0,
        disabled: bool = False,
    ) -> None:
        super().__init__()

        self.quantity = initial_amount

        self.setProperty("style", "buy-box")
        self.setMaximumHeight(36)
        self.setMinimumHeight(36)
        layout = QHBoxLayout()
        self.setLayout(layout)

        decrease = QPushButton(decrease_text)
        decrease.setProperty("style", "btn-sell")
        decrease.setDisabled(disabled)
        decrease.setMinimumSize(16, 16)
        decrease.setMaximumSize(16, 16)
        decrease.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )
        decrease.clicked.connect(lambda: on_decrease(self))
        layout.addWidget(decrease)

        self.count_label = QLabel()
        self.count_label.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )
        self.set_quantity(initial_amount)
        layout.addWidget(self.count_label)

        increase = QPushButton(increase_text)
        increase.setProperty("style", "btn-buy")
        increase.setDisabled(disabled)
        increase.setMinimumSize(16, 16)
        increase.setMaximumSize(16, 16)
        increase.clicked.connect(lambda: on_increase(self))
        increase.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )
        layout.addWidget(increase)

    def set_quantity(self, quantity: int) -> None:
        self.quantity = quantity
        self.count_label.setText(f"<b>{self.quantity}</b>")


class ScrollingUnitTransferGrid(QFrame):
    transfer_quantity_changed = Signal()

    def __init__(
        self,
        cp: ControlPoint,
        game_model: GameModel,
        inventory: dict[GroundUnitType, int] | None = None,
    ) -> None:
        super().__init__()
        self.cp = cp
        self.game_model = game_model
        self.transfers: dict[GroundUnitType, int] = defaultdict(int)
        self.inventory = inventory
        # One (send everything, send nothing) pair per unit row. A row owns its own
        # remaining-inventory count, so the bulk buttons drive the rows rather than
        # reaching into their state.
        self.rows: List[Tuple[Callable[[], None], Callable[[], None]]] = []

        main_layout = QVBoxLayout()

        scroll_content = QWidget()
        task_box_layout = QGridLayout()

        owner = cp.captured
        game = self.game_model.game
        if game is None:
            raise ValueError("No campaign is loaded")
        unit_types = (
            set(inventory)
            if inventory is not None
            else set(game.faction_for(player=owner).ground_units)
        )
        sorted_units = sorted(
            {u for u in unit_types if self.cp.base.total_units_of_type(u)},
            key=lambda u: u.display_name,
        )
        for row, unit_type in enumerate(sorted_units):
            self.add_unit_row(unit_type, task_box_layout, row)
        stretch = QVBoxLayout()
        stretch.addStretch()
        task_box_layout.addLayout(stretch, task_box_layout.count(), 0)

        scroll_content.setLayout(task_box_layout)

        # A base can hold two dozen unit types, and clicking each one up to its full
        # count is the slowest part of moving a garrison.
        bulk = QHBoxLayout()
        bulk.addStretch()
        select_none = QPushButton("None <<")
        select_none.setProperty("style", "btn-sell")
        select_none.clicked.connect(self.transfer_none)
        bulk.addWidget(select_none)
        select_all = QPushButton("All >>")
        select_all.setProperty("style", "btn-buy")
        select_all.clicked.connect(self.transfer_all)
        bulk.addWidget(select_all)
        main_layout.addLayout(bulk)

        scroll = QScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def add_unit_row(
        self,
        unit_type: GroundUnitType,
        layout: QGridLayout,
        row: int,
    ) -> None:
        exist = QGroupBox()
        exist.setProperty("style", "buy-box")
        exist.setMaximumHeight(36)
        exist.setMinimumHeight(36)
        origin_inventory_layout = QHBoxLayout()
        exist.setLayout(origin_inventory_layout)

        origin_inventory = (
            self.inventory.get(unit_type, 0)
            if self.inventory is not None
            else self.cp.base.total_units_of_type(unit_type)
        )

        unit_name = QLabel(f"<b>{unit_type.display_name}</b>")
        unit_name.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )

        origin_inventory_label = QLabel(str(origin_inventory))
        origin_inventory_label.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

        def increase(controls: TransferControls) -> None:
            nonlocal origin_inventory
            nonlocal origin_inventory_label
            if not origin_inventory:
                return

            modifiers = QApplication.keyboardModifiers()
            if modifiers == Qt.KeyboardModifier.ShiftModifier:
                amount = 10
            elif modifiers == Qt.KeyboardModifier.ControlModifier:
                amount = 5
            else:
                amount = 1

            self.transfers[unit_type] += min(origin_inventory, amount)
            origin_inventory -= min(origin_inventory, amount)
            controls.set_quantity(self.transfers[unit_type])
            origin_inventory_label.setText(str(origin_inventory))
            self.transfer_quantity_changed.emit()

        def decrease(controls: TransferControls) -> None:
            nonlocal origin_inventory
            nonlocal origin_inventory_label
            if not controls.quantity:
                return

            modifiers = QApplication.keyboardModifiers()
            if modifiers == Qt.KeyboardModifier.ShiftModifier:
                amount = 10
            elif modifiers == Qt.KeyboardModifier.ControlModifier:
                amount = 5
            else:
                amount = 1

            origin_inventory += min(self.transfers[unit_type], amount)
            self.transfers[unit_type] -= min(self.transfers[unit_type], amount)
            controls.set_quantity(self.transfers[unit_type])
            origin_inventory_label.setText(str(origin_inventory))
            self.transfer_quantity_changed.emit()

        transfer_controls = TransferControls("->", increase, "<-", decrease)

        def send_everything() -> None:
            nonlocal origin_inventory
            if not origin_inventory:
                return
            self.transfers[unit_type] += origin_inventory
            origin_inventory = 0
            transfer_controls.set_quantity(self.transfers[unit_type])
            origin_inventory_label.setText(str(origin_inventory))

        def send_nothing() -> None:
            nonlocal origin_inventory
            if not self.transfers[unit_type]:
                return
            origin_inventory += self.transfers[unit_type]
            self.transfers[unit_type] = 0
            transfer_controls.set_quantity(0)
            origin_inventory_label.setText(str(origin_inventory))

        self.rows.append((send_everything, send_nothing))

        origin_inventory_layout.addWidget(unit_name)
        origin_inventory_layout.addItem(
            QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        )
        origin_inventory_layout.addWidget(origin_inventory_label)
        origin_inventory_layout.addItem(
            QSpacerItem(20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        )

        layout.addWidget(exist, row, 1)
        layout.addWidget(transfer_controls, row, 2)

    def transfer_all(self) -> None:
        for send_everything, _ in self.rows:
            send_everything()
        # Once at the end: the dialog only needs to know whether anything is queued.
        self.transfer_quantity_changed.emit()

    def transfer_none(self) -> None:
        for _, send_nothing in self.rows:
            send_nothing()
        self.transfer_quantity_changed.emit()


class NewUnitTransferDialog(QDialog):
    def __init__(
        self,
        game_model: GameModel,
        origin: ControlPoint,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.origin = origin
        self.setWindowTitle(f"New unit transfer from {origin.name}")

        self.game_model = game_model
        game = game_model.game
        if game is None:
            raise ValueError("No campaign is loaded")
        self.game = game
        self.owner = origin.captured
        self.turn = self.game.turn
        self.preview: BaseMovementPreview | None = None
        self.gps_mode = False
        self.stale = False

        layout = QVBoxLayout()
        self.main_layout = layout
        self.setLayout(layout)

        self.dest_panel = TransferOptionsPanel(self.game, origin)
        self.dest_panel.changed.connect(self.destination_changed)
        layout.addLayout(self.dest_panel)

        self.transfer_panel = ScrollingUnitTransferGrid(origin, game_model)
        self.transfer_panel.transfer_quantity_changed.connect(
            self.on_transfer_quantity_changed
        )
        layout.addWidget(self.transfer_panel)

        self.gps_panel = QWidget()
        gps_layout = QVBoxLayout(self.gps_panel)
        gps_layout.addWidget(
            QLabel("Create an active Reserve Armor Group in friendly territory.")
        )
        coordinate_row = QHBoxLayout()
        self.coordinates = QLineEdit()
        self.coordinates.setPlaceholderText(
            "Friendly GPS position (DDM, DMS, decimal or MGRS)"
        )
        self.coordinates.textChanged.connect(self.on_transfer_quantity_changed)
        coordinate_row.addWidget(self.coordinates)
        paste = QPushButton("Paste")
        paste.clicked.connect(
            lambda: self.coordinates.setText(QApplication.clipboard().text())
        )
        coordinate_row.addWidget(paste)
        self.pick_on_map = QPushButton("Choose on map…")
        self.pick_on_map.clicked.connect(self.choose_on_map)
        coordinate_row.addWidget(self.pick_on_map)
        gps_layout.addLayout(coordinate_row)
        self.details = QLabel(
            "Select units and GPS coordinates, then preview the route."
        )
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        gps_layout.addWidget(self.details)
        self.preview_button = QPushButton("Preview route")
        self.preview_button.clicked.connect(self.calculate)
        gps_layout.addWidget(self.preview_button)
        layout.addWidget(self.gps_panel)

        self.submit_button = QPushButton("Create Transfer Order", parent=self)
        self.submit_button.clicked.connect(self.on_submit)
        self.submit_button.setProperty("style", "start-button")
        self.submit_button.setDisabled(True)
        layout.addWidget(self.submit_button)
        self.destination_changed()
        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            signal.ground_movements_changed.connect(
                self.campaign_changed, Qt.ConnectionType.QueuedConnection
            )
            signal.gameupdated.connect(
                self.campaign_changed, Qt.ConnectionType.QueuedConnection
            )
        game_model.transfer_model.inventory_changed.connect(
            self.campaign_changed, Qt.ConnectionType.QueuedConnection
        )

    def destination_changed(self) -> None:
        gps = self.dest_panel.gps_selected
        if gps != self.gps_mode:
            old = self.transfer_panel
            self.transfer_panel = ScrollingUnitTransferGrid(
                self.origin,
                self.game_model,
                available_stock(self.origin) if gps else None,
            )
            self.transfer_panel.transfer_quantity_changed.connect(
                self.on_transfer_quantity_changed
            )
            self.main_layout.replaceWidget(old, self.transfer_panel)
            old.hide()
            old.deleteLater()
        self.gps_mode = gps
        self.gps_panel.setVisible(gps)
        self.dest_panel.transport_type.setEnabled(not gps)
        self.submit_button.setText(
            "Dispatch Reserve Armor Group" if gps else "Create Transfer Order"
        )
        self.on_transfer_quantity_changed()

    def campaign_changed(self) -> None:
        self.stale = True
        self.preview = None
        self.submit_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.pick_on_map.setEnabled(False)
        self.set_details(
            "The campaign or inventory changed. Close and reopen this dialog.",
            blocked=True,
        )

    def set_details(self, text: str, *, blocked: bool = False) -> None:
        self.details.setProperty("movementBlocked", blocked)
        self.details.setStyleSheet(
            f"QLabel {{ color: {AMBER}; background: #352b25; border: 1px solid {RED}; padding: 8px; }}"
            if blocked
            else ""
        )
        self.details.setText(text)

    def gps_position(self) -> GroundPosition:
        latlng = parse_latlng(self.coordinates.text())
        if latlng is None:
            raise ValueError("Enter valid coordinates or paste them from the map")
        point = Point.from_latlng(latlng, self.game.theater.terrain)
        return GroundPosition(point.x, point.y)

    def choose_on_map(self) -> None:
        from qt_ui.widgets.map.grounddestination import GroundDestinationDialog

        selected = dict(self.transfer_panel.transfers)

        def preview(position: GroundPosition) -> BaseMovementPreview:
            if self.stale:
                raise ValueError("The campaign changed. Close and reopen this dialog")
            return preview_base_movement(
                self.game, self.origin.id, self.owner, selected, position
            )

        try:
            self.game_model.ground_movement_commands.require_planning(self.game)
            if not any(selected.values()):
                raise ValueError("Select units before choosing a destination")
            picker = GroundDestinationDialog(
                self.game_model, self.origin.position, self.origin.name, preview, self
            )
            try:
                if picker.exec() == QDialog.DialogCode.Accepted and picker.selected:
                    at = picker.selected
                    self.coordinates.setText(f"{at.lat:.10f}, {at.lng:.10f}")
                    self.calculate()
            finally:
                picker.deleteLater()
        except (ValueError, PermissionError, RuntimeError) as exc:
            self.set_details(str(exc), blocked=True)

    def calculate(self) -> None:
        self.on_transfer_quantity_changed()
        try:
            self.game_model.ground_movement_commands.require_planning(self.game)
            if self.stale or self.game.turn != self.turn:
                raise ValueError("The campaign changed. Close and reopen this dialog")
            self.preview = preview_base_movement(
                self.game,
                self.origin.id,
                self.owner,
                self.transfer_panel.transfers,
                self.gps_position(),
            )
        except (ValueError, PermissionError) as exc:
            self.set_details(str(exc), blocked=True)
            return
        p = self.preview
        included = ", ".join(
            f"{n} × {GroundUnitType.named(name).display_name}" for name, n in p.units
        )
        added = (
            ", ".join(
                f"{n} × {GroundUnitType.named(name).display_name}"
                for name, n in p.automatically_added
            )
            or "none"
        )
        self.set_details(
            f"{included}\nAutomatically added tractors: {added}\nRoad: {p.road_distance_m/1000:.1f} km · Off-road: {p.offroad_distance_m/1000:.1f} km\nEstimated arrival: {p.arrival_in_turns} turn(s)\nUnits leave base stock on dispatch and remain an active group at the destination."
        )
        self.submit_button.setEnabled(True)

    def on_submit(self) -> None:
        if self.gps_mode:
            if self.preview is None:
                return
            self.submit_button.setEnabled(False)
            try:
                if self.stale or self.game.turn != self.turn:
                    raise ValueError("The campaign changed. Request a new preview")
                self.game_model.ground_movement_commands.dispatch_base(
                    self.game,
                    self.origin.id,
                    self.owner,
                    dict(self.transfer_panel.transfers),
                    self.gps_position(),
                    preview_token(self.game, self.preview),
                )
            except (ValueError, PermissionError) as exc:
                self.preview = None
                self.set_details(str(exc), blocked=True)
                return
            self.accept()
            return
        destination = self.dest_panel.current
        if destination is None:
            return
        submit_transfer(
            self.game_model,
            self.origin,
            destination,
            self.transfer_panel.transfers,
            self.game_model.sim_controller.current_time_in_sim,
            request_airlift=self.dest_panel.request_airlift,
        )
        self.close()

    def on_transfer_quantity_changed(self) -> None:
        self.preview = None
        if self.stale:
            self.submit_button.setEnabled(False)
            self.set_details(
                "The campaign or inventory changed. Close and reopen this dialog.",
                blocked=True,
            )
            return
        if hasattr(self, "details"):
            self.set_details("Selection changed. Preview the route before dispatching.")
        has_transfer_items = any(self.transfer_panel.transfers.values())
        self.submit_button.setDisabled(
            self.stale
            or self.gps_mode
            or not has_transfer_items
            or self.dest_panel.current is None
        )
