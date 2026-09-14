from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.ato.flight import Flight
from game.ato.starttype import StartType
from game.theater import OffMapSpawn
from qt_ui.models import PackageModel
from qt_ui.widgets.controls import Segmented

AMBER = "#E0A86B"


class QFlightStartType(QWidget):
    """How the flight is on the ground when the mission loads.

    Four mutually exclusive choices, so they are four buttons rather than a combo box:
    the set is short, it never changes, and which one is picked is something you want
    to see without clicking. The balance note appears only when it applies -- as a
    permanent sentence it was furniture, and furniture is not read.
    """

    #: Anything other than Cold makes the flight untargetable by OCA, which the header
    #: shows as a pill. Emitted however the start type moved -- picked by hand, or
    #: reset because a player took a seat.
    start_type_changed = Signal()

    def __init__(self, package_model: PackageModel, flight: Flight):
        super().__init__()
        self.package_model = package_model
        self.flight = flight

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.segmented = Segmented(
            [(start_type.value, start_type) for start_type in StartType],
            current=flight.start_type,
        )
        self.segmented.selection_changed.connect(self._on_start_type_selected)
        if isinstance(self.flight.departure, OffMapSpawn):
            self.segmented.set_enabled(False)
        layout.addWidget(self.segmented)

        self.balance_note = QLabel(
            "Anything but Cold makes this flight untargetable by OCA/Aircraft "
            "missions, which affects balance."
        )
        self.balance_note.setWordWrap(True)
        self.balance_note.setStyleSheet(
            f"font-size: 11px; color: {AMBER}; background: transparent; border: none;"
        )
        layout.addWidget(self.balance_note)
        self._update_note()

        self.setLayout(layout)

    def _update_note(self) -> None:
        self.balance_note.setVisible(self.flight.start_type is not StartType.COLD)

    def on_pilot_selected(self) -> None:
        # Pilot selection detected. If this is a player flight, set start_type
        # as configured for players in the settings.
        # Otherwise, set the start_type as configured for AI.
        # https://github.com/dcs-liberation/dcs_liberation/issues/1567

        if isinstance(self.flight.departure, OffMapSpawn):
            return
        elif self.flight.roster.player_count > 0:
            self.flight.start_type = (
                self.flight.coalition.game.settings.default_start_type_client
            )
        else:
            self.flight.start_type = (
                self.flight.coalition.game.settings.default_start_type
            )

        self.segmented.set_value(self.flight.start_type)
        self._update_note()

        self.package_model.update_tot()
        self.start_type_changed.emit()

    def _on_start_type_selected(self, start_type: StartType) -> None:
        self.flight.start_type = start_type
        self._update_note()
        self.package_model.update_tot()
        self.start_type_changed.emit()
