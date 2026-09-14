"""The small pieces the Air Wing Configuration panes share.

The selectors, spinners and the parking tracker are unchanged from the form this
replaced: they are what the dialog is made of, not what was wrong with it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QSpinBox, QWidget

from game.dcs.aircrafttype import AircraftType
from game.squadrons import Squadron
from game.theater import Airfield, ControlPoint

#: The one palette, taken from the Air Wing list so the two windows read as one app.
BG = "#2D3E50"
PANEL = "#26343F"
HEADER = "#1B2732"
LINE = "#1D2731"
ACCENT = "#8FC3F0"
AMBER = "#E0A86B"
GREEN = "#86C39A"
RED = "#D9645E"
TEXT_PRIMARY = "#F2F7FA"
TEXT_BASE = "#D3DFE8"
TEXT_SECONDARY = "#B7C6D2"
TEXT_LABEL = "#7C8B99"
TEXT_MUTED = "#6B7A87"
TEXT_TERTIARY = "#8E9DAA"
FIELD_BG = "#26343F"
FIELD_BORDER = "#3A4B5C"
BAR_TRACK = "#1D2731"
BAR_OTHERS = "#3F5D73"

CHEAT_BG = "#2A2218"
CHEAT_BORDER = "#4A3A28"
CHEAT_HEADER = "#33291E"
CHEAT_HEADER_LINE = "#4A3A28"
CHEAT_CHIP_BG = "#2A1F12"
CHEAT_HINT = "#C9B28E"


class SquadronBaseSelector(QComboBox):
    """A combo box for selecting a squadron's home air base.

    The combo box will automatically be populated with all air bases compatible with the
    squadron.
    """

    def __init__(
        self,
        bases: Iterable[ControlPoint],
        selected_base: Optional[ControlPoint],
        aircraft_type: Optional[AircraftType],
    ) -> None:
        super().__init__()
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.bases = list(bases)
        self.set_aircraft_type(aircraft_type)

        if selected_base:
            self.setCurrentText(selected_base.name)

    def set_aircraft_type(self, aircraft_type: Optional[AircraftType]) -> None:
        self.clear()
        if aircraft_type:
            for base in self.bases:
                if not base.can_operate(aircraft_type) and not isinstance(
                    base, Airfield
                ):
                    continue
                self.addItem(base.name, base)
            self.model().sort(0)
            self.setEnabled(True)
        else:
            self.addItem("Select aircraft type first", None)
            self.setEnabled(False)
        self.update()


class SquadronSizeSpinner(QSpinBox):
    def __init__(self, starting_size: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Disable text editing, which wouldn't work in the first place, but also
        # obnoxiously selects the text on change (highlighting it) and leaves a flashing
        # cursor in the middle of the element when clicked.
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setEnabled(False)
        self.setMinimum(1)
        self.setValue(starting_size)


class PilotLimitSpinner(QSpinBox):
    """This squadron's own pilot ceiling, or the campaign's if it has none.

    The campaign setting is shown as the value when nothing has been chosen, and the
    suffix says so, so the box reads as "this is what it will be" rather than as an
    empty field somebody forgot to fill in.
    """

    def __init__(self, squadron: Squadron, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.squadron = squadron
        self.setMinimum(1)
        self.setMaximum(200)
        self._default = squadron.settings.squadron_pilot_limit
        override = squadron.pilot_limit_override
        self.setValue(self._default if override is None else override)
        self.setToolTip(
            "How many pilots this squadron may hold. Leave it at the campaign's own "
            f"figure ({self._default}) to follow that setting."
        )
        self.valueChanged.connect(self._update_suffix)
        self._update_suffix(self.value())

    def _update_suffix(self, value: int) -> None:
        # Short, because it shares a 300 px column with the size spinner; the tooltip
        # carries the sentence.
        self.setSuffix("  default" if value == self._default else "")

    @property
    def chosen_limit(self) -> Optional[int]:
        """None while it matches the campaign, so moving that setting still moves it."""
        return None if self.value() == self._default else self.value()


class AirWingConfigParkingTracker(QWidget):
    allocation_changed = Signal()

    def __init__(self, squadrons: Iterable[Squadron]) -> None:
        super().__init__()
        self.by_cp: dict[ControlPoint, set[Squadron]] = defaultdict(set)
        for squadron in squadrons:
            self.add_squadron(squadron)

    def add_squadron(self, squadron: Squadron) -> None:
        self.by_cp[squadron.location].add(squadron)
        self.signal_change()

    def remove_squadron(self, squadron: Squadron) -> None:
        self.by_cp[squadron.location].discard(squadron)
        self.signal_change()

    def relocate_squadron(
        self,
        squadron: Squadron,
        prior_location: ControlPoint,
        new_location: ControlPoint,
    ) -> None:
        self.by_cp[prior_location].discard(squadron)
        self.by_cp[new_location].add(squadron)
        squadron.relocate_to(new_location)
        self.signal_change()

    def used_parking_at(self, control_point: ControlPoint) -> int:
        return sum(s.max_size for s in self.by_cp[control_point])

    def squadrons_at(self, control_point: ControlPoint) -> set[Squadron]:
        return self.by_cp[control_point]

    def signal_change(self) -> None:
        self.allocation_changed.emit()
