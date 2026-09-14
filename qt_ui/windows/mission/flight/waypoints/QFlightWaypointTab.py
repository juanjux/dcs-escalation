import logging
from typing import Iterable, List, Optional

from PySide6.QtCore import Signal, Qt, QModelIndex
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from game import Game
from qt_ui.widgets.cards import carded, make_transparent
from qt_ui.widgets.controls import mono, styled_input, wrapped_tooltip
from game.ato.flight import Flight
from game.ato.flightplans.custom import CustomFlightPlan
from game.ato.flightplans.formationattack import FormationAttackFlightPlan
from game.ato.flightplans.planningerror import PlanningError
from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.ato.flighttype import FlightType
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.fuelestimate import estimate_fuel
from game.utils import feet
from game.ato.loadouts import Loadout
from game.ato.package import Package
from game.theater import Player
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
    QFlightWaypointList,
)
from qt_ui.windows.mission.flight.waypoints.QPredefinedWaypointSelectionWindow import (
    QPredefinedWaypointSelectionWindow,
)


def _footer_caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        "font-size: 11px; font-weight: bold; letter-spacing: 1px; color: #6B7A87;"
        " background: transparent; border: none;"
    )
    return label


class FuelBar(QWidget):
    """What the plan asks for against what the flight carries, as a bar.

    "Fuel: ~10,057 of 13,033" is two numbers you have to divide in your head to know
    whether it is close. The bar is the division: the fill is what the route needs, the
    tick is what the aircraft has, and the fill turns red when it goes past the tick.
    """

    WIDTH = 220
    HEIGHT = 6

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(self.WIDTH, self.HEIGHT + 6)
        self.required = 0.0
        self.carried = 0.0
        make_transparent(self)

    def show_fuel(self, required: float, carried: float) -> None:
        self.required, self.carried = required, carried
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            top = (self.height() - self.HEIGHT) // 2
            track = QRect(0, top, self.WIDTH, self.HEIGHT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1D2731"))
            painter.drawRoundedRect(track, 3, 3)

            if self.carried <= 0:
                return
            # The scale runs to whichever is larger, so an overrun has somewhere to be
            # drawn rather than being clipped at full.
            top_of_scale = max(self.carried, self.required)
            enough = self.required <= self.carried
            fill_width = int(self.WIDTH * self.required / top_of_scale)
            painter.setBrush(QColor("#86C39A" if enough else "#D9645E"))
            painter.drawRoundedRect(
                QRect(0, top, max(2, fill_width), self.HEIGHT), 3, 3
            )

            tick_x = int(self.WIDTH * self.carried / top_of_scale)
            painter.setBrush(QColor("#F2F7FA"))
            painter.drawRect(
                QRect(min(tick_x, self.WIDTH - 2), top - 2, 2, self.HEIGHT + 4)
            )
        finally:
            painter.end()


class QFlightWaypointTab(QFrame):
    loadout_changed = Signal()

    # Waypoint types whose altitude the bulk setter must not touch. Their altitude is
    # tied to something other than the en-route cruise band, so overwriting it with a
    # cruise MSL would break the flight plan:
    #   * Takeoff / pattern / landing points are tied to the airfield.
    #   * Divert and cargo-stop points are alternate landing fields.
    #   * Target points carry the target's own elevation (used for attack geometry).
    #   * Pickup / dropoff zones are ground-level helo landing zones.
    #   * Refuel / recovery-tanker points are tied to the tanker's orbit altitude.
    #   * Bullseye is a fixed map reference, not a flown waypoint.
    #: Over the fuel carried by no more than this reads as tight rather than short.
    TIGHT_OVERRUN = 1.15

    BULK_ALTITUDE_SKIP_TYPES = frozenset(
        {
            FlightWaypointType.TAKEOFF,
            FlightWaypointType.DESCENT_POINT,
            FlightWaypointType.LANDING_POINT,
            FlightWaypointType.DIVERT,
            FlightWaypointType.CARGO_STOP,
            FlightWaypointType.TARGET_POINT,
            FlightWaypointType.TARGET_GROUP_LOC,
            FlightWaypointType.TARGET_SHIP,
            FlightWaypointType.PICKUP_ZONE,
            FlightWaypointType.DROPOFF_ZONE,
            FlightWaypointType.REFUEL,
            FlightWaypointType.RECOVERY_TANKER,
            FlightWaypointType.BULLSEYE,
        }
    )

    def __init__(self, game: Game, package: Package, flight: Flight):
        super(QFlightWaypointTab, self).__init__()
        self.game = game
        self.coalition = game.coalition_for(player=Player.BLUE)
        self.package = package
        self.flight = flight

        self.flight_waypoint_list: Optional[QFlightWaypointList] = None
        self.rtb_waypoint: Optional[QPushButton] = None
        self.delete_selected: Optional[QPushButton] = None
        self.add_nav_waypoint: Optional[QPushButton] = None
        self.open_fast_waypoint_button: Optional[QPushButton] = None
        self.recreate_buttons: List[QPushButton] = []
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()

        #: The last route length the list reported, so the footer can be redrawn when
        #: only the fuel side of it has moved.
        self._route_length_nm = 0.0

        self.flight_waypoint_list = QFlightWaypointList(self.package, self.flight)
        layout.addWidget(self.flight_waypoint_list, 0, 0)

        # Under the table, not a last row: on_changed indexes the rows against
        # flight_plan.waypoints.
        self.route_length = QLabel()
        self.route_length.setFont(mono(14))
        self.route_length.setStyleSheet(
            "color: #D3DFE8; background: transparent; border: none;"
        )
        self.fuel_bar = FuelBar()
        self.fuel_numbers = QLabel()
        self.fuel_numbers.setFont(mono(13))
        self.fuel_numbers.setStyleSheet(
            "color: #D3DFE8; background: transparent; border: none;"
        )
        self.fuel_note = QLabel()
        self.fuel_note.setStyleSheet(
            "font-size: 11px; color: #D9645E; background: transparent; border: none;"
        )

        footer = QHBoxLayout()
        footer.setContentsMargins(14, 0, 14, 0)
        footer.setSpacing(10)
        footer.addWidget(_footer_caption("ROUTE"))
        footer.addWidget(self.route_length)
        footer.addSpacing(18)
        footer.addWidget(_footer_caption("FUEL"))
        footer.addWidget(self.fuel_bar)
        footer.addWidget(self.fuel_numbers)
        footer.addWidget(self.fuel_note)
        footer.addStretch()
        footer_holder = QWidget()
        footer_holder.setFixedHeight(48)
        footer_holder.setStyleSheet(
            "background: #1B2732; border: 1px solid #1D2731; border-radius: 3px;"
        )
        footer_holder.setLayout(footer)

        self.flight_waypoint_list.route_length_changed.connect(self.show_route_length)
        # It built itself in its constructor, before this was connected.
        self.flight_waypoint_list.update_list()
        layout.addWidget(footer_holder, 1, 0)

        rlayout = QVBoxLayout()
        rlayout.setSpacing(18)
        layout.addLayout(rlayout, 0, 1)

        # --- altitude -------------------------------------------------------
        self.bulk_altitude = QSpinBox()
        self.bulk_altitude.setMinimum(0)
        self.bulk_altitude.setMaximum(40000)
        self.bulk_altitude.setSingleStep(1000)
        self.bulk_altitude.setValue(self._default_bulk_altitude())
        self.bulk_altitude.setSuffix(" ft")
        self.bulk_altitude.setToolTip(
            wrapped_tooltip(
                "Apply this MSL altitude to every en-route waypoint. Takeoff, landing, "
                "divert, target, landing-zone, tanker, and ground (AGL) waypoints are "
                "left unchanged."
            )
        )
        self.apply_bulk_altitude = QPushButton("Apply to all")
        self.apply_bulk_altitude.setFixedHeight(28)
        self.apply_bulk_altitude.clicked.connect(self.on_apply_bulk_altitude)
        bulk_alt_layout = QHBoxLayout()
        bulk_alt_layout.setContentsMargins(0, 0, 0, 0)
        bulk_alt_layout.setSpacing(8)
        bulk_alt_layout.addWidget(styled_input(self.bulk_altitude), 1)
        bulk_alt_layout.addWidget(self.apply_bulk_altitude)
        altitude_box = QWidget()
        make_transparent(altitude_box)
        altitude_box.setLayout(bulk_alt_layout)
        rlayout.addLayout(
            carded("En-route altitude", altitude_box, "leaves the fixed points alone")
        )

        # --- regenerate -----------------------------------------------------
        # Nine stacked "Recreate as X" buttons, one per task the target accepts, was a
        # wall of near-identical controls for something you do once. One combo says
        # what the list holds without spending nine rows on it.
        self.recreate_buttons.clear()
        self.recreate_selector = QComboBox()
        for task in self.package.target.mission_types(for_player=Player.BLUE):
            if task == FlightType.AIR_ASSAULT and not self.game.settings.plugin_option(
                "ctld"
            ):
                # Only add Air Assault if ctld plugin is enabled
                continue
            self.recreate_selector.addItem(f"as {task}", task)
        current = self.recreate_selector.findData(self.flight.flight_type)
        if current >= 0:
            self.recreate_selector.setCurrentIndex(current)

        self.recreate_button = QPushButton("Recreate")
        self.recreate_button.setFixedHeight(28)
        self.recreate_button.setToolTip(
            "Throw this flight's route away and build the standard one for the "
            "selected task."
        )
        self.recreate_button.clicked.connect(self.on_recreate_selected)

        recreate_row = QHBoxLayout()
        recreate_row.setContentsMargins(0, 0, 0, 0)
        recreate_row.setSpacing(8)
        recreate_row.addWidget(styled_input(self.recreate_selector), 1)
        recreate_row.addWidget(self.recreate_button)

        self.add_nav_waypoint = QPushButton("Insert NAV point after selected")
        self.add_nav_waypoint.setFixedHeight(28)
        self.add_nav_waypoint.clicked.connect(self.on_add_nav)

        generator_layout = QVBoxLayout()
        generator_layout.setContentsMargins(0, 0, 0, 0)
        generator_layout.setSpacing(8)
        generator_layout.addLayout(recreate_row)
        generator_layout.addWidget(self.add_nav_waypoint)
        generator_box = QWidget()
        make_transparent(generator_box)
        generator_box.setLayout(generator_layout)
        rlayout.addLayout(carded("Regenerate", generator_box, "AI compatible"))

        # --- by hand --------------------------------------------------------
        self.open_fast_waypoint_button = QPushButton("Add waypoint...")
        self.open_fast_waypoint_button.setFixedHeight(28)
        self.open_fast_waypoint_button.clicked.connect(self.on_fast_waypoint)

        self.rtb_waypoint = QPushButton("Add RTB")
        self.rtb_waypoint.setFixedHeight(28)
        self.rtb_waypoint.clicked.connect(self.on_rtb_waypoint)

        self.delete_selected = QPushButton("Delete selected")
        self.delete_selected.setFixedHeight(28)
        # The only destructive control on the tab, and the only red one.
        self.delete_selected.setStyleSheet(
            "QPushButton { background: #3B2523; color: #E8B7B3;"
            " border: 1px solid #A8443F; border-radius: 3px; font-size: 12px; }"
            "QPushButton:hover { background: #4A2B29; }"
            "QPushButton:disabled { background: #241D1D; color: #6B5352;"
            " border-color: #4A3230; }"
        )
        self.delete_selected.clicked.connect(self.on_delete_waypoint)

        manual_top = QHBoxLayout()
        manual_top.setContentsMargins(0, 0, 0, 0)
        manual_top.setSpacing(8)
        manual_top.addWidget(self.open_fast_waypoint_button, 1)
        manual_top.addWidget(self.rtb_waypoint)

        manual_layout = QVBoxLayout()
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(8)
        manual_layout.addLayout(manual_top)
        manual_box = QWidget()
        make_transparent(manual_box)
        manual_box.setLayout(manual_layout)

        # A hand-added waypoint is what a player can fly and the AI cannot: we have
        # already seen an edited route take DCS down with it. So ADDING is greyed out
        # for any flight with an AI seat in it, and says why.
        #
        # Deleting is not, because whether it is safe is a property of the waypoint
        # rather than of the crew: taking back a nav point you added yourself, or a
        # refuelling stop, or the join of a flight that is the whole package, leaves a
        # plan the AI can still fly. So the button sits OUTSIDE the greyed box -- a
        # disabled parent disables its children whatever they say -- and turns itself
        # on for a selection it can actually reach.
        ai_seats = sum(
            1 for member in self.flight.iter_members() if not member.is_player
        )
        if ai_seats:
            crew = "seat" if ai_seats == 1 else "seats"
            hint = f"adding disabled: {ai_seats} AI {crew} in this flight"
        else:
            hint = "all seats are players"
        self.manual_box = manual_box
        manual_box.setEnabled(not ai_seats)

        editing = QVBoxLayout()
        editing.setContentsMargins(0, 0, 0, 0)
        editing.setSpacing(8)
        editing.addWidget(manual_box)
        editing.addWidget(self.delete_selected)
        editing_box = QWidget()
        make_transparent(editing_box)
        editing_box.setLayout(editing)
        rlayout.addLayout(carded("Manual editing", editing_box, hint, loud_hint=True))

        self.flight_waypoint_list.selectionModel().selectionChanged.connect(
            self.refresh_delete_button
        )
        self.flight_waypoint_list.delete_requested.connect(self.on_delete_requested)
        self.refresh_delete_button()

        rlayout.addStretch()
        self.setLayout(layout)

    def on_recreate_selected(self) -> None:
        task = self.recreate_selector.currentData()
        if task is not None:
            self.confirm_recreate(task)

    def on_add_nav(self):
        selected = self.flight_waypoint_list.selectedIndexes()
        if not selected:
            return
        index: QModelIndex = selected[0]
        self.flight_waypoint_list.setCurrentIndex(index)
        wpt: FlightWaypoint = self.flight_waypoint_list.model.data(
            index, Qt.ItemDataRole.UserRole
        )
        next_wpt: Optional[FlightWaypoint] = None
        if index.row() + 1 < self.flight_waypoint_list.model.rowCount():
            next_wpt = self.flight_waypoint_list.model.data(
                index.siblingAtRow(index.row() + 1), Qt.ItemDataRole.UserRole
            )
        if not self.flight.flight_plan.layout.add_waypoint(wpt, next_wpt):
            QMessageBox.critical(
                QWidget(),
                "Failed to add NAV waypoint",
                "Could not insert a new waypoint given the currently selected waypoint.\n"
                "Please select a different waypoint to insert the new NAV waypoint.",
            )
        else:
            self.flight_waypoint_list.model.insertRow(
                self.flight_waypoint_list.model.rowCount()
            )
            self.on_change()

    def selected_waypoints(self) -> list[FlightWaypoint]:
        """The waypoints under the selection, in list order, without the departure."""
        waypoints: list[FlightWaypoint] = []
        selection = self.flight_waypoint_list.selectionModel()
        for selected_row in selection.selectedIndexes():
            if selected_row.row() <= 0:
                continue
            # Never by row index: a folded target group is one row standing for
            # several, so the row and the waypoint list stopped lining up.
            waypoint = self.flight_waypoint_list.waypoint_at_row(selected_row.row())
            if waypoint is not None and waypoint not in waypoints:
                waypoints.append(waypoint)
        return waypoints

    def refresh_delete_button(self, *_args: object) -> None:
        """On for a selection this flight can actually give up.

        Every selected waypoint has to be one, not just one of them: half a deletion is
        worse than none, and a player who selected four things and got one deleted has
        to work out which.
        """
        if self.delete_selected is None:
            return
        waypoints = self.selected_waypoints()
        deletable = bool(waypoints) and all(
            self.waypoint_is_deletable(waypoint) for waypoint in waypoints
        )
        self.delete_selected.setEnabled(deletable or self.manual_box.isEnabled())

    def waypoint_is_deletable(self, waypoint: FlightWaypoint) -> bool:
        """Whether this one can go without rebuilding the plan around it."""
        return self.flight.flight_plan.can_delete_waypoint(waypoint)

    def on_delete_requested(self) -> None:
        """Delete pressed over the list. Under the button's rule, so the key can never
        do what the button refuses to."""
        if self.delete_selected is not None and self.delete_selected.isEnabled():
            self.on_delete_waypoint()

    def on_delete_waypoint(self):
        for waypoint in self.selected_waypoints():
            self.delete_waypoint(waypoint)
        self.on_change()
        self.refresh_delete_button()

    def delete_waypoint(self, waypoint: FlightWaypoint) -> None:
        # Need to degrade to a custom flight plan and remove the waypoint.
        # If the waypoint is a target waypoint and is not the last target
        # waypoint, we don't need to degrade.
        fp = self.flight.flight_plan
        model = self.flight_waypoint_list.model
        if fp.delete_waypoint(waypoint):
            model.removeRow(model.rowCount() - 1)
            return

        if not self.flight.flight_plan.is_custom:
            confirmed = self.confirm_degrade()
            if not confirmed:
                return
        model.removeRow(model.rowCount() - 1)
        self.degrade_to_custom_flight_plan()
        assert isinstance(self.flight.flight_plan, CustomFlightPlan)
        self.flight.flight_plan.layout.custom_waypoints.remove(waypoint)

    def confirm_degrade(self, parent: Optional[QWidget] = None) -> bool:
        result = QMessageBox.warning(
            parent if parent else self,
            "Degrade flight-plan?",
            "Deleting the selected waypoint(s) will require degradation to a custom flight-plan. "
            "A custom flight-plan will no longer respect the TOTs of the package.<br><br>"
            "<b>Are you sure you wish to continue?</b>",
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def on_fast_waypoint(self):
        self.subwindow = QPredefinedWaypointSelectionWindow(
            self.game, self.flight, self.flight_waypoint_list
        )
        self.subwindow.waypoints_added.connect(self.on_waypoints_added)
        self.subwindow.show()

    def on_waypoints_added(self, waypoints: Iterable[FlightWaypoint]) -> None:
        if not waypoints:
            return
        self.flight.flight_plan.layout.custom_waypoints.extend(waypoints)
        self.add_rows(len(list(waypoints)))

    def add_rows(self, count: int) -> None:
        rc = self.flight_waypoint_list.model.rowCount()
        self.flight_waypoint_list.model.insertRows(rc, count)
        self.on_change()

    def on_rtb_waypoint(self):
        rtb = WaypointBuilder(self.flight).land(self.flight.arrival)
        self.degrade_to_custom_flight_plan()
        assert isinstance(self.flight.flight_plan, CustomFlightPlan)
        self.flight.flight_plan.layout.custom_waypoints.append(rtb)
        self.add_rows(1)

    def degrade_to_custom_flight_plan(self) -> None:
        if not isinstance(self.flight.flight_plan, CustomFlightPlan):
            self.flight.degrade_to_custom_flight_plan()

    def confirm_recreate(self, task: FlightType) -> None:
        result = QMessageBox.question(
            self,
            "Regenerate flight?",
            (
                "Changing the flight type will reset its flight plan. Do you want "
                "to continue?"
            ),
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        original_task = self.flight.flight_type
        if result == QMessageBox.StandardButton.Yes:
            self.flight.set_flight_type(task)
            try:
                self.flight.recreate_flight_plan(dump_debug_info=True)
            except PlanningError as ex:
                self.flight.set_flight_type(original_task)
                logging.exception("Could not recreate flight")
                QMessageBox.critical(
                    self,
                    "Could not recreate flight",
                    str(ex),
                    QMessageBox.StandardButton.Ok,
                )
            for member in self.flight.iter_members():
                if not member.loadout.is_custom:
                    member.loadout = Loadout.default_for(self.flight)
                    self.loadout_changed.emit()
            self.flight_waypoint_list.update_list()
            self.on_change()

    def _is_bulk_editable(self, waypoint: FlightWaypoint) -> bool:
        # By type only. Skipping every AGL point as well froze whole flight plans:
        # a helicopter cruises AGL, so an Apache had nothing left to set, and a
        # low-level A-10 most of a route. The points that must not move -- takeoff,
        # landing, pattern, zones, targets -- are in the list above whatever they are
        # referenced to. A waypoint keeps its own reference; only the number changes.
        return waypoint.waypoint_type not in self.BULK_ALTITUDE_SKIP_TYPES

    def _default_bulk_altitude(self) -> int:
        # Seed the spinner with the highest en-route altitude already planned so the
        # control opens on a sensible value rather than zero.
        altitudes = [
            round(wpt.alt.feet)
            for wpt in self.flight.flight_plan.waypoints
            if self._is_bulk_editable(wpt)
        ]
        return max(altitudes, default=0)

    def on_apply_bulk_altitude(self) -> None:
        altitude = feet(self.bulk_altitude.value())
        changed = False
        for waypoint in self.flight.flight_plan.waypoints:
            if self._is_bulk_editable(waypoint):
                waypoint.alt = altitude
                changed = True
        if changed:
            self.on_change()

    def refresh_fuel(self) -> None:
        """Recompute the footer without the route having changed.

        Carried fuel is half of the estimate and it is set on another tab, so
        removing a drop tank used to leave this line showing the old total until
        something moved a waypoint.
        """
        self.show_route_length(self._route_length_nm)

    def show_route_length(self, nautical_miles: float) -> None:
        self._route_length_nm = nautical_miles
        self.route_length.setText(f"{nautical_miles:.0f} nm")

        fuel = estimate_fuel(self.flight)
        if fuel is None:
            self.fuel_bar.hide()
            self.fuel_numbers.setText("")
            self.fuel_note.setText("")
            return

        self.fuel_bar.show()
        self.fuel_bar.show_fuel(fuel.required.pounds, fuel.carried.pounds)
        self.fuel_numbers.setText(
            f"~{fuel.required.pounds:,.0f} of {fuel.carried.pounds:,.0f} lb"
        )
        if fuel.enough:
            self.fuel_note.setText("")
            return
        # Loud on purpose: the estimate errs high, so it saying no is still worth a
        # look before you launch. Being over by a tenth and being over by half are not
        # the same news, so they do not read alike.
        short = fuel.required.pounds - fuel.carried.pounds
        if fuel.required.pounds <= fuel.carried.pounds * self.TIGHT_OVERRUN:
            self.fuel_note.setText("tight")
            self.fuel_note.setStyleSheet(
                "font-size: 11px; color: #E0A86B; background: transparent;"
                " border: none;"
            )
        else:
            self.fuel_note.setText(f"short by {short:,.0f} lb")
            self.fuel_note.setStyleSheet(
                "font-size: 11px; color: #D9645E; background: transparent;"
                " border: none;"
            )

    def on_change(self):
        self.flight_waypoint_list.update_list()
        self.flight_waypoint_list.on_changed()
        self.update()
