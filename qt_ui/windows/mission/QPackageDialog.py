"""Dialogs for creating and editing ATO packages."""

import logging
from typing import Optional

from PySide6.QtCore import QItemSelection, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTimeEdit,
    QVBoxLayout,
    QLineEdit,
    QStackedWidget,
)

from game.ato.flight import Flight
from game.ato.flightplans.planningerror import PlanningError
from game.ato.package import Package
from game.game import Game
from game.radio.radios import RadioFrequency
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.theater.missiontarget import MissionTarget
from qt_ui.models import GameModel, PackageModel
from qt_ui.uiconstants import EVENT_ICONS
from qt_ui.widgets.QFrequencyWidget import QFrequencyWidget
from qt_ui.widgets.ato import QFlightList
from qt_ui.widgets.cards import card, caption, make_transparent
from qt_ui.widgets.controls import (
    button,
    key_value,
    styled_input,
    style_button,
    value_label,
)
from qt_ui.windows.QRadioFrequencyDialog import QRadioFrequencyDialog
from qt_ui.windows.mission.QAutoCreateDialog import QAutoCreateDialog
from qt_ui.windows.mission.refueloffer import offer_for_package
from qt_ui.windows.mission.flight.QFlightCreator import QFlightCreator


class QPackageDialog(QDialog):
    """Base package management dialog.

    The dialogs for creating a new package and editing an existing dialog are
    very similar, and this implements the shared behavior.
    """

    #: Emitted when a change is made to the package.
    package_changed = Signal()

    def __init__(self, game_model: GameModel, model: PackageModel, parent=None) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self.package_model = model
        self.add_flight_dialog: Optional[QFlightCreator] = None

        self.setMinimumSize(1000, 600)
        self.resize(1100, 700)
        self.setWindowTitle(
            f"Mission Package: {self.package_model.mission_target.name}"
        )
        self.setWindowIcon(EVENT_ICONS["strike"])

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        headline = card()
        headline_layout = QVBoxLayout(headline)
        headline_layout.setContentsMargins(14, 10, 14, 10)
        headline_layout.setSpacing(6)
        headline_layout.addWidget(make_transparent(caption("Mission package")))
        title_row = QHBoxLayout()
        target = value_label(self.package_model.mission_target.name)
        target.setTextFormat(Qt.TextFormat.PlainText)
        target.setWordWrap(True)
        target.setStyleSheet(
            "color: #F2F7FA; font-size: 20px; background: transparent; border: none;"
        )
        title_row.addWidget(target, 1)
        self.package_type_text = value_label(self.package_model.description)
        title_row.addWidget(self.package_type_text)
        headline_layout.addLayout(title_row)
        self.package_changed.connect(self.on_package_changed)
        self.package_context = value_label("")
        self.package_context.setWordWrap(True)
        self.package_context.setTextFormat(Qt.TextFormat.PlainText)
        self.package_context.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        headline_layout.addWidget(self.package_context)
        self.layout.addWidget(headline)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(12)
        identity = card()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(0, 6, 0, 6)
        identity_layout.setSpacing(4)
        self.package_name_text = QLineEdit(self.package_model.package.custom_name)
        self.package_name_text.setPlaceholderText("Optional package name")
        self.package_name_text.textChanged.connect(self.on_change_name)
        identity_layout.addWidget(
            key_value("Name", styled_input(self.package_name_text), key_width=84)
        )
        self.freq_widget = QFrequencyWidget(self.package_model.package, game_model)
        make_transparent(self.freq_widget)
        self.freq_widget.layout().setContentsMargins(14, 0, 14, 0)
        for control, text in (
            (self.freq_widget.set_freq_btn, "Set radio"),
            (self.freq_widget.reset_freq_btn, "Reset"),
        ):
            style_button(control)
            control.setText(text)
            control.setAutoDefault(False)
        identity_layout.addWidget(self.freq_widget)
        settings_row.addWidget(identity, 1)

        timing = card()
        timing_layout = QVBoxLayout(timing)
        timing_layout.setContentsMargins(14, 6, 14, 6)
        timing_layout.setSpacing(6)
        timing_layout.addWidget(make_transparent(caption("Time over target")))
        self.tot_column = QHBoxLayout()
        timing_layout.addLayout(self.tot_column)

        self.tot_spinner = QTimeEdit(self.tot_qtime())
        self.tot_spinner.setMinimumTime(QTime(0, 0))
        self.tot_spinner.setDisplayFormat("hh:mm:ss")
        self.tot_spinner.timeChanged.connect(self.save_tot)
        self.tot_spinner.setToolTip(
            "Mission clock time at which the package reaches its target."
        )
        styled_input(self.tot_spinner, 130)
        self.tot_spinner.setEnabled(
            not self.package_model.package.auto_asap
            and self.package_model.package.all_flights_waiting_for_start()
        )
        self.tot_column.addWidget(self.tot_spinner)

        self.auto_asap = QCheckBox("ASAP")
        self.auto_asap.setStyleSheet(
            "QCheckBox { color: #D3DFE8; font-size: 12px; background: transparent; }"
        )
        self.auto_asap.setToolTip(
            "Sets the package TOT to the earliest time that all flights can "
            "arrive at the target."
        )
        self.auto_asap.setChecked(self.package_model.package.auto_asap)
        self.auto_asap.setEnabled(
            self.package_model.package.all_flights_waiting_for_start()
        )
        self.auto_asap.toggled.connect(self.set_asap)
        self.tot_column.addWidget(self.auto_asap)
        self.tot_column.addStretch()

        self.tot_help_label = QLabel(
            '<a href="https://github.com/dcs-retribution/dcs-retribution/wiki/Mission-planning" style="color:#8FC3F0;">Planning help</a>'
        )
        self.tot_help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tot_help_label.setOpenExternalLinks(True)
        self.tot_help_label.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        self.tot_column.addWidget(self.tot_help_label)

        self.timing_hint = value_label("")
        self.timing_hint.setWordWrap(True)
        timing_layout.addWidget(self.timing_hint)
        settings_row.addWidget(timing, 1)
        self.layout.addLayout(settings_row)

        toolbar = QHBoxLayout()
        toolbar.addWidget(caption("Flights"))
        toolbar.addStretch()
        self.add_flight_button = button("Add flight", "primary", self.on_add_flight)
        toolbar.addWidget(self.add_flight_button)
        self.edit_flight_button = button("Edit selected", handler=self.on_edit_flight)
        toolbar.addWidget(self.edit_flight_button)
        self.delete_flight_button = button(
            "Delete selected", handler=self.on_delete_flight
        )
        toolbar.addWidget(self.delete_flight_button)
        self.auto_create_button = button("Auto create", handler=self.on_auto_create)
        self.auto_create_button.setToolTip(
            "Automatically plan flights for an empty package."
        )
        toolbar.addWidget(self.auto_create_button)
        for control in (
            self.add_flight_button,
            self.edit_flight_button,
            self.delete_flight_button,
            self.auto_create_button,
        ):
            control.setAutoDefault(False)
        self.layout.addLayout(toolbar)

        self.package_view = QFlightList(self.game_model, self.package_model)
        self.package_view.flight_deleted.connect(self.on_flight_deleted)
        self.package_view.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )
        self.flight_stack = QStackedWidget()
        self.flight_stack.addWidget(self.package_view)
        empty_card = card()
        empty_layout = QVBoxLayout(empty_card)
        empty_layout.addStretch()
        empty_title = value_label("No flights assigned")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = value_label(
            "Add a flight or use Auto create to plan this package."
        )
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)
        empty_layout.addStretch()
        self.flight_stack.addWidget(empty_card)
        self.layout.addWidget(self.flight_stack, 1)

        self.departures_label = value_label("")
        self.departures_label.setTextFormat(Qt.TextFormat.PlainText)
        self.departures_label.setWordWrap(True)
        self.layout.addWidget(self.departures_label)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        self.footer_hint = value_label(
            "Double-click a flight to edit its plan and loadout."
        )
        self.button_layout.addWidget(self.footer_hint)
        self.button_layout.addStretch()

        self.setLayout(self.layout)

        self.package_model.tot_changed.connect(self.update_tot)
        self.package_model.tot_changed.connect(self.update_package_context)
        self.package_model.rowsInserted.connect(self.update_package_context)
        self.package_model.rowsRemoved.connect(self.update_package_context)
        self.package_model.dataChanged.connect(self.update_package_context)

        self.accepted.connect(self.on_save)
        self.finished.connect(self.on_close)
        self.rejected.connect(self.on_cancel)
        self.update_package_context()

    @property
    def game(self) -> Game:
        return self.game_model.game

    def tot_qtime(self) -> QTime:
        tot = self.package_model.package.time_over_target
        return QTime(tot.hour, tot.minute, tot.second)

    def on_cancel(self) -> None:
        pass

    def on_close(self, _result) -> None:
        EventStream.put_nowait(
            GameUpdateEvents().update_flights_in_package(self.package_model.package)
        )

    def on_save(self) -> None:
        # TODO: Cache package start state and only update if valid
        if not self.package_valid():
            return
        self.save_tot()

    def save_tot(self) -> None:
        # TODO: This is going to break horribly around midnight.
        time = self.tot_spinner.time()
        self.package_model.set_tot(
            self.package_model.package.time_over_target.replace(
                hour=time.hour(), minute=time.minute(), second=time.second()
            )
        )

    def set_asap(self, checked: bool) -> None:
        self.package_model.set_asap(checked)
        self.tot_spinner.setEnabled(not self.package_model.package.auto_asap)
        self.update_tot()

    def update_tot(self) -> None:
        self.tot_spinner.setTime(self.tot_qtime())

    def on_selection_changed(
        self, selected: QItemSelection, _deselected: QItemSelection
    ) -> None:
        """Updates the state of the delete button."""
        self.delete_flight_button.setEnabled(not selected.empty())
        self.edit_flight_button.setEnabled(not selected.empty())

    def on_edit_flight(self) -> None:
        if self.package_view.selected_item is not None:
            self.package_view.edit_flight(self.package_view.currentIndex())

    def on_add_flight(self) -> None:
        """Opens the new flight dialog."""
        self.add_flight_dialog = QFlightCreator(
            self.game,
            self.package_model.package,
            is_ownfor=self.game_model.is_ownfor,
            parent=self.window(),
        )
        self.add_flight_dialog.created.connect(self.add_flight)
        self.add_flight_dialog.show()

    def add_flight(self, flight: Flight) -> None:
        """Adds the new flight to the package."""
        self.package_model.add_flight(flight)
        try:
            flight.recreate_flight_plan()
            self.package_model.update_tot()
            # The same questions the flight editor asks on the way out. A flight that
            # is created short of fuel never goes through that editor, so without this
            # nobody ever asks about it.
            EventStream.put_nowait(
                offer_for_package(
                    self.package_model,
                    self,
                    GameUpdateEvents().new_flight(flight),
                    only=[flight],
                )
            )
        except PlanningError as ex:
            self.package_model.delete_flight(flight)
            logging.exception("Could not create flight")
            QMessageBox.critical(
                self, "Could not create flight", str(ex), QMessageBox.StandardButton.Ok
            )
        self.auto_create_button.setDisabled(True)
        # noinspection PyUnresolvedReferences
        self.package_changed.emit()

    def on_delete_flight(self) -> None:
        """Removes the selected flight from the package."""
        flight = self.package_view.selected_item
        if flight is None:
            logging.error(f"Cannot delete flight when no flight is selected.")
            return
        self.package_model.cancel_or_abort_flight(flight)
        self.on_flight_deleted()

    def on_flight_deleted(self) -> None:
        """What follows a cancelled flight, however it was cancelled.

        The Delete key goes straight to the list, so this is the shared tail: an empty
        package is offered its auto-create button again.
        """
        if len(list(self.package_model.flights)) == 0:
            self.auto_create_button.setDisabled(False)
        # noinspection PyUnresolvedReferences
        self.package_changed.emit()

    def on_auto_create(self) -> None:
        """Opens the new flight dialog."""
        auto_create_dialog = QAutoCreateDialog(
            self.game,
            self.package_model,
            self.game_model.is_ownfor,
            parent=self.window(),
        )
        if auto_create_dialog.exec_() == QDialog.DialogCode.Accepted:
            events = GameUpdateEvents()
            for f in self.package_model.package.flights:
                events = events.new_flight(f)
            # A whole package at once, so the questions are asked once for it: one
            # tanker serves the package, and the moment one is agreed to the rest of
            # its flights have nothing left to ask.
            EventStream.put_nowait(offer_for_package(self.package_model, self, events))
            self.package_model.update_tot()
            self.package_changed.emit()
            self.auto_create_button.setDisabled(True)

    def on_change_name(self) -> None:
        self.package_model.package.custom_name = self.package_name_text.text()

    def on_open_radio(self) -> None:
        self.package_frequency_dialog = QRadioFrequencyDialog(
            parent=self.window(), container=self.package_model.package
        )
        self.package_frequency_dialog.accepted.connect(self.assign_frequency)
        self.package_frequency_dialog.show()

    def assign_frequency(self):
        hz = round(self.package_frequency_dialog.frequency_input.value() * 10**6)
        self.package_model.package.frequency = RadioFrequency(hertz=hz)
        self.package_changed.emit()

    def on_package_changed(self):
        self.package_type_text.setText(self.package_model.description)
        self.freq_widget.check_freq()
        self.update_package_context()

    def update_package_context(self) -> None:
        package = self.package_model.package
        flights = list(package.flights)
        self.package_type_text.setText(self.package_model.description)
        self.flight_stack.setCurrentIndex(0 if flights else 1)
        self.auto_create_button.setEnabled(not flights)
        selected = self.package_view.selected_item is not None
        self.edit_flight_button.setEnabled(selected)
        self.delete_flight_button.setEnabled(selected)
        waiting = package.all_flights_waiting_for_start()
        self.tot_spinner.setEnabled(waiting and not package.auto_asap)
        self.auto_asap.setEnabled(waiting)
        self.timing_hint.setText(
            "Timing is locked while flights are active."
            if not waiting
            else (
                "Earliest arrival shared by all flights."
                if package.auto_asap
                else "Manual arrival time for this package."
            )
        )
        if not flights:
            self.package_context.setText("0 flights  ·  0 aircraft  ·  0 player slots")
            self.departures_label.setText("")
            return

        player_slots = sum(f.client_count for f in flights)
        missing_pilots = sum(f.missing_pilots for f in flights)
        departures = sorted({f.departure.name for f in flights})
        summary = [
            f"{len(flights)} flight{'' if len(flights) == 1 else 's'}",
            f"{sum(f.count for f in flights)} aircraft",
            f"{player_slots} player slot{'' if player_slots == 1 else 's'}",
        ]
        if missing_pilots:
            summary.append(f"Missing pilots: {missing_pilots}")
        self.package_context.setText("  ·  ".join(summary))
        self.departures_label.setText(f"Departures: {', '.join(departures)}")

    def on_reset_radio(self):
        self.package_model.package.frequency = None
        self.package_freq_text.setText("AUTO")

    def package_valid(self) -> bool:
        """Validates the package before saving.

        Returns:
            True if the package is valid, False otherwise.
        """
        # Validate the package has more than just escort flights but allow empty packages
        if len(self.package_model.package.flights) == 0:
            return True
        if any(
            flight.flight_type.name not in {"ESCORT", "SEAD_ESCORT"}
            for flight in self.package_model.package.flights
        ):
            return True
        else:
            for flight in list(self.package_model.package.flights):
                self.package_model.cancel_or_abort_flight(flight)
            QMessageBox.critical(
                self,
                "Invalid Package",
                "Package cannot contain only escort flights.",
                QMessageBox.StandardButton.Ok,
            )
            return False


class QNewPackageDialog(QPackageDialog):
    """Dialog window for creating a new package.

    New packages do not affect the ATO model until they are saved.
    """

    def __init__(
        self, game_model: GameModel, target: MissionTarget, parent=None
    ) -> None:
        super().__init__(
            game_model,
            PackageModel(
                Package(target, game_model.game.db.flights, auto_asap=True), game_model
            ),
            parent=parent,
        )
        self.ato_model = (
            game_model.ato_model if game_model.is_ownfor else game_model.red_ato_model
        )

        # In the *new* package dialog, a package has been created and may have aircraft
        # assigned to it, but it is not a part of the ATO until the user saves it.
        #
        # Other actions (modifying settings, closing some other dialogs like the base
        # menu) can cause a Game update which will forcibly close this window without
        # either accepting or rejecting it, so we neither save the package nor release
        # any allocated units.
        #
        # While it would be preferable to be able to update this dialog as needed in the
        # event of game updates, the quick fix is to just not allow interaction with
        # other UI elements until the new package has either been finalized or canceled.
        self.setModal(True)

        self.cancel_button = button("Cancel", handler=self.reject)
        self.cancel_button.setAutoDefault(False)
        self.button_layout.addWidget(self.cancel_button)
        self.save_button = button("Save package", "primary", self.accept)
        self.save_button.setAutoDefault(False)
        self.button_layout.addWidget(self.save_button)

    def on_save(self) -> None:
        """Saves the created package.

        Empty packages may be created. They can be modified later, and will have
        no effect if empty when the mission is generated.
        """
        if not super().package_valid():
            return
        super().on_save()
        self.ato_model.add_package(self.package_model.package)

    def on_cancel(self) -> None:
        super().on_cancel()
        for flight in list(self.package_model.package.flights):
            self.package_model.cancel_or_abort_flight(flight)


class QEditPackageDialog(QPackageDialog):
    """Dialog window for editing an existing package.

    Changes to existing packages occur immediately.
    """

    def __init__(self, gm: GameModel, package: PackageModel) -> None:
        super().__init__(gm, package)
        self.ato_model = gm.ato_model if gm.is_ownfor else gm.red_ato_model

        self.delete_button = button("Delete package", "danger", self.on_delete)
        self.delete_button.setAutoDefault(False)
        self.button_layout.addWidget(self.delete_button)

        self.done_button = button("Done", "primary", self.accept)
        self.done_button.setAutoDefault(False)
        self.button_layout.addWidget(self.done_button)

    def on_delete(self) -> None:
        """Removes the viewed package from the ATO."""
        # The ATO model returns inventory for us when deleting a package.
        self.ato_model.cancel_or_abort_package(self.package_model.package)
        self.close()
