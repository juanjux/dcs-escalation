"""Select an armor detachment and confirm a validated ground route."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from dcs import Point
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from game.coordinates import parse_latlng
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition,
    MovementDestination,
)
from game.groundmovement.planning import (
    armor_movement_options,
    movement_destination,
    preview_armor_movement,
)
from game.groundmovement.report import preview_token
from game.theater.player import Player
from qt_ui.widgets.searchablecombo import SearchableComboBox
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.pilot.common import PANEL, AMBER, RED

if TYPE_CHECKING:
    from game.groundmovement.planning import ArmorMovementPreview
    from game.theater.controlpoint import ControlPoint
    from qt_ui.models import GameModel


class ArmorMovementDialog(QDialog):
    def __init__(
        self,
        model: GameModel,
        source_id: UUID,
        owner: Player,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.game = model.get()
        self.turn = self.game.turn
        self.source_id = source_id
        self.owner = owner
        self.preview: ArmorMovementPreview | None = None
        self.setWindowTitle("Move armor group")
        self.setMinimumWidth(620)
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; }}")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Select units. Required tractors are added automatically.")
        )
        self.units: dict[int, QCheckBox] = {}
        options = armor_movement_options(self.game, source_id, owner)
        holder = QWidget()
        rows = QVBoxLayout(holder)
        for unit in options.units:
            suffix = (
                " · tractor"
                if unit.can_tow
                else f" · {unit.mobility.replace('_', ' ')}"
            )
            checkbox = QCheckBox(f"{unit.name} [#{unit.id}]{suffix}")
            checkbox.setEnabled(unit.selectable)
            if not unit.selectable:
                checkbox.setToolTip("Already reserved or mobility is not supported")
            checkbox.toggled.connect(self.invalidate)
            self.units[unit.id] = checkbox
            rows.addWidget(checkbox)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setMinimumHeight(170)
        scroll.setMaximumHeight(280)
        layout.addWidget(scroll)
        select_row = QHBoxLayout()
        for title, checked in (
            ("Select all available", True),
            ("Clear selection", False),
        ):
            button = QPushButton(title)
            button.clicked.connect(
                lambda _=False, value=checked: self.select_all(value)
            )
            select_row.addWidget(button)
        layout.addLayout(select_row)
        for warning in options.warnings:
            text = QLabel(warning)
            text.setWordWrap(True)
            text.setStyleSheet(f"color: {AMBER};")
            layout.addWidget(text)
        self.kind = QComboBox()
        for title, kind in (
            ("Position — create a new armor group", DestinationKind.POSITION),
            ("Base — join its ground inventory", DestinationKind.BASE),
            ("Frontline — reinforce its supporting base", DestinationKind.FRONTLINE),
        ):
            self.kind.addItem(title, kind)
        layout.addWidget(self.kind)
        self.target = SearchableComboBox(
            placeholder="Type to find a base or frontline…"
        )
        layout.addWidget(self.target)
        coordinates = QHBoxLayout()
        self.coordinates = QLineEdit()
        self.coordinates.setPlaceholderText(
            "Friendly-territory coordinates (DDM, DMS, decimal or MGRS)"
        )
        coordinates.addWidget(self.coordinates, 1)
        self.paste = QPushButton("Paste")
        self.paste.clicked.connect(self.paste_coordinates)
        coordinates.addWidget(self.paste)
        layout.addLayout(coordinates)
        self.details = QLabel("Choose units and a destination, then preview the route.")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.details)
        layout.addWidget(
            QLabel(
                "Movement advances after mission results, one distance budget per turn."
            )
        )
        buttons = QHBoxLayout()
        self.preview_button = QPushButton("Preview route")
        self.preview_button.clicked.connect(self.calculate)
        self.dispatch_button = QPushButton("Dispatch")
        self.dispatch_button.setEnabled(False)
        self.dispatch_button.clicked.connect(self.dispatch)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        for button in (self.preview_button, self.dispatch_button, cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.kind.currentIndexChanged.connect(self.change_kind)
        self.target.currentIndexChanged.connect(self.invalidate)
        self.coordinates.textChanged.connect(self.invalidate)
        self.change_kind()
        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            signal.ground_movements_changed.connect(
                self.campaign_changed, Qt.ConnectionType.QueuedConnection
            )
            signal.gameupdated.connect(
                self.campaign_changed, Qt.ConnectionType.QueuedConnection
            )

    def select_all(self, checked: bool) -> None:
        for checkbox in self.units.values():
            if checkbox.isEnabled():
                checkbox.setChecked(checked)

    def paste_coordinates(self) -> None:
        self.coordinates.setText(QApplication.clipboard().text())

    def invalidate(self) -> None:
        self.preview = None
        self.dispatch_button.setEnabled(False)
        self.set_details("Selection changed. Preview the route before dispatching.")

    def set_details(self, text: str, *, blocked: bool = False) -> None:
        self.details.setProperty("movementBlocked", blocked)
        self.details.setStyleSheet(
            f"QLabel {{ color: {AMBER}; background: #352b25; "
            f"border: 1px solid {RED}; border-left: 4px solid {RED}; "
            "border-radius: 3px; padding: 10px; font-weight: bold; }"
            if blocked
            else ""
        )
        self.details.setText(f"Movement blocked\n{text}" if blocked else text)

    def campaign_changed(self) -> None:
        self.invalidate()
        self.preview_button.setEnabled(False)
        self.set_details(
            "The campaign or movement orders changed. Close and reopen this dialog.",
            blocked=True,
        )

    def change_kind(self) -> None:
        kind = self.kind.currentData()
        position = kind is DestinationKind.POSITION
        self.target.setVisible(not position)
        self.coordinates.setVisible(position)
        self.paste.setVisible(position)
        self.target.clear()
        if not position:
            for base in sorted(self.game.theater.controlpoints, key=lambda cp: cp.name):
                opponents: list[ControlPoint | None] = (
                    list(base.front_lines)
                    if kind is DestinationKind.FRONTLINE
                    else [None]
                )
                for opponent in opponents:
                    try:
                        destination = movement_destination(
                            self.game,
                            self.owner,
                            kind,
                            base_id=base.id,
                            opposing_base_id=(
                                opponent.id if opponent is not None else None
                            ),
                        )
                    except (ValueError, PermissionError):
                        continue
                    title = (
                        f"{base.name} / {opponent.name}"
                        if opponent is not None
                        else base.name
                    )
                    self.target.addItem(title, destination)
        self.invalidate()

    def selected_ids(self) -> list[int]:
        return [
            unit_id for unit_id, checkbox in self.units.items() if checkbox.isChecked()
        ]

    def destination(self) -> MovementDestination:
        kind = self.kind.currentData()
        if kind is not DestinationKind.POSITION:
            destination = self.target.currentData()
            if not isinstance(destination, MovementDestination):
                raise ValueError("No eligible destination is available")
            return destination
        latlng = parse_latlng(self.coordinates.text())
        if latlng is None:
            raise ValueError("Enter valid coordinates or paste them from the map")
        point = Point.from_latlng(latlng, self.game.theater.terrain)
        return movement_destination(
            self.game, self.owner, kind, position=GroundPosition(point.x, point.y)
        )

    def calculate(self) -> None:
        self.invalidate()
        try:
            self.model.ground_movement_commands.require_planning(self.game)
            if self.game.turn != self.turn:
                raise ValueError("The turn changed. Close and reopen this dialog")
            result = preview_armor_movement(
                self.game,
                self.source_id,
                self.owner,
                self.selected_ids(),
                self.destination(),
            )
        except (ValueError, PermissionError) as exc:
            self.set_details(str(exc), blocked=True)
            return
        self.preview = result
        automatic = set(result.manifest.unit_ids) - set(self.selected_ids())
        included = (
            ", ".join(self.units[unit_id].text() for unit_id in sorted(automatic))
            or "none"
        )
        self.set_details(
            f"{len(result.manifest.unit_ids)} units moving · {len(result.remaining_unit_ids)} remain\n"
            f"Automatically added tractors: {included}\n"
            f"Road: {result.road_distance_m / 1000:.1f} km · Off-road: {result.offroad_distance_m / 1000:.1f} km\n"
            f"Estimated arrival: {result.arrival_in_turns} turn(s)\n"
            "Cargo is abstracted during transit. A piece is lost if its tractor is destroyed."
            + ("\n" + "\n".join(result.warnings) if result.warnings else "")
        )
        self.dispatch_button.setEnabled(True)

    def dispatch(self) -> None:
        if self.preview is None:
            return
        self.dispatch_button.setEnabled(False)
        try:
            if self.game.turn != self.turn:
                raise ValueError("The turn changed. Request a new preview")
            self.model.ground_movement_commands.dispatch(
                self.game,
                self.source_id,
                self.owner,
                self.selected_ids(),
                self.preview.destination,
                preview_token(self.game, self.preview),
            )
        except (ValueError, PermissionError) as exc:
            self.preview = None
            self.set_details(str(exc), blocked=True)
            return
        self.accept()
