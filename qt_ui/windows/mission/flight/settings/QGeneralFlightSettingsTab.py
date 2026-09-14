"""The General tab: who flies it, how it starts, when it goes and on what frequency.

Two columns of captioned cards instead of six stacked group boxes. The task and type
box is gone -- the mission header above the tabs answers that, and answered it twice
before. What is left is grouped by the question it answers: the crew and how they
start on the left, the timing and the radios on the right.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from game.ato.flight import Flight
from game.ato.flightmember import apply_default_player_laser_code
from qt_ui.models import PackageModel, GameModel
from qt_ui.widgets.cards import carded
from qt_ui.windows.mission.flight.payload.QFlightPayloadTab import QFlightPayloadTab
from qt_ui.windows.mission.flight.settings.FlightPlanPropertiesGroup import (
    FlightPlanPropertiesGroup,
)
from qt_ui.windows.mission.flight.settings.QCommsEditor import QCommsEditor
from qt_ui.windows.mission.flight.settings.QCustomName import QFlightCustomName
from qt_ui.windows.mission.flight.settings.QFlightSlotEditor import QFlightSlotEditor
from qt_ui.windows.mission.flight.settings.QFlightStartType import QFlightStartType
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
    QFlightWaypointList,
)

#: The left column carries the roster, which is the widest thing on the tab.
LEFT_WIDTH = 640
RIGHT_WIDTH = 456
GAP = 24
MARGIN = 20


class QGeneralFlightSettingsTab(QFrame):
    flight_size_changed = Signal()
    squadron_changed = Signal(Flight)
    #: Something on this tab changed what the header shows -- a seat filled, the
    #: start type moved.
    header_changed = Signal()

    def __init__(
        self,
        game: GameModel,
        package_model: PackageModel,
        flight: Flight,
        flight_wpt_list: QFlightWaypointList,
        payload_tab: QFlightPayloadTab,
    ):
        super().__init__()
        self.flight = flight
        self.payload_tab = payload_tab

        self.flight_slot_editor = QFlightSlotEditor(package_model, flight, game.game)
        self.flight_slot_editor.flight_resized.connect(self.flight_size_changed)
        self.flight_slot_editor.flight_resized.connect(self.header_changed)
        self.flight_slot_editor.squadron_changed.connect(self.squadron_changed)
        for pc in self.flight_slot_editor.roster_editor.pilot_controls:
            pc.player_toggled.connect(self.on_player_toggle)
            pc.player_toggled.connect(
                self.flight_slot_editor.roster_editor.pilots_changed
            )

        self.start_type = QFlightStartType(package_model, flight)
        self.start_type.start_type_changed.connect(self.header_changed)

        roster = self.flight_slot_editor.roster_editor
        roster.pilots_changed.connect(self.start_type.on_pilot_selected)
        roster.pilots_changed.connect(self.header_changed)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)
        left.addLayout(carded("Crew", self.flight_slot_editor))
        left.addLayout(
            carded(
                "Start type",
                self.start_type,
                "how the flight is sitting when the mission loads",
            )
        )
        left.addLayout(carded("Custom name", QFlightCustomName(flight)))
        left.addStretch()

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(18)
        right.addLayout(
            carded(
                "Timing & route",
                FlightPlanPropertiesGroup(
                    game.game, package_model, flight, flight_wpt_list
                ),
                "TOT comes from the package",
                margins=(0, 4, 0, 4),
            )
        )
        right.addLayout(
            carded(
                "Comms",
                QCommsEditor(flight, game),
                "AUTO lets the generator pick; set a value to override",
            )
        )
        right.addStretch()

        left_holder = QWidget()
        left_holder.setLayout(left)
        left_holder.setMinimumWidth(LEFT_WIDTH)
        right_holder = QWidget()
        right_holder.setLayout(right)
        right_holder.setFixedWidth(RIGHT_WIDTH)

        columns = QHBoxLayout()
        columns.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        columns.setSpacing(GAP)
        columns.addWidget(left_holder, 1)
        columns.addWidget(right_holder)
        self.setLayout(columns)

    def on_player_toggle(self) -> None:
        # When a flight member's player flag changes, reconcile their laser code
        # with the campaign default. AI -> player members get the configured
        # default applied (mirroring how new player flights are seeded). Player
        # -> AI members release any owned code back to the registry.
        coalition_game = self.flight.coalition.game
        for member in self.flight.iter_members():
            if not member.is_player and member.tgp_laser_code is not None:
                member.release_tgp_laser_code()
            elif member.is_player and member.tgp_laser_code is None:
                apply_default_player_laser_code(
                    member,
                    coalition_game.settings,
                    coalition_game.laser_code_registry,
                )
        self.payload_tab.property_editor.build_props(self.flight)
        self.payload_tab.own_laser_code_info.bind_to_selected_member()
        self.payload_tab.weapon_laser_code_selector.rebuild()
