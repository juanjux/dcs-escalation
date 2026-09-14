"""Dialog window for editing flights."""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game.ato.flight import Flight
from game.ato.flightplans.planningerror import PlanningError
from game.ato.flightplans.refueledit import (
    RefuelVerdict,
    add_refuel_waypoint,
    can_offer_a_tanker,
    plan_tanker_for,
    planned_tanker_name,
    refuel_verdict,
    refuelling_system,
    remove_refuel_waypoint,
)
from game.squadrons import Squadron
from game.server import EventStream
from game.sim import GameUpdateEvents
from qt_ui.models import GameModel, PackageModel
from qt_ui.uiconstants import EVENT_ICONS
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.mission.flight.header import FlightHeader
from qt_ui.windows.mission.flight.QFlightPlanner import QFlightPlanner


class QEditFlightDialog(QDialog):
    """Dialog window for editing flight plans and loadouts."""

    def __init__(
        self,
        game_model: GameModel,
        package_model: PackageModel,
        flight: Flight,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)

        self.game_model = game_model
        self.flight = flight
        self.package_model = package_model
        self.events = GameUpdateEvents()

        self.setWindowTitle("Edit flight")
        self.setWindowIcon(EVENT_ICONS["strike"])
        # Deliberately NOT modal. Picking another flight in the main window's list is
        # meant to bring it up here, and a modal dialog eats that click -- the window
        # flashed and nothing happened. Everything here applies as it is changed, so
        # there is no half-finished state a stray click could leave behind.
        self.setModal(False)
        # On the way out, ask about what was just edited. It belongs here and not in
        # a handler: connecting it inside on_go_to_package meant it was connected on
        # one path out of four, and there after the accept() that would have fired it.
        self.finished.connect(self.on_close)

        self._layout = QVBoxLayout()
        self.header: Optional[FlightHeader] = None
        self.flight_planner: Optional[QFlightPlanner] = None
        self._build_for_flight()
        self._layout.addWidget(self._footer())
        self.setLayout(self._layout)

    # --- the flight this dialog is showing ----------------------------------

    def _build_for_flight(self) -> None:
        """Put the header and the tabs in, for whichever flight is current."""
        # Above the tabs and on every one of them: what flies, whose it is, where it
        # is going, and what still needs deciding.
        self.header = FlightHeader(self.flight)
        self._layout.insertWidget(0, self.header)

        self.flight_planner = QFlightPlanner(
            self.package_model, self.flight, self.game_model
        )
        self.flight_planner.squadron_changed.connect(self.on_squadron_change)
        self.flight_planner.header_changed.connect(self.header.refresh)
        self.header.jump_to_tab.connect(self.flight_planner.setCurrentIndex)
        self.header.switch_to_flight.connect(self.switch_to)
        self._layout.insertWidget(1, self.flight_planner)

    def switch_to(self, flight: Flight) -> None:
        """Show another flight of the same package without closing.

        Editing a package means going round its flights, and every trip round used to
        cost closing this and finding the next one in the list behind it. The checks
        that run when the dialog closes run here too, on the flight being left: they
        are about what you just changed, not about the window.
        """
        if flight is self.flight or flight.package is not self.flight.package:
            return

        tab = self.flight_planner.currentIndex() if self.flight_planner else 0
        self._apply_pending_changes()

        for widget in (self.header, self.flight_planner):
            if widget is not None:
                self._layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()

        self.flight = flight
        self._build_for_flight()
        if self.flight_planner is not None:
            self.flight_planner.setCurrentIndex(tab)
        self.game_model.ato_model.client_slots_changed.emit()

    def _footer(self) -> QWidget:
        """A way out, and a way up.

        Everything here is applied as you change it -- there is nothing to confirm --
        so the footer says so rather than offering an OK that would imply otherwise.
        The package is one level up and was reachable only by closing this and finding
        it again on the map.
        """
        hint = QLabel("Changes apply immediately to the package")
        hint.setStyleSheet(
            "font-size: 11px; color: #7C8B99; background: transparent; border: none;"
        )

        to_package = QPushButton("Go to package")
        to_package.setFixedHeight(28)
        to_package.setStyleSheet(
            "QPushButton { background: #26343F; color: #B7C6D2;"
            " border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 14px;"
            " font-size: 12px; }"
            "QPushButton:hover { background: #33475C; }"
        )
        to_package.clicked.connect(self.on_go_to_package)

        done = QPushButton("Done")
        done.setFixedHeight(28)
        done.setStyleSheet(
            "QPushButton { background: #8FC3F0; color: #0F1922; border: none;"
            " border-radius: 3px; padding: 0 20px; font-size: 12px;"
            " font-weight: 600; }"
            "QPushButton:hover { background: #A6D0F4; }"
        )
        done.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.setContentsMargins(14, 0, 6, 0)
        row.setSpacing(10)
        row.addWidget(hint)
        row.addStretch()
        row.addWidget(to_package)
        row.addWidget(done)
        holder = QWidget()
        holder.setFixedHeight(44)
        make_transparent(holder)
        holder.setLayout(row)
        return holder

    def on_go_to_package(self) -> None:
        from qt_ui.dialogs import Dialog

        self.accept()
        Dialog.open_edit_package_dialog(self.package_model)

    def on_squadron_change(self, flight: Flight):
        self.events = GameUpdateEvents().delete_flight(self.flight)
        self.events = self.events.new_flight(flight)
        self.game_model.ato_model.client_slots_changed.emit()
        self.flight = flight
        self.reject()
        new_dialog = QEditFlightDialog(
            self.game_model, self.package_model, flight, self.parent()
        )
        new_dialog.show()

    def on_close(self, _result) -> None:
        self._apply_pending_changes()
        self.game_model.ato_model.client_slots_changed.emit()

    def _apply_pending_changes(self) -> None:
        """The questions that are asked about what was just edited.

        Called when the dialog closes, and when it swaps to another flight of the same
        package -- the edits are the same edits either way, and asking about them only
        on the way out would have let a trip round the package skip every one.
        """
        self._recreate_package_if_standoff_changed()
        self._offer_to_move_the_refuelling_waypoint()
        self.events = self.events.update_flight(self.flight)
        EventStream.put_nowait(self.events)
        self.events = GameUpdateEvents()

    def _recreate_package_if_standoff_changed(self) -> None:
        """Move the ingress point when the package's stand-off range changed.

        Editing the payload does not rebuild the flight plan, so the ingress point can
        be left at a distance that no longer matches the loadout (e.g. a Kh-22 was
        added or removed). The package waypoints remember the stand-off range they were
        built with, so if it now differs we offer to regenerate the package's flight
        plans (which resets their routes).
        """
        package = self.flight.package
        waypoints = package.waypoints
        if waypoints is None:
            return
        if waypoints.standoff_range == package.max_standoff_range():
            return

        result = QMessageBox.question(
            self,
            "Update flight plan?",
            (
                "The stand-off weapons in this package changed, so the ingress point "
                "should move to match the new launch range. This will regenerate the "
                "flight plan(s) for the package and reset any manual route changes. "
                "Continue?"
            ),
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        package.waypoints = None
        for flight in package.flights:
            try:
                flight.recreate_flight_plan()
                self.events = self.events.update_flight(flight)
            except PlanningError:
                logging.exception(
                    "Could not regenerate flight plan after stand-off change"
                )

    def _offer_to_move_the_refuelling_waypoint(self) -> None:
        """Ask again about the tanker, now that the player has had their way.

        The planner decides this while it builds the plan, and never again. Taking the
        drop tanks off, or taking the route down low, leaves a flight short of fuel
        with nothing noticing -- which is exactly what it looks like from the outside:
        "I made it not have enough and it did not plan me a tanker."

        Unlike the stand-off question above, saying yes here does NOT rebuild the plan.
        Rebuilding would throw away the edits that made the flight short in the first
        place, which is the opposite of helpful.
        """
        verdict = refuel_verdict(self.flight)
        if verdict is RefuelVerdict.NOTHING_TO_DO:
            return

        if verdict is RefuelVerdict.SHOULD_ADD:
            self._ask_about_adding()
            return

        result = QMessageBox.question(
            self,
            "Remove the refuelling waypoint?",
            (
                "This flight now carries comfortably more fuel than its route asks "
                "for, so it no longer needs the detour to the tanker. Remove the "
                "refuelling waypoint?"
                "\n\nThe rest of the route is left exactly as you set it."
            ),
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        if remove_refuel_waypoint(self.flight):
            self.events = self.events.update_flight(self.flight)

    def _ask_about_adding(self) -> None:
        """One question, two answers: the waypoint on its own, or with a tanker.

        These used to be two dialogs in a row, and they contradicted each other -- the
        first said no tanker was planned, and the second then offered one. What the
        player is really choosing between is a waypoint that hopes to find a tanker and
        a waypoint with one sent to meet it, so it is one choice with two buttons. The
        second is greyed out, with the reason on screen, when there is nothing to send.
        """
        available = can_offer_a_tanker(self.flight)
        flying = planned_tanker_name(self.flight)

        if available:
            situation = (
                "A tanker can be sent with it, orbiting at the refuelling point, "
                "which is clear of enemy air defences."
            )
        elif flying is not None:
            situation = (
                f"No tanker is free to send, but {flying} is already flying this turn "
                "and the flight will go looking for it."
            )
        else:
            situation = (
                "No tanker is free to send and none is flying this turn, so the "
                "waypoint will do nothing until you plan one."
            )

        box = QMessageBox(self)
        box.setWindowTitle("Add a refuelling waypoint?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            "This flight no longer has the fuel for its route. A refuelling waypoint "
            f"can be added on the way home. {situation}"
            "\n\nThe rest of the route is left exactly as you set it."
        )
        with_tanker = box.addButton(
            "Add waypoint and tanker", QMessageBox.ButtonRole.AcceptRole
        )
        waypoint_only = box.addButton(
            "Add waypoint only", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        with_tanker.setEnabled(bool(available))
        box.setDefaultButton(with_tanker if available else waypoint_only)
        box.exec()

        clicked = box.clickedButton()
        if clicked not in (with_tanker, waypoint_only):
            return
        if not add_refuel_waypoint(self.flight):
            return
        self.events = self.events.update_flight(self.flight)
        if clicked is not with_tanker:
            return

        squadron = self._choose_tanker(available)
        if squadron is None:
            return

        self._plan_the_tanker(squadron)

    def _choose_tanker(self, available: list[Squadron]) -> Optional[Squadron]:
        """Which tanker to send, when the wing has more than one kind sitting idle.

        Nothing in the unit data says whether a receiver has a probe or a receptacle,
        so this is not a choice that can be made for the player -- send a Hornet to a
        boom-only KC-135 and it comes home empty. Each option says which system it
        offers; picking is a second's work for someone who knows what they are flying.
        """
        if len(available) == 1:
            # Consent was given on the way in; there is nothing left to choose.
            return available[0]

        labels = [
            f"{squadron.aircraft} ({refuelling_system(squadron)}) —"
            f" {squadron.name} at {squadron.location}"
            for squadron in available
        ]
        choice, accepted = QInputDialog.getItem(
            self,
            "Which tanker?",
            (
                "More than one is free. A receiver with a probe cannot take fuel from "
                "a boom, and nothing in the aircraft data says which this flight has, "
                "so the choice is yours."
            ),
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return available[labels.index(choice)]

    def _plan_the_tanker(self, squadron: Squadron) -> None:
        tanker = plan_tanker_for(self.flight, squadron)
        self.package_model.add_flight(tanker)
        try:
            tanker.recreate_flight_plan()
            self.package_model.update_tot()
            self.events = self.events.new_flight(tanker)
        except PlanningError:
            logging.exception("Could not plan the tanker")
            self.package_model.delete_flight(tanker)
            QMessageBox.critical(
                self,
                "Could not plan the tanker",
                "The tanker could not be given a flight plan, so it has not been "
                "added. The refuelling waypoint is still there.",
                QMessageBox.StandardButton.Ok,
            )
