"""The questions a flight's fuel raises, wherever the flight came from.

They lived on the flight editor, which is where a player who breaks a flight plan
ends up: take the drop tanks off, take the route down low, and on the way out the
editor asks whether a tanker is wanted. That is the right moment for a flight
somebody edited, and it is the only moment there was -- a flight that has just been
created never goes through it, so a package auto-planned short of fuel, with a
refuelling waypoint and nothing flying to meet it, was never asked about at all.

So they are here instead, and the editor, the Add flight button and the auto-create
button all ask the same questions in the same words.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

from game.ato.flight import Flight
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
from game.ato.flightplans.planningerror import PlanningError
from game.ato.flightplans.refuelneed import has_refuel_waypoint
from game.sim import GameUpdateEvents
from game.squadrons import Squadron
from qt_ui.models import PackageModel
from qt_ui.widgets.controls import style_button


def adding_message(who: str, situation: str, fresh: bool) -> str:
    """The body of the "add a waypoint" question.

    Out here so a test can read it back: it is a run of implicit string concatenation,
    which is where an editing slip leaves a duplicated sentence that nothing notices.
    """
    # "No longer" is wrong for a flight that has only just been planned: it never had
    # the fuel in the first place.
    shortfall = (
        "does not have the fuel for its route"
        if fresh
        else "no longer has the fuel for its route"
    )
    return (
        f"{who} {shortfall}. A refuelling waypoint can be added on the way home. "
        f"{situation}"
        "\n\nThe rest of the route is left exactly as you set it."
    )


class RefuelOffer:
    """Asks one flight whatever its fuel calls for, and plans what is agreed to."""

    def __init__(
        self, flight: Flight, package_model: PackageModel, parent: QWidget
    ) -> None:
        self.flight = flight
        self.package_model = package_model
        self.parent = parent
        self.events = GameUpdateEvents()
        #: The player was asked something and said no. The caller stops there rather
        #: than putting the same question about the next flight of the package.
        self.declined = False

    def ask(self, events: GameUpdateEvents, fresh: bool = False) -> GameUpdateEvents:
        """Whatever this flight needs asking about. Returns events plus any tanker.

        Nothing is rebuilt: saying yes to a tanker does not touch the route. For an
        edited flight rebuilding would throw away the very edits that made it short.

        ``fresh`` is a flight that has only just been planned. The planner puts the
        refuelling waypoint in itself while it builds the layout, so by the time
        anyone looks the waypoint is already there and the question that should have
        been asked -- waypoint, waypoint and a tanker, or neither -- can no longer
        come up. For a new flight it is taken back off and that question is put,
        which is what the waypoint was always meant to be: an offer, not a decision
        made for the player.
        """
        self.events = events
        if fresh and has_refuel_waypoint(self.flight):
            # The planner adding it IS the judgement that the flight is short, so the
            # estimate is not asked again -- without the detour the route is shorter
            # and might read as fine, which would drop a waypoint the flight needs.
            remove_refuel_waypoint(self.flight)
            self._ask_about_adding(fresh=True)
            return self.events
        verdict = refuel_verdict(self.flight)
        if verdict is RefuelVerdict.NOTHING_TO_DO:
            return self.events
        if verdict is RefuelVerdict.SHOULD_ADD:
            self._ask_about_adding()
        elif verdict is RefuelVerdict.NEEDS_A_TANKER:
            self._ask_about_the_tanker()
        else:
            self._ask_about_removing()
        return self.events

    def _ask_about_removing(self) -> None:
        result = QMessageBox.question(
            self.parent,
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
            self.declined = True
            return
        if remove_refuel_waypoint(self.flight):
            self.events = self.events.update_flight(self.flight)

    def _ask_about_adding(self, fresh: bool = False) -> None:
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

        box = QMessageBox(self.parent)
        box.setWindowTitle("Add a refuelling waypoint?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(adding_message(self._who(), situation, fresh))
        with_tanker = style_button(
            box.addButton("Add waypoint and tanker", QMessageBox.ButtonRole.AcceptRole),
            "primary",
        )
        waypoint_only = style_button(
            box.addButton("Add waypoint only", QMessageBox.ButtonRole.AcceptRole)
        )
        style_button(box.addButton(QMessageBox.StandardButton.Cancel))
        with_tanker.setEnabled(bool(available))
        box.setDefaultButton(with_tanker if available else waypoint_only)
        box.exec()

        clicked = box.clickedButton()
        if clicked not in (with_tanker, waypoint_only):
            self.declined = True
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

    def _ask_about_the_tanker(self) -> None:
        """The waypoint is already there, and nothing is flying to meet it.

        The route needs no change here -- only somebody to be at the point the flight
        is already going to.
        """
        available = can_offer_a_tanker(self.flight)
        box = QMessageBox(self.parent)
        box.setWindowTitle("Send a tanker?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"{self._who()} is short of fuel for its route and has a refuelling "
            "waypoint on the way home, but no tanker is flying this turn, so there "
            "will be nothing to meet there. One can be sent to orbit at the point, "
            "which is clear of enemy air defences."
            "\n\nThe route is not touched either way."
        )
        send = style_button(
            box.addButton("Send a tanker", QMessageBox.ButtonRole.AcceptRole),
            "primary",
        )
        style_button(box.addButton(QMessageBox.StandardButton.Cancel))
        box.setDefaultButton(send)
        box.exec()
        if box.clickedButton() is not send:
            self.declined = True
            return

        squadron = self._choose_tanker(available)
        if squadron is None:
            return
        self._plan_the_tanker(squadron)

    def _who(self) -> str:
        """Name the flight: asked from a package, "this flight" is ambiguous."""
        name = str(self.flight.callsign or "")
        return f"{name} ({self.flight.unit_type})" if name else "This flight"

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
            self.parent,
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
                self.parent,
                "Could not plan the tanker",
                "The tanker could not be given a flight plan, so it has not been "
                "added. The refuelling waypoint is still there.",
                QMessageBox.StandardButton.Ok,
            )


def offer_for_package(
    package_model: PackageModel,
    parent: QWidget,
    events: GameUpdateEvents,
    fresh: bool = True,
) -> GameUpdateEvents:
    """Ask about a whole package, which is what creating one produces.

    One tanker serves the package, so the moment one is agreed to the rest of its
    flights have nothing left to ask. And a player who says no is not asked again
    about the next flight: they have answered the question.
    """
    for flight in list(package_model.package.flights):
        if _package_already_has_a_tanker(flight):
            break
        offer = RefuelOffer(flight, package_model, parent)
        events = offer.ask(events, fresh=fresh)
        if offer.declined:
            break
    return events


def _package_already_has_a_tanker(flight: Flight) -> bool:
    from game.ato.flighttype import FlightType

    return any(
        other.flight_type is FlightType.REFUELING for other in flight.package.flights
    )
