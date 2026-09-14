import logging
from typing import Any, Optional, Callable

from PySide6.QtCore import QModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QLabel,
    QGroupBox,
    QSpinBox,
    QGridLayout,
    QComboBox,
    QHBoxLayout,
    QCheckBox,
    QVBoxLayout,
    QPushButton,
    QDialog,
    QWidget,
    QSizePolicy,
)

from game import Game
from game.ato.closestairfields import ClosestAirfields
from game.ato.flight import Flight
from game.ato.flightroster import FlightRoster
from game.ato.iflightroster import IFlightRoster
from game.dcs.aircrafttype import AircraftType
from game.squadrons import Squadron, friendship
from game.squadrons.morale import emoji_for, rank_level
from game.squadrons.pilot import Pilot
from game.theater import ControlPoint, OffMapSpawn
from game.utils import nautical_miles
from qt_ui.models import PackageModel
from qt_ui.rankstars import rank_stars_text
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import mono, styled_input, wrapped_tooltip
from qt_ui.widgets.pilotrow import (
    PaintedPilotCombo,
    PilotItemDelegate,
    row_width_hint,
)

#: The amber of a seat nobody is in.
AMBER = "#E0A86B"


class PilotSelector(PaintedPilotCombo):
    """The seat, painted rather than written.

    Qt draws a combo's current item as plain text, so the five things you pick a pilot
    on -- rank, name, whether he is you, how he is holding up -- arrived as one line in
    one colour, with morale reduced to an emoji. Both the closed box and the popup now
    go through the same painter as the squadron roster.
    """

    available_pilots_changed = Signal()

    #: Room for the drop-down arrow, the view's frame and a scrollbar, so the widest
    #: name is not the last thing to fit.
    POPUP_CHROME_PX = 48

    def __init__(
        self, squadron: Optional[Squadron], roster: Optional[IFlightRoster], idx: int
    ) -> None:
        super().__init__(squadron, affinity_of=self.affinity_of)
        self.roster = roster
        self.pilot_index = idx
        self.setItemDelegate(PilotItemDelegate(squadron, self, self.affinity_of))
        # Once, here: connected inside the rebuild it accumulated a connection per
        # rebuild, and every seat rebuilds whenever any seat changes.
        self.currentIndexChanged.connect(self.replace_pilot)
        # The default policy measures the box once, at its first show. These are
        # rebuilt whenever another selector changes, so a longer name arriving after
        # that was elided for good -- in the box AND in the list, whatever the dialog
        # was widened to, because the popup inherits the box's width.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.rebuild()

    def _fit_popup_to_contents(self) -> None:
        """The list is never narrower than its widest row, even when the box is.

        A rank and a name that do not fit the closed combo are exactly what you open
        it to read, so the popup is allowed to be wider than the widget it hangs off.
        The width comes from the painter's own reckoning, not from the item text, which
        is no longer what is drawn.
        """
        self.view().setMinimumWidth(
            row_width_hint(self.squadron) + self.POPUP_CHROME_PX
        )

    def crew_without_this_seat(self) -> list[Pilot]:
        """Who he would be joining: the other seats, with this one left out."""
        if self.roster is None:
            return []
        return [
            other
            for index, other in enumerate(self.roster.iter_pilots())
            if other is not None and index != self.pilot_index
        ]

    def affinity_of(self, pilot: Optional[Pilot]) -> Optional[float]:
        """How he and the rest of this crew would get on, both directions averaged.

        Both, because the question here is whether they would get on rather than what
        one of them thinks. Nothing for the first seat -- there is nobody to get on
        with yet -- and nothing at all while friendship is off, so the list is
        byte-for-byte what it always was.
        """
        if pilot is None or self.squadron is None:
            return None
        if not getattr(self.squadron, "friendship_in_play", False):
            return None
        others = [
            other for other in self.crew_without_this_seat() if other is not pilot
        ]
        if not others:
            return None
        return friendship.group_affinity(pilot, others)

    def affinity_tooltip(self, pilot: Pilot) -> Optional[str]:
        """What the colour behind his name means, named man by man.

        The only place the player can find out that the wash is about friendship at
        all, so it says the word as well as the men.
        """
        affinity = self.affinity_of(pilot)
        if affinity is None or self.squadron is None:
            return None
        settings = self.squadron.settings
        others = [
            other for other in self.crew_without_this_seat() if other is not pilot
        ]
        pairs = sorted(
            others,
            key=lambda other: abs(
                friendship.points(friendship.group_affinity(pilot, [other]))
            ),
            reverse=True,
        )[:3]
        lines = [
            f"  {other.name}: "
            f"{friendship.band_name(friendship.group_affinity(pilot, [other]), settings)}"
            for other in pairs
        ]
        return wrapped_tooltip(
            "\n".join(
                [f"With this crew: {friendship.band_name(affinity, settings)}"] + lines
            )
        )

    def text_for(self, pilot: Pilot) -> str:
        """The pilot as he is addressed: his seniority, his rank, his name.

        The same five slots the roster paints, so choosing a pilot here and reading the
        squadron dialog are the same act. A combo draws its own text, so these are one
        colour rather than the gold and grey of the list.
        """
        if self.squadron is None:
            return pilot.name
        # How he is holding up is the thing you are choosing on, and this list has no
        # room for the word: one face at the end of the name says it. Not for the
        # player -- he knows how his own week went -- and nothing at all with morale off.
        mood = ""
        if self.squadron.morale_in_play and pilot.has_morale:
            mood = f"  {emoji_for(pilot.morale, self.squadron.settings)}"
        rank = self.squadron.pilot_rank(pilot)
        if rank is None:
            return f"{pilot.name}{mood}"
        stars = rank_stars_text(rank_level(self.squadron.pilot_skill(pilot)))
        return f"{stars}  {rank.abbreviation} {pilot.name}{mood}"

    def _do_rebuild(self) -> None:
        self.clear()
        if self.roster is None or self.pilot_index >= self.roster.max_size:
            self.addItem("No aircraft", None)
            self.setDisabled(True)
            self._fit_popup_to_contents()
            return

        if self.squadron is None:
            raise RuntimeError("squadron cannot be None if roster is set")

        self.setEnabled(True)
        self.addItem("Unassigned", None)
        choices = list(self.squadron.available_pilots)
        current_pilot = self.roster.pilot_at(self.pilot_index)
        if current_pilot is not None and not any(p is current_pilot for p in choices):
            # Only if he is not in the pool already. A save written while rosters gave
            # their crews back without letting go of them has pilots in both places, and
            # the list showed those men twice.
            choices.append(current_pilot)
        # Players first, then by rank, then alphabetically. Squadron.rank_order is the
        # same rule the Air Wing roster sorts by, and it flattens to nothing while Live
        # Pilots is off, leaving the old alphabetical order untouched.
        squadron = self.squadron

        def order(pilot: Pilot) -> tuple[Any, ...]:
            # Rank first, because the list's first job is still "who is my best
            # pilot"; friendship only orders the men who hold the same rank, where
            # experience alone would decide it and the tint is what you are reading.
            rank = tuple(squadron.rank_order(pilot))
            affinity = self.affinity_of(pilot)
            # Sliced rather than unpacked: rank_order is free to say as much or as
            # little as Live Pilots is switched on for, and friendship goes after the
            # first thing it says rather than after all of them.
            return (
                not pilot.player,
                rank[:1],
                -(affinity if affinity is not None else friendship.FRIENDSHIP_START),
                rank[1:],
                pilot.name,
            )

        for pilot in sorted(choices, key=order):
            self.addItem(self.text_for(pilot), pilot)
            tip = self.affinity_tooltip(pilot)
            if tip is not None:
                self.setItemData(self.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        if current_pilot is None:
            self.setCurrentText("Unassigned")
        else:
            self.setCurrentText(self.text_for(current_pilot))
        self._fit_popup_to_contents()

    def rebuild(self) -> None:
        # The contents of the selector depend on the selection of the other selectors
        # for the flight, so changing the selection of one causes each selector to
        # rebuild. A rebuild causes a selection change, so if we don't block signals
        # during a rebuild we'll never stop rebuilding.
        self.blockSignals(True)
        try:
            self._do_rebuild()
        finally:
            self.blockSignals(False)

    def replace_pilot(self, index: QModelIndex) -> None:
        if self.itemText(index) == "No aircraft":
            # The roster resize is handled separately, so we have no pilots to remove.
            return
        pilot = self.itemData(index)
        if pilot == self.roster.pilot_at(self.pilot_index):
            return
        self.roster.set_pilot(self.pilot_index, pilot)
        self.available_pilots_changed.emit()

    def replace(
        self, squadron: Optional[Squadron], new_roster: Optional[FlightRoster]
    ) -> None:
        self.squadron = squadron
        self.roster = new_roster
        self.setItemDelegate(PilotItemDelegate(squadron, self, self.affinity_of))
        self.rebuild()


class PilotControls(QWidget):
    """One seat: its number, who is in it, and whether that is you.

    A row rather than a pair of controls in a form, so an empty seat can carry an
    amber bar and be the one thing on the tab that draws the eye -- an unfilled slot
    discovered at take-off is a mission flown one aircraft short.
    """

    player_toggled = Signal()

    ROW_HEIGHT = 44
    INDEX_WIDTH = 22
    SELECTOR_WIDTH = 440

    def __init__(
        self,
        squadron: Optional[Squadron],
        roster: Optional[FlightRoster],
        idx: int,
        pilots_changed: Signal,
    ) -> None:
        super().__init__()
        self.roster = roster
        self.pilot_index = idx
        self.pilots_changed = pilots_changed
        self.setFixedHeight(self.ROW_HEIGHT)
        make_transparent(self)

        row = QHBoxLayout()
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)

        self.index_label = QLabel(str(idx + 1))
        self.index_label.setFont(mono(12))
        self.index_label.setFixedWidth(self.INDEX_WIDTH)
        self.index_label.setStyleSheet(
            "color: #8E9DAA; background: transparent; border: none;"
        )
        row.addWidget(self.index_label)

        self.selector = PilotSelector(squadron, roster, idx)
        self.selector.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.selector.setMinimumWidth(self.SELECTOR_WIDTH)
        self.selector.setFixedHeight(28)
        self.selector.currentIndexChanged.connect(self.on_pilot_changed)
        self.selector.currentIndexChanged.connect(lambda _index: self.update())
        row.addWidget(self.selector, 1)

        self.player_checkbox = QCheckBox(text="Player")
        self.player_checkbox.setToolTip("Checked if this pilot is a player.")
        self.player_checkbox.setStyleSheet(
            "font-size: 12px; background: transparent; border: none;"
        )
        self.on_pilot_changed(self.selector.currentIndex())
        enabled = False
        if self.roster is not None and squadron is not None:
            enabled = squadron.aircraft.flyable
        self.player_checkbox.setEnabled(enabled)
        row.addWidget(self.player_checkbox)

        self.player_checkbox.toggled.connect(self.on_player_toggled)
        self.setLayout(row)

    @property
    def _has_a_seat(self) -> bool:
        return self.roster is not None and self.pilot_index < self.roster.max_size

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        """An amber bar down the left of a seat nobody is in.

        A seat this flight does not have is left on whatever ground it sits on. It used
        to get a fill of its own, but a fill can only be quiet against the one
        background it was mixed for: on the Crew card it was four shades off the card
        and invisible, while the Create flight dialog, which has no card, turned it
        into a dark slab under every seat past the last one the flight has. The greyed
        "No aircraft" box says the same thing on both.
        """
        painter = QPainter(self)
        try:
            if not self._has_a_seat:
                return
            if self.pilot is None:
                painter.fillRect(QRect(0, 0, 3, self.height()), QColor(AMBER))
        finally:
            painter.end()

    @property
    def pilot(self) -> Optional[Pilot]:
        if self.roster is None or self.pilot_index >= self.roster.max_size:
            return None
        return self.roster.pilot_at(self.pilot_index)

    def on_player_toggled(self, checked: bool) -> None:
        pilot = self.pilot
        if pilot is None:
            logging.error("Cannot toggle state of a pilot when none is selected")
            return
        pilot.player = checked
        self.player_toggled.emit()

        self.pilots_changed.emit()

    def on_pilot_changed(self, index: int) -> None:
        pilot = self.selector.itemData(index)
        self.player_checkbox.blockSignals(True)
        try:
            if self.roster and self.roster.squadron.aircraft.flyable:
                self.player_checkbox.setChecked(pilot is not None and pilot.player)
            else:
                self.player_checkbox.setChecked(False)
        finally:
            if self.roster is not None:
                self.player_checkbox.setEnabled(self.roster.squadron.aircraft.flyable)
            self.player_checkbox.blockSignals(False)
            # on_pilot_changed should emit pilots_changed in its finally block,
            # otherwise the start-type isn't updated if you have a single client
            # pilot which you switch to a non-client pilot
            self.pilots_changed.emit()

    def update_available_pilots(self) -> None:
        self.selector.rebuild()

    def enable_and_reset(self) -> None:
        self.selector.rebuild()
        self.player_checkbox.setEnabled(True)
        self.on_pilot_changed(self.selector.currentIndex())

    def disable_and_clear(self) -> None:
        self.selector.rebuild()
        self.player_checkbox.blockSignals(True)
        try:
            self.player_checkbox.setEnabled(False)
            self.player_checkbox.setChecked(False)
        finally:
            self.player_checkbox.blockSignals(False)

    def replace(
        self, squadron: Optional[Squadron], new_roster: Optional[FlightRoster]
    ) -> None:
        self.roster = new_roster
        if self.roster is None or self.pilot_index >= self.roster.max_size:
            self.disable_and_clear()
        else:
            self.enable_and_reset()
        self.selector.replace(squadron, new_roster)


class FlightRosterEditor(QVBoxLayout):
    MAX_PILOTS = 4
    pilots_changed = Signal()

    def __init__(
        self,
        squadron: Optional[Squadron],
        roster: Optional[IFlightRoster],
    ) -> None:
        super().__init__()
        self.roster = roster

        self.pilot_controls = []
        for pilot_idx in range(self.MAX_PILOTS):

            def make_reset_callback(source_idx: int) -> Callable[[int], None]:
                def callback() -> None:
                    self.update_available_pilots(source_idx)

                return callback

            controls = PilotControls(squadron, roster, pilot_idx, self.pilots_changed)
            controls.selector.available_pilots_changed.connect(
                make_reset_callback(pilot_idx)
            )
            self.pilot_controls.append(controls)
            self.addWidget(controls)

    def update_available_pilots(self, source_idx: int) -> None:
        for idx, controls in enumerate(self.pilot_controls):
            # No need to reset the source of the reset, it was just manually selected.
            if idx != source_idx:
                controls.update_available_pilots()

    def resize(self, new_size: int) -> None:
        if new_size > self.MAX_PILOTS:
            raise ValueError("A flight may not have more than four pilots.")
        if self.roster is not None:
            self.roster.resize(new_size)
        for controls in self.pilot_controls[:new_size]:
            controls.enable_and_reset()
        for controls in self.pilot_controls[new_size:]:
            controls.disable_and_clear()

    def replace(
        self, squadron: Optional[Squadron], new_roster: Optional[FlightRoster]
    ) -> None:
        if self.roster is not None:
            self.roster.clear()
        self.roster = new_roster
        for controls in self.pilot_controls:
            controls.replace(squadron, new_roster)


class QSquadronSelector(QDialog):
    def __init__(self, flight: Flight, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.flight = flight
        self.parent = parent
        self.init()

    def init(self):
        vbox = QVBoxLayout()
        self.setLayout(vbox)

        self.selector = QComboBox()
        air_wing = self.flight.coalition.air_wing
        for squadron in air_wing.best_squadrons_for(
            self.flight.package.target,
            self.flight.flight_type,
            self.flight.roster.max_size,
            self.flight.is_helo,
            True,
            ignore_range=True,
        ):
            if squadron is self.flight.squadron:
                continue
            self.selector.addItem(
                f"{squadron.name} - {squadron.aircraft.variant_id}", squadron
            )

        vbox.addWidget(self.selector)

        hbox = QHBoxLayout()
        accept = QPushButton("Accept")
        accept.clicked.connect(self.accept)
        hbox.addWidget(accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        hbox.addWidget(cancel)

        vbox.addLayout(hbox)


class QFlightSlotEditor(QWidget):
    """The squadron and its seats.

    A plain widget rather than a group box: the card it sits in draws the frame and
    the caption above it, so a title inside a second border would be the same word
    twice.
    """

    flight_resized = Signal(int)
    squadron_changed = Signal(Flight)

    def __init__(
        self,
        package_model: PackageModel,
        flight: Flight,
        game: Game,
    ):
        super().__init__()
        self.package_model = package_model
        self.flight = flight
        self.game = game
        self.closest_airfields = ClosestAirfields(
            flight.package.target,
            list(game.theater.control_points_for(self.flight.coalition.player)),
        )
        available = self.flight.squadron.untasked_aircraft
        max_count = self.flight.count + available
        if max_count > 4:
            max_count = 4

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(0)
        layout.addWidget(self._squadron_strip(max_count))

        self.roster_editor = FlightRosterEditor(flight.squadron, flight.roster)
        layout.addLayout(self.roster_editor)

        self.setLayout(layout)

    def _squadron_strip(self, max_count: int) -> QWidget:
        """Whose flight this is, how many are going, and how many are left to send.

        One strip above the seats rather than two rows of a form: the squadron and its
        base are context for the roster, not two more fields to fill in.
        """
        squadron = self.flight.squadron

        name = QLabel(squadron.name)
        name.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #F2F7FA;"
            " background: transparent; border: none;"
        )

        detail = f'"{squadron.nickname}"' if squadron.nickname else ""
        detail = f"{detail}  {squadron.location}".strip()
        base = QLabel(detail)
        base.setStyleSheet(
            "font-size: 12px; color: #7C8B99; background: transparent; border: none;"
        )

        ready = len(list(squadron.available_pilots))
        pilots = QLabel(f"{ready} pilots ready")
        pilots.setStyleSheet(
            f"font-size: 11px; color: {'#86C39A' if ready else '#5F8A6C'};"
            " background: transparent; border: none;"
        )

        self.aircraft_count_spinner = QSpinBox()
        self.aircraft_count_spinner.setMinimum(1)
        self.aircraft_count_spinner.setMaximum(max_count)
        self.aircraft_count_spinner.setValue(self.flight.count)
        self.aircraft_count_spinner.setPrefix("× ")
        self.aircraft_count_spinner.setToolTip("How many aircraft fly this mission.")
        self.aircraft_count_spinner.valueChanged.connect(self._changed_aircraft_count)
        styled_input(self.aircraft_count_spinner, width=88)

        squadron_btn = QPushButton("Change…")
        squadron_btn.setFixedHeight(24)
        squadron_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        squadron_btn.setStyleSheet(
            "QPushButton { background: #26343F; color: #B7C6D2;"
            " border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 10px;"
            " font-size: 12px; }"
            "QPushButton:hover { background: #33475C; }"
        )
        squadron_btn.clicked.connect(self._change_squadron)

        row = QHBoxLayout()
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)
        row.addWidget(name)
        row.addWidget(base)
        row.addWidget(pilots)
        row.addStretch()
        row.addWidget(self.aircraft_count_spinner)
        row.addWidget(squadron_btn)

        strip = QWidget()
        strip.setFixedHeight(40)
        strip.setStyleSheet("background: #1B2732; border: none;")
        strip.setLayout(row)
        return strip

    def _change_squadron(self):
        dialog = QSquadronSelector(self.flight)
        if dialog.exec():
            squadron: Optional[Squadron] = dialog.selector.currentData()
            if not squadron:
                return
            flight = Flight(
                self.package_model.package,
                squadron,
                self.flight.count,
                self.flight.flight_type,
                self.flight.start_type,
                self._find_divert_field(squadron.aircraft, squadron.location),
                frequency=self.flight.frequency,
                cargo=self.flight.cargo,
                channel=self.flight.tacan,
                callsign_tcn=self.flight.tcn_name,
            )
            self.package_model.add_flight(flight)
            self.package_model.delete_flight(self.flight)
            self.squadron_changed.emit(flight)

    def _find_divert_field(
        self, aircraft: AircraftType, arrival: ControlPoint
    ) -> Optional[ControlPoint]:
        divert_limit = nautical_miles(150)
        for airfield in self.closest_airfields.operational_airfields_within(
            divert_limit
        ):
            if airfield.captured != self.flight.coalition.player:
                continue
            if airfield == arrival:
                continue
            if not airfield.can_operate(aircraft):
                continue
            if isinstance(airfield, OffMapSpawn):
                continue
            return airfield
        return None

    def _changed_aircraft_count(self):
        old_count = self.flight.count
        new_count = int(self.aircraft_count_spinner.value())
        try:
            self.flight.resize(new_count)
        except ValueError:
            # The UI should have prevented this, but if we ran out of aircraft
            # then roll back the inventory change.
            difference = new_count - self.flight.count
            available = self.flight.squadron.untasked_aircraft
            logging.error(
                f"Could not add {difference} additional aircraft to "
                f"{self.flight} because {self.flight.departure} has only "
                f"{available} {self.flight.unit_type} remaining"
            )
            self.flight.resize(old_count)
            return
        self.roster_editor.resize(new_count)
        self.flight_resized.emit(new_count)
