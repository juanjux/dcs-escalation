"""Select a persistent enemy objective or exact GPS missile aimpoint."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from dcs import Point
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QWidget,
)

from game import missiletargets
from game.coordinates import parse_latlng
from game.groundmovement.orders import GroundPosition
from game.theater.player import Player
from qt_ui.models import GameModel
from qt_ui.missiletargets import apply
from qt_ui.widgets.searchablecombo import SearchableComboBox
from qt_ui.widgets.map.grounddestination import GroundDestinationPicker
from shiboken6 import isValid


class MissileTargetDialog(QDialog):
    def __init__(self, model: GameModel, source_id: UUID, parent: Any = None) -> None:
        super().__init__(parent)
        self.model = model
        self.game = model.get()
        self.source_id = source_id
        self.setWindowTitle("Missile target")
        self.setMinimumWidth(600)
        self.preview: dict[str, Any] | None = None
        options = missiletargets.options(self.game, source_id, Player.BLUE)
        column = QVBoxLayout(self)
        column.addWidget(QLabel(options["source_name"]))
        ranges = QLabel(
            "\n".join(
                f"{w['unit_type']}: {w['min_range_m'] / 1000:.1f}–{w['max_range_m'] / 1000:.1f} km"
                for w in options["launchers"]
            )
        )
        ranges.setWordWrap(True)
        column.addWidget(ranges)
        self.target = SearchableComboBox()
        self.target.addItem("GPS position", None)
        for target in options["targets"]:
            suffix = "" if target["in_range"] else " — outside missile range"
            self.target.addItem(
                f"{target['name']} · {target['distance_m'] / 1000:.1f} km{suffix}",
                target["id"],
            )
        column.addWidget(self.target)
        self.coordinates = QLineEdit()
        self.coordinates.setPlaceholderText(
            "Latitude, longitude (decimal degrees, DDM or DMS)"
        )
        column.addWidget(self.coordinates)
        self.message = QLabel()
        self.message.setWordWrap(True)
        column.addWidget(self.message)
        if not options["enabled"]:
            disabled = QLabel(
                "Missile firing is disabled in campaign settings. Assignments are saved but will not fire until enabled."
            )
            disabled.setWordWrap(True)
            disabled.setStyleSheet("color: #e6ad62; font-weight: bold;")
            column.addWidget(disabled)
        buttons = QHBoxLayout()
        self.pick_button = QPushButton("Choose on map…")
        self.pick_button.clicked.connect(self.pick)
        self.assign_button = QPushButton("Assign target")
        self.assign_button.clicked.connect(self.assign)
        clear = QPushButton("Clear target")
        clear.clicked.connect(self.clear)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        for button in (self.pick_button, self.assign_button, clear, cancel):
            buttons.addWidget(button)
        column.addLayout(buttons)
        self.target.currentIndexChanged.connect(self.update_preview)
        self.coordinates.textChanged.connect(self.update_preview)
        order = missiletargets.stored(self.game.db.tgos.get(source_id))
        if order:
            if order.target_id and order.track_position:
                index = self.target.findData(str(order.target_id))
                if index >= 0:
                    self.target.setCurrentIndex(index)
            else:
                at = Point(order.x, order.z, self.game.theater.terrain).latlng()
                self.coordinates.setText(f"{at.lat:.8f}, {at.lng:.8f}")
        self.update_preview()

    def selection(self) -> dict[str, Any]:
        if self.target.currentData():
            return {"target_id": UUID(self.target.currentData())}
        at = parse_latlng(self.coordinates.text())
        if at is None:
            raise ValueError("Enter a valid latitude and longitude")
        return {"lat": at.lat, "lng": at.lng}

    def update_preview(self) -> None:
        self.coordinates.setEnabled(self.target.currentData() is None)
        try:
            self.model.ground_movement_commands.require_planning(self.game)
            _, self.preview = missiletargets.preview(
                self.game, self.source_id, Player.BLUE, **self.selection()
            )
            self.message.setText(
                self.preview["warning"]
                or f"{self.preview['target_name']} · {self.preview['distance_m'] / 1000:.1f} km"
            )
            self.message.setStyleSheet(
                "color: #e6ad62;" if self.preview["empty_position"] else ""
            )
            self.assign_button.setEnabled(True)
        except (ValueError, PermissionError) as exc:
            self.preview = None
            self.message.setText(str(exc))
            self.message.setStyleSheet("color: #ff8b7e; font-weight: bold;")
            self.assign_button.setEnabled(False)

    def assign(self) -> None:
        try:
            self.update_preview()
            if self.preview is None:
                return
            confirm = False
            if self.preview["empty_position"]:
                confirm = (
                    QMessageBox.question(
                        self,
                        "No known target",
                        self.preview["warning"] + "\n\nKeep this aimpoint?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                )
                if not confirm:
                    return
            commands = self.model.ground_movement_commands
            commands.run(
                lambda: apply(
                    self.game,
                    commands,
                    self.source_id,
                    Player.BLUE,
                    {**self.selection(), "confirm_empty": confirm},
                )
            )
            self.accept()
        except (ValueError, PermissionError) as exc:
            self.message.setText(str(exc))
            self.message.setStyleSheet("color: #ff8b7e; font-weight: bold;")

    def clear(self) -> None:
        try:
            commands = self.model.ground_movement_commands
            commands.run(
                lambda: apply(self.game, commands, self.source_id, Player.BLUE, None)
            )
            self.accept()
        except (ValueError, PermissionError) as exc:
            self.message.setText(str(exc))

    def pick(self) -> None:
        try:
            source = self.game.db.tgos.get(self.source_id)
            weapons = missiletargets.launchers(self.game, source)
            if not weapons:
                raise ValueError("No operational missile launcher with ammunition")

            def preview(position: GroundPosition) -> dict[str, Any]:
                at = Point(position.x, position.z, self.game.theater.terrain).latlng()
                return missiletargets.preview(
                    self.game, self.source_id, Player.BLUE, lat=at.lat, lng=at.lng
                )[1]

            picker = GroundDestinationPicker(
                self.model,
                source.position,
                source.obj_name,
                preview,
                self,
                details={
                    "mode": "missile",
                    "min_range_m": min(w.minimum for w in weapons),
                    "max_range_m": max(w.maximum for w in weapons),
                    "snap_targets": [
                        {
                            "id": str(target.id),
                            "name": target.obj_name,
                            "position": {
                                "lat": target.position.latlng().lat,
                                "lng": target.position.latlng().lng,
                            },
                        }
                        for target in missiletargets.targets(self.game, Player.BLUE)
                    ],
                },
            )
            if picker.exec() == QDialog.DialogCode.Accepted and picker.selected:
                self.target.setCurrentIndex(0)
                self.coordinates.setText(
                    f"{picker.selected.lat:.8f}, {picker.selected.lng:.8f}"
                )
        except (ValueError, RuntimeError) as exc:
            self.message.setText(str(exc))


class MissileTargetPanel(QWidget):
    """Base and carrier access to all their missile-launching groups."""

    def __init__(self, model: GameModel, sources: list[Any]) -> None:
        super().__init__()
        self.model = model
        column = QVBoxLayout(self)
        for source in sources:
            row = QHBoxLayout()
            order = missiletargets.stored(source)
            text = QLabel(
                f"{source.obj_name}: {order.name if order else 'No assigned target'}"
            )
            text.setWordWrap(True)
            row.addWidget(text, 1)
            choose = QPushButton("Assign missile target…")
            choose.clicked.connect(
                lambda checked=False, source_id=source.id, status=text: self.open_target(
                    source_id, status
                )
            )
            row.addWidget(choose)
            column.addLayout(row)
        column.addStretch()

    def open_target(self, source_id: UUID, status: QLabel) -> None:
        dialog = MissileTargetDialog(self.model, source_id, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def update_status() -> None:
            if self.model.get() is not dialog.game or not isValid(status):
                return
            source = dialog.game.db.tgos.get(source_id)
            order = missiletargets.stored(source)
            status.setText(
                f"{source.obj_name}: {order.name if order else 'No assigned target'}"
            )

        dialog.finished.connect(update_status)
        # The map picker temporarily hides this window. QDialog.exec() would
        # finish its nested event loop on hide, before an assignment is made.
        dialog.show()
