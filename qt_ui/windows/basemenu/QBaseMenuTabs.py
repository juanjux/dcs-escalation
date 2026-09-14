"""The tabs of the base menu: named for what is in them, and the same set every time.

Membership used to depend on four conditions, so the window changed shape between
bases with nothing saying why -- an "Airfield Command" here, a "Heliport" there, no
ground tab on a carrier. The set is now fixed per owner and a tab that does not apply
is disabled with the reason on it, so the shape holds and the player is told.

Each tab carries its count, so you know whether it is worth opening.
"""

from typing import Optional

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from game.theater import ControlPoint, ParkingType
from qt_ui.models import GameModel
from qt_ui.widgets.cards import make_transparent
from qt_ui.windows.basemenu.DepartingConvoysMenu import DepartingConvoysMenu
from qt_ui.windows.basemenu.airfield.QAirfieldCommand import QAirfieldCommand
from qt_ui.windows.basemenu.ground_forces.QGroundForcesHQ import QGroundForcesHQ
from qt_ui.windows.basemenu.intel.QIntelInfo import QIntelInfo
from qt_ui.windows.mission.QPlannedFlightsView import QPlannedFlightsView


def _blank() -> QWidget:
    """The body of a tab that does not apply. The tooltip says why."""
    widget = QWidget()
    make_transparent(widget)
    return widget


class QBaseMenuTabs(QTabWidget):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super(QBaseMenuTabs, self).__init__()
        self.cp = cp
        self.game_model = game_model
        game = game_model.game

        if cp.captured.is_red:
            self.intel = QIntelInfo(cp, game_model)
            self.addTab(self.intel, "Intel")

            self.departing_convoys = DepartingConvoysMenu(cp, game_model)
            self._add(self.departing_convoys, "Convoys", count=self._convoy_count())
            if game is not None and game.settings.enable_enemy_buy_sell:
                self.ground_forces_hq = QGroundForcesHQ(cp, game_model)
                self._add(
                    self.ground_forces_hq,
                    "Ground forces",
                    count=self._ground_count(),
                )
            return

        parking = cp.total_aircraft_parking(
            ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
        )
        if parking:
            self.airfield_command = QAirfieldCommand(cp, game_model)
            self._add(self.airfield_command, "Aircraft", count=self._aircraft_count())
        else:
            self._add(
                _blank(),
                "Aircraft",
                disabled_because="Nothing can be based here: this base has no parking.",
            )

        if cp.can_deploy_ground_units and not cp.captured.is_neutral:
            self.ground_forces_hq = QGroundForcesHQ(cp, game_model)
            self._add(
                self.ground_forces_hq, "Ground forces", count=self._ground_count()
            )
        else:
            self._add(
                _blank(),
                "Ground forces",
                disabled_because="Ground units cannot be based here.",
            )

        self._add(self._flights(), "Flights", count=self._flight_count())

    # -- the tabs ------------------------------------------------------------

    def _flights(self) -> QWidget:
        """What is fragged from here this turn.

        Its own tab rather than a box inside the buying one: it answers a different
        question, and it was competing with the aircraft list for the same width.
        """
        holder = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QPlannedFlightsView(self.game_model, self.cp))
        holder.setLayout(layout)
        return holder

    def _add(
        self,
        widget: QWidget,
        name: str,
        count: Optional[int] = None,
        disabled_because: str = "",
    ) -> None:
        label = name if count is None else f"{name}  {count}"
        index = self.addTab(widget, label)
        if disabled_because:
            self.setTabEnabled(index, False)
            self.setTabToolTip(index, disabled_because)

    # -- the counts ----------------------------------------------------------

    def _aircraft_count(self) -> int:
        every = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)
        return self.cp.allocated_aircraft(every).total_present

    def _ground_count(self) -> int:
        game = self.game_model.game
        if game is None:
            return 0
        transfers = game.coalition_for(self.cp.captured).transfers
        return self.cp.allocated_ground_units(transfers).total_present

    def _flight_count(self) -> int:
        game = self.game_model.game
        if game is None:
            return 0
        count = 0
        for coalition in game.coalitions:
            for package in coalition.ato.packages:
                for flight in package.flights:
                    if flight.departure == self.cp:
                        count += 1
        return count

    def _convoy_count(self) -> int:
        game = self.game_model.game
        if game is None:
            return 0
        count = 0
        for coalition in game.coalitions:
            for transfer in coalition.transfers:
                if transfer.origin == self.cp:
                    count += 1
        return count
