from typing import Optional, Type

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QLineEdit,
    QHBoxLayout,
    QStyledItemDelegate,
    QToolTip,
    QWidget,
    QScrollArea,
    QFrame,
)
from dcs.unittype import FlyingType

from game import Game
from game.ato.flight import Flight
from game.ato.flightroster import FlightRoster
from game.ato.flightmember import apply_default_player_laser_code
from game.ato.loadouts import Loadout, get_default_loadout_override
from game.ato.package import Package
from game.ato.starttype import StartType
from game.squadrons.squadron import Squadron
from game.theater import ControlPoint, OffMapSpawn
from qt_ui.uiconstants import EVENT_ICONS
from qt_ui.widgets.QFlightSizeSpinner import QFlightSizeSpinner
from qt_ui.widgets.searchablecombo import LOADOUT_SEARCH_FLOOR, SearchableComboBox
from qt_ui.widgets.cards import card, caption, make_transparent
from qt_ui.widgets.controls import button, key_value, styled_input, value_label
from qt_ui.widgets.combos.QAircraftTypeSelector import QAircraftTypeSelector
from qt_ui.widgets.combos.QArrivalAirfieldSelector import QArrivalAirfieldSelector
from qt_ui.widgets.combos.QFlightTypeComboBox import QFlightTypeComboBox
from qt_ui.windows.mission.flight.SquadronSelector import SquadronSelector
from qt_ui.windows.mission.flight.settings.QFlightSlotEditor import FlightRosterEditor


class QFlightCreator(QDialog):
    created = Signal(Flight)

    def __init__(
        self, game: Game, package: Package, is_ownfor: bool, parent=None
    ) -> None:
        super().__init__(parent=parent)
        self.setMinimumSize(880, 620)
        self.resize(960, 700)

        self.game = game
        self.package = package
        self.custom_name_text = None

        # Make dialog modal to prevent background windows to close unexpectedly.
        self.setModal(True)

        self.setWindowTitle("Create flight")
        self.setWindowIcon(EVENT_ICONS["strike"])

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        headline = card()
        headline_layout = QVBoxLayout(headline)
        headline_layout.setContentsMargins(14, 10, 14, 10)
        headline_layout.addWidget(make_transparent(caption("New flight")))
        target = value_label(package.target.name)
        target.setTextFormat(Qt.TextFormat.PlainText)
        target.setWordWrap(True)
        target.setStyleSheet(
            "color: #F2F7FA; font-size: 20px; background: transparent; border: none;"
        )
        headline_layout.addWidget(target)
        layout.addWidget(headline)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        columns = QHBoxLayout()
        columns.setSpacing(12)
        mission_column = QVBoxLayout()
        mission_column.setSpacing(8)
        mission_column.addWidget(caption("Mission & aircraft"))
        mission = card()
        mission_layout = QVBoxLayout(mission)
        mission_layout.setContentsMargins(0, 6, 0, 10)
        mission_layout.setSpacing(0)
        mission_column.addWidget(mission, 1)
        columns.addLayout(mission_column, 3)
        departure_column = QVBoxLayout()
        departure_column.setSpacing(8)
        departure_column.addWidget(caption("Departure"))
        departure = card()
        departure_layout = QVBoxLayout(departure)
        departure_layout.setContentsMargins(0, 6, 0, 10)
        departure_layout.setSpacing(0)
        departure_column.addWidget(departure, 1)
        columns.addLayout(departure_column, 2)
        body.addLayout(columns)

        self.task_selector = QFlightTypeComboBox(
            self.game.theater, package.target, self.game.settings, is_ownfor
        )
        self.task_selector.setCurrentIndex(0)
        self.task_selector.currentIndexChanged.connect(self.on_task_changed)
        mission_layout.addWidget(
            key_value("Task", styled_input(self.task_selector), key_width=72)
        )

        self.air_wing = self.game.blue.air_wing if is_ownfor else self.game.red.air_wing
        self.aircraft_selector = QAircraftTypeSelector(
            self.air_wing.best_available_aircrafts_for(self.task_selector.currentData())
        )
        self.aircraft_selector.setCurrentIndex(0)
        self.aircraft_selector.currentIndexChanged.connect(self.on_aircraft_changed)
        mission_layout.addWidget(
            key_value("Aircraft", styled_input(self.aircraft_selector), key_width=72)
        )

        self.squadron_selector = SquadronSelector(
            self.air_wing,
            self.task_selector.currentData(),
            self.aircraft_selector.currentData(),
            package.target,
        )
        self.squadron_selector.setCurrentIndex(0)
        mission_layout.addWidget(
            key_value("Squadron", styled_input(self.squadron_selector), key_width=72)
        )

        self.selection_summary = QLabel()
        self.selection_summary.setWordWrap(True)
        self.selection_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.selection_summary.setStyleSheet(
            "color: #B7C6D2; font-size: 12px; background: transparent; border: none;"
        )
        self.selection_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.divert = QArrivalAirfieldSelector(
            [
                cp
                for cp in game.theater.controlpoints
                if cp.captured.is_blue == is_ownfor and not cp.captured.is_neutral
            ],
            self.aircraft_selector.currentData(),
            "None",
        )
        departure_layout.addWidget(
            key_value("Divert", styled_input(self.divert), key_width=72)
        )

        self.flight_size_spinner = QFlightSizeSpinner()
        self.update_max_size(self.squadron_selector.aircraft_available)
        # Same searchable combo as the payload tab: an aircraft's preset list runs to
        # a few hundred, and finding one means scrolling a list ordered by a rule you
        # did not choose.
        self.loadout_selector = SearchableComboBox(
            placeholder="Search loadouts…", threshold=LOADOUT_SEARCH_FLOOR
        )
        self.loadout_selector.setItemDelegate(LoadoutDelegate(self.loadout_selector))
        self._init_loadout_selector()
        mission_layout.addWidget(
            key_value("Loadout", styled_input(self.loadout_selector), key_width=72)
        )
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(14, 8, 14, 0)
        summary_row.addWidget(self.selection_summary)
        mission_layout.addLayout(summary_row)
        mission_layout.addStretch()

        required_start_type = None
        squadron = self.squadron_selector.currentData()
        if squadron is None:
            roster = None
        else:
            required_start_type = squadron.location.required_aircraft_start_type
            roster = FlightRoster(
                squadron, initial_size=self.flight_size_spinner.value()
            )
        self.roster_editor = FlightRosterEditor(squadron, roster)
        self.flight_size_spinner.valueChanged.connect(self.roster_editor.resize)
        self.squadron_selector.currentIndexChanged.connect(self.on_squadron_changed)
        body.addWidget(caption("Assigned pilots"))
        roster_card = card()
        roster_layout = QVBoxLayout(roster_card)
        roster_layout.setContentsMargins(0, 6, 0, 6)
        roster_layout.setSpacing(0)
        self.crew_summary = value_label("")
        size_row = QWidget()
        make_transparent(size_row)
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(14, 4, 14, 8)
        size_layout.addWidget(value_label("Aircraft"))
        size_layout.addWidget(styled_input(self.flight_size_spinner, 68))
        size_layout.addSpacing(12)
        size_layout.addWidget(self.crew_summary)
        size_layout.addStretch()
        roster_layout.addWidget(size_row)
        self.roster_editor.setContentsMargins(0, 0, 0, 0)
        self.roster_editor.setSpacing(0)
        roster_layout.addLayout(self.roster_editor)
        body.addWidget(roster_card)
        body.addStretch()

        self.roster_editor.pilots_changed.connect(self.on_pilot_selected)

        # When an off-map spawn overrides the start type to in-flight, we save
        # the selected type into this value. If a non-off-map spawn is selected
        # we restore the previous choice.
        self.restore_start_type: Optional[StartType] = None
        self.start_type = QComboBox()
        for start_type in StartType:
            self.start_type.addItem(start_type.value, userData=start_type)
        self.start_type.setCurrentText(self.game.settings.default_start_type.value)
        departure_layout.addWidget(
            key_value("Start", styled_input(self.start_type), key_width=72)
        )
        if squadron is not None and required_start_type:
            self.start_type.setEnabled(False)
        self.start_hint = QLabel()
        self.start_hint.setWordWrap(True)
        self.start_hint.setStyleSheet(
            "color: #E0A86B; font-size: 12px; background: transparent; border: none;"
        )
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(14, 8, 14, 8)
        hint_row.addWidget(self.start_hint)
        departure_layout.addLayout(hint_row)
        self.start_type.currentIndexChanged.connect(self._update_start_hint)

        self.custom_name = QLineEdit()
        self.custom_name.setPlaceholderText("Optional flight name")
        self.custom_name.textChanged.connect(self.set_custom_name_text)
        departure_layout.addWidget(
            key_value("Name", styled_input(self.custom_name), key_width=72)
        )
        departure_layout.addStretch()
        for selector in (
            self.task_selector,
            self.aircraft_selector,
            self.squadron_selector,
            self.loadout_selector,
            self.divert,
        ):
            selector.setMinimumContentsLength(12)
            selector.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
        self.loadout_selector.currentIndexChanged.connect(self.update_selection_summary)
        self.flight_size_spinner.valueChanged.connect(self._update_crew_summary)
        self.roster_editor.pilots_changed.connect(self._update_crew_summary)
        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = button("Cancel", handler=self.reject)
        self.cancel_button.setAutoDefault(False)
        footer.addWidget(self.cancel_button)
        self.create_button = button("Create flight", "primary", self.create_flight)
        self.create_button.setAutoDefault(False)
        footer.addWidget(self.create_button)
        layout.addLayout(footer)

        self.setLayout(layout)

        tab_order = [
            self.task_selector,
            self.aircraft_selector,
            self.squadron_selector,
            self.loadout_selector,
            self.divert,
            self.start_type,
            self.custom_name,
            self.flight_size_spinner,
        ]
        for controls in self.roster_editor.pilot_controls:
            tab_order.extend([controls.selector, controls.player_checkbox])
        tab_order.extend([self.cancel_button, self.create_button])
        for first, second in zip(tab_order, tab_order[1:]):
            self.setTabOrder(first, second)

        self.roster_editor.pilots_changed.emit()
        self.update_selection_summary()

        self._update_start_hint()
        self._update_crew_summary()

    def _update_start_hint(self) -> None:
        required = not self.start_type.isEnabled()
        if self.start_type.currentData() == StartType.COLD:
            text = "Cold starts remain vulnerable to OCA/Aircraft attacks."
        else:
            text = "This start type prevents OCA/Aircraft attacks against the flight."
        self.start_hint.setText(
            ("Required by this departure location. " if required else "") + text
        )
        colour = (
            "#8E9DAA" if self.start_type.currentData() == StartType.COLD else "#E0A86B"
        )
        self.start_hint.setStyleSheet(
            f"color: {colour}; font-size: 12px; background: transparent; border: none;"
        )

    def _update_crew_summary(self) -> None:
        roster = self.roster_editor.roster
        players = roster.player_count if roster is not None else 0
        assigned = (
            sum(pilot is not None for pilot in roster.iter_pilots())
            if roster is not None
            else 0
        )
        size = self.flight_size_spinner.value()
        self.crew_summary.setText(
            f"{assigned}/{size} pilots assigned  ·  {players} player slot{'' if players == 1 else 's'}"
        )
        self.create_button.setEnabled(
            self.squadron_selector.currentData() is not None and size > 0
        )

    def reject(self) -> None:
        super().reject()
        # Clear the roster to return pilots to the pool.
        self.roster_editor.replace(None, None)

    def set_custom_name_text(self, text: str):
        self.custom_name_text = text

    def verify_form(self) -> Optional[str]:
        aircraft: Optional[Type[FlyingType]] = self.aircraft_selector.currentData()
        squadron: Optional[Squadron] = self.squadron_selector.currentData()
        divert: Optional[ControlPoint] = self.divert.currentData()
        size: int = self.flight_size_spinner.value()
        if aircraft is None:
            return "You must select an aircraft type."
        if squadron is None:
            return "You must select a squadron."
        if divert is not None and divert.captured != squadron.player:
            return f"{divert.name} is not owned by your coalition."
        available = squadron.untasked_aircraft
        if not available:
            return f"{squadron} has no aircraft available."
        if size > available:
            return f"{squadron} has only {available} aircraft available."
        if size <= 0:
            return f"Flight must have at least one aircraft."
        if self.custom_name_text and "|" in self.custom_name_text:
            return f"Cannot include | in flight name"
        return None

    def create_flight(self) -> None:
        error = self.verify_form()
        if error is not None:
            QMessageBox.critical(
                self, "Could not create flight", error, QMessageBox.StandardButton.Ok
            )
            return

        task = self.task_selector.currentData()
        squadron = self.squadron_selector.currentData()
        divert = self.divert.currentData()
        roster = self.roster_editor.roster

        flight = Flight(
            self.package,
            squadron,
            # A bit of a hack to work around the old API. Not actually relevant because
            # the roster is passed explicitly. Needs a refactor.
            roster.max_size,
            task,
            self.start_type.currentData(),
            divert,
            custom_name=self.custom_name_text,
            roster=roster,
        )

        for member in flight.iter_members():
            apply_default_player_laser_code(
                member, self.game.settings, self.game.laser_code_registry
            )
            member.loadout = self.current_loadout()

        # noinspection PyUnresolvedReferences
        self.created.emit(flight)
        self.accept()

    def on_aircraft_changed(self, index: int) -> None:
        new_aircraft = self.aircraft_selector.itemData(index)
        self.squadron_selector.update_items(
            self.task_selector.currentData(), new_aircraft
        )
        self.divert.change_aircraft(new_aircraft)
        self.roster_editor.pilots_changed.emit()
        if self.aircraft_selector.currentData() is not None:
            self._init_loadout_selector()
        self.update_selection_summary()

    def on_departure_changed(self, departure: ControlPoint) -> None:
        if isinstance(departure, OffMapSpawn):
            previous_type = self.start_type.currentData()
            if previous_type != StartType.IN_FLIGHT:
                self.restore_start_type = previous_type
            self.start_type.setCurrentText(StartType.IN_FLIGHT.value)
            self.start_type.setEnabled(False)
        else:
            self.start_type.setEnabled(True)
            if self.restore_start_type is not None:
                self.start_type.setCurrentText(self.restore_start_type.value)
                self.restore_start_type = None
        self._update_start_hint()

    def on_task_changed(self, index: int) -> None:
        task = self.task_selector.itemData(index)
        self.aircraft_selector.update_items(
            self.air_wing.best_available_aircrafts_for(task)
        )
        self.squadron_selector.update_items(task, self.aircraft_selector.currentData())
        self.update_selection_summary()

    def on_squadron_changed(self, index: int) -> None:
        squadron: Optional[Squadron] = self.squadron_selector.itemData(index)
        self.update_max_size(self.squadron_selector.aircraft_available)
        # Clear the roster first so we return the pilots to the pool. This way if we end
        # up repopulating from the same squadron we'll get the same pilots back.
        self.roster_editor.replace(None, None)
        if squadron is not None:
            self.roster_editor.replace(
                squadron, FlightRoster(squadron, self.flight_size_spinner.value())
            )
            self.on_departure_changed(squadron.location)

            self.roster_editor.pilots_changed.emit()
        self.update_selection_summary()

    def update_max_size(self, available: int) -> None:
        aircraft = self.aircraft_selector.currentData()
        if aircraft is None:
            self.flight_size_spinner.setMaximum(0)
            return

        self.flight_size_spinner.setMaximum(min(available, aircraft.max_group_size))

        default_size = max(2, available, aircraft.max_group_size)
        self.flight_size_spinner.setValue(default_size)

        try:
            self.roster_editor.pilots_changed.emit()
        except AttributeError:
            return

    def on_pilot_selected(self):
        # Pilot selection detected. If this is a player flight, set start_type
        # as configured for players in the settings.
        # Otherwise, set the start_type as configured for AI.
        # https://github.com/dcs-liberation/dcs_liberation/issues/1567

        roster = self.roster_editor.roster
        required_start_type = None
        squadron = self.squadron_selector.currentData()
        if squadron:
            required_start_type = squadron.location.required_aircraft_start_type

        if required_start_type:
            start_type = required_start_type
        elif roster is not None and roster.player_count > 0:
            start_type = self.game.settings.default_start_type_client
        else:
            start_type = self.game.settings.default_start_type

        self.start_type.setCurrentText(start_type.value)
        self.start_type.setEnabled(required_start_type is None)
        self._update_start_hint()

    def current_loadout(self) -> Loadout:
        loadout = self.loadout_selector.currentData()
        if loadout is None:
            return Loadout.empty_loadout()
        return loadout

    def _init_loadout_selector(self):
        self.loadout_selector.clear()
        ac_type = self.aircraft_selector.currentData()
        if ac_type is None or not any(list(Loadout.iter_for_aircraft(ac_type))):
            self.loadout_selector.addItem("No loadouts available", None)
            self.loadout_selector.setDisabled(True)
            self.update_selection_summary()
            return
        else:
            self.loadout_selector.setDisabled(False)
        for loadout in Loadout.iter_for_aircraft(ac_type):
            self.loadout_selector.addItem(loadout.name, loadout)
        task = self.task_selector.currentData()
        # A user-set default (per aircraft + task, set with the payload editor's
        # "Set as default" button) wins over the "Escalation <task>" name
        # conventions, mirroring Loadout.default_for_task_and_aircraft.
        override = get_default_loadout_override(ac_type.dcs_unit_type.id, task)
        candidates = ([override] if override else []) + list(
            Loadout.default_loadout_names_for(task)
        )
        for name in candidates:
            index = self.loadout_selector.findText(name)
            if index != -1:
                self.loadout_selector.setCurrentIndex(index)
                break
        self.update_selection_summary()

    def update_selection_summary(self) -> None:
        task = self.task_selector.currentData()
        aircraft = self.aircraft_selector.currentData()
        squadron = self.squadron_selector.currentData()

        if task is None:
            self.selection_summary.setText(
                "Select a mission task to see compatible aircraft and squadrons."
            )
            return
        if aircraft is None:
            self.selection_summary.setText(
                f"{task.value} is selected for this target, but no compatible aircraft "
                "are currently available in the air wing."
            )
            return
        if squadron is None:
            self.selection_summary.setText(
                f"{aircraft.display_name} can fly {task.value}, but no squadron with a "
                "working runway and spare aircraft is currently available."
            )
            return

        role_alignment = (
            "Primary role"
            if squadron.primary_task == task
            else f"Secondary role (primary: {squadron.primary_task.value})"
        )
        self.selection_summary.setText(
            f"{squadron.location.name}\n"
            f"{squadron.untasked_aircraft} aircraft available  ·  {role_alignment}"
        )


class LoadoutDelegate(QStyledItemDelegate):
    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip:
            loadout = index.data(Qt.UserRole)
            if loadout:
                max_pylon = max(loadout.pylons.keys(), default=0)
                pylons_info = "\n".join(
                    f"Pylon {pylon}: {loadout.pylons.get(pylon, 'Clean')}"
                    for pylon in range(1, max_pylon + 1)
                )
                QToolTip.showText(event.globalPos(), pylons_info, view)
                return True
