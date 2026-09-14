from PySide6.QtWidgets import QVBoxLayout, QWidget

from game.ato import Flight, FlightType
from qt_ui.models import GameModel
from qt_ui.widgets.QCallsignWidget import QCallsignWidget
from qt_ui.widgets.QFrequencyWidget import QFrequencyWidget
from qt_ui.widgets.QTacanWidget import QTacanWidget


class QCommsEditor(QWidget):
    """Frequency, callsign and (for a tanker) TACAN.

    A plain widget: the card around it carries the caption, and the hint that used to
    be a sentence inside the box now sits beside that caption.
    """

    def __init__(self, flight: Flight, game: GameModel):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        is_refuel = flight.flight_type == FlightType.REFUELING
        has_tacan = flight.unit_type.dcs_unit_type.tacan

        layout.addWidget(QFrequencyWidget(flight, game))
        layout.addWidget(QCallsignWidget(flight, game))
        if is_refuel and has_tacan:
            layout.addWidget(QTacanWidget(flight, game))
        super().__init__()
        self.flight = flight

        self.setLayout(layout)
