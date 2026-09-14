"""The popups that add or replace a squadron.

Unchanged from the form this dialog replaced: they ask four questions and hand back a
squadron, which was never the part that was wrong.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from game.dcs.aircrafttype import AircraftType
from game.squadrons.squadrondef import SquadronDef
from game.theater import ControlPoint
from qt_ui.widgets.combos.primarytaskselector import PrimaryTaskSelector
from .common import SquadronBaseSelector


class SquadronAircraftTypeSelector(QComboBox):
    def __init__(
        self, types: set[AircraftType], selected_aircraft: Optional[str]
    ) -> None:
        super().__init__()
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        for type in sorted(types, key=lambda type: type.display_name):
            self.addItem(type.display_name, type)

        if selected_aircraft:
            self.setCurrentText(selected_aircraft)


class SquadronDefSelector(QComboBox):
    def __init__(
        self,
        squadron_defs: dict[AircraftType, list[SquadronDef]],
        aircraft: Optional[AircraftType],
        allow_random: bool = True,
    ) -> None:
        super().__init__()
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.squadron_defs = squadron_defs
        self.allow_random = allow_random
        self.set_aircraft_type(aircraft)

    def set_aircraft_type(self, aircraft: Optional[AircraftType]):
        self.clear()
        if self.allow_random:
            self.addItem("None (Random)", None)
        if aircraft and aircraft in self.squadron_defs:
            for squadron_def in sorted(
                self.squadron_defs[aircraft], key=lambda squadron_def: squadron_def.name
            ):
                if not squadron_def.claimed:
                    squadron_name = squadron_def.name
                    if squadron_def.nickname:
                        squadron_name += " (" + squadron_def.nickname + ")"
                    self.addItem(squadron_name, squadron_def)
        self.setCurrentIndex(0)


class SquadronConfigPopup(QDialog):
    def __init__(
        self,
        selected_aircraft: Optional[str],
        types: set[AircraftType],
        bases: list[ControlPoint],
        squadron_defs: dict[AircraftType, list[SquadronDef]],
    ) -> None:
        super().__init__()

        self.setWindowTitle(f"Add new Squadron")

        self.column = QVBoxLayout()
        self.setLayout(self.column)

        self.column.addWidget(QLabel("Aircraft:"))
        self.aircraft_type_selector = SquadronAircraftTypeSelector(
            types, selected_aircraft
        )
        self.aircraft_type_selector.currentIndexChanged.connect(
            self.on_aircraft_selection
        )
        self.column.addWidget(self.aircraft_type_selector)

        self.column.addWidget(QLabel("Primary task:"))
        self.primary_task_selector = PrimaryTaskSelector(
            self.aircraft_type_selector.currentData()
        )
        self.column.addWidget(self.primary_task_selector)

        self.column.addWidget(QLabel("Base:"))
        self.squadron_base_selector = SquadronBaseSelector(
            bases, None, self.aircraft_type_selector.currentData()
        )
        self.column.addWidget(self.squadron_base_selector)

        self.column.addWidget(QLabel("Preset:"))
        self.squadron_def_selector = SquadronDefSelector(
            squadron_defs, self.aircraft_type_selector.currentData()
        )
        self.column.addWidget(self.squadron_def_selector)

        self.column.addStretch()

        self.button_layout = QHBoxLayout()
        self.column.addLayout(self.button_layout)

        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(lambda state: self.accept())
        self.update_accept_button()
        self.button_layout.addWidget(self.accept_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(lambda state: self.reject())
        self.button_layout.addWidget(self.cancel_button)

    def update_accept_button(self) -> None:
        enabled = (
            self.aircraft_type_selector.currentData() is not None
            and self.squadron_base_selector.currentData() is not None
            and self.primary_task_selector.selected_task is not None
        )
        self.accept_button.setEnabled(enabled)

    def on_aircraft_selection(self) -> None:
        self.squadron_base_selector.set_aircraft_type(
            self.aircraft_type_selector.currentData()
        )
        self.squadron_def_selector.set_aircraft_type(
            self.aircraft_type_selector.currentData()
        )
        self.primary_task_selector.set_aircraft(
            self.aircraft_type_selector.currentData()
        )
        self.update_accept_button()
        self.update()


class PresetSquadronSelector(QDialog):
    def __init__(
        self,
        aircraft: AircraftType,
        squadron_defs: dict[AircraftType, list[SquadronDef]],
    ) -> None:
        super().__init__()

        self.setWindowTitle(f"Choose preset squadron")

        self.column = QVBoxLayout()
        self.setLayout(self.column)

        self.column.addWidget(QLabel("Preset:"))
        self.squadron_def_selector = SquadronDefSelector(
            squadron_defs, aircraft, allow_random=False
        )
        self.column.addWidget(self.squadron_def_selector)

        self.column.addStretch()

        self.button_layout = QHBoxLayout()
        self.column.addLayout(self.button_layout)

        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(lambda state: self.accept())
        self.button_layout.addWidget(self.accept_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(lambda state: self.reject())
        self.button_layout.addWidget(self.cancel_button)
