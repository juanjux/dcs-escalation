from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget

from game.ato.flight import Flight
from qt_ui.models import PackageModel, GameModel
from qt_ui.windows.mission.flight.payload.QFlightPayloadTab import QFlightPayloadTab
from qt_ui.windows.mission.flight.settings.QGeneralFlightSettingsTab import (
    QGeneralFlightSettingsTab,
)
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab import QFlightWaypointTab


class QFlightPlanner(QTabWidget):
    squadron_changed = Signal(Flight)
    #: Something changed that the mission header above these tabs reports on: a seat,
    #: the fuel, the start type, the size of the flight. Gathered here so the header
    #: has one thing to listen to rather than reaching into three tabs.
    header_changed = Signal()

    def __init__(self, package_model: PackageModel, flight: Flight, gm: GameModel):
        super().__init__()

        self.payload_tab = QFlightPayloadTab(flight, gm.game)

        self.waypoint_tab = QFlightWaypointTab(gm.game, package_model.package, flight)
        self.waypoint_tab.loadout_changed.connect(self.payload_tab.reload_from_flight)

        self.general_settings_tab = QGeneralFlightSettingsTab(
            gm,
            package_model,
            flight,
            self.waypoint_tab.flight_waypoint_list,
            self.payload_tab,
        )
        self.general_settings_tab.flight_size_changed.connect(
            self.payload_tab.resize_for_flight
        )
        self.general_settings_tab.squadron_changed.connect(self.squadron_changed)

        # The waypoint tab's footer weighs the route against what the aircraft carries,
        # and what it carries is set over on the payload tab. Without this the fuel line
        # kept showing the tanks after they were taken off.
        self.payload_tab.carried_fuel_changed.connect(self.waypoint_tab.refresh_fuel)
        # And a backstop for any path that changes carried fuel without saying so:
        # arriving at the tab is a fine moment to recompute.
        self.currentChanged.connect(self.on_tab_changed)

        self.payload_tab.carried_fuel_changed.connect(self.header_changed)
        self.general_settings_tab.header_changed.connect(self.header_changed)
        self.waypoint_tab.flight_waypoint_list.route_length_changed.connect(
            self.header_changed
        )

        self.addTab(self.general_settings_tab, "General")
        self.addTab(self.payload_tab, "Payload")
        self.waypoints_index = self.addTab(self.waypoint_tab, "Waypoints")
        self.setCurrentIndex(0)

        # Restyled here rather than in style.css: this is the only tab bar in the
        # application that follows the redesign's vocabulary, and putting it in the
        # global sheet would drag every other one along with it.
        # An unselected tab needs to look like a tab you can press: as bare text on
        # the same ground as the dialog it read as a label, and only the selected one
        # looked like anything at all.
        self.setStyleSheet(
            "QTabBar::tab { background: #1B2732; color: #8E9DAA; padding: 7px 18px;"
            " font-size: 12.5px; border: 1px solid #1D2731; border-bottom: none;"
            " border-top-left-radius: 3px; border-top-right-radius: 3px;"
            " margin-right: 2px; }"
            "QTabBar::tab:hover { background: #24333F; color: #B7C6D2; }"
            "QTabBar::tab:selected { background: #2D3E50; color: #F2F7FA;"
            " font-weight: 600; border-color: #3A4B5C; }"
            "QTabWidget::pane { border: none; border-top: 1px solid #1D2731; }"
        )
        self.waypoint_tab.flight_waypoint_list.route_length_changed.connect(
            self.show_waypoint_count
        )
        self.show_waypoint_count()

    def show_waypoint_count(self, _route_nm: float = 0.0) -> None:
        """How many waypoints there are, on the tab that holds them.

        A route that grew a leg you did not ask for is worth noticing from another
        tab, and the count is the cheapest way to notice it.
        """
        try:
            count = len(self.waypoint_tab.flight.flight_plan.waypoints)
        except Exception:
            return
        self.setTabText(self.waypoints_index, f"Waypoints  {count}")

    def on_tab_changed(self, index: int) -> None:
        if self.widget(index) is self.waypoint_tab:
            self.waypoint_tab.refresh_fuel()
