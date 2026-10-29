"""Controls for the optional tanker stop before the mission."""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from game.ato import prerefuel
from game.ato.flight import Flight
from game.ato.flightplans.barcap import BarCapFlightPlan
from game.ato.flightplans.tarcap import TarCapFlightPlan
from game.ato.flightplans.formationattack import FormationAttackFlightPlan


class QPreRefuelOptions(QWidget):
    def __init__(self, flight: Flight, changed: Callable[[], None]) -> None:
        super().__init__()
        self.flight = flight
        self.changed = changed
        plan = flight.flight_plan
        supported = not flight.is_helo and isinstance(
            plan, (FormationAttackFlightPlan, BarCapFlightPlan, TarCapFlightPlan)
        )
        label = (
            "Refuel before station"
            if isinstance(plan, (BarCapFlightPlan, TarCapFlightPlan))
            else "Refuel before the push"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox(label)
        self.enabled.setChecked(getattr(flight, "refuel_before_push", False))
        self.enabled.setToolTip(
            "Rebuild this flight's route with a compatible theater-tanker stop. "
            "Leave earlier to keep the Join/TOT or CAP station times. "
            "This is not an automatic mid-patrol refuel and return to station."
        )
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 60)
        self.minutes.setSuffix(" min")
        self.minutes.setValue(int(prerefuel.tanking_time(flight).total_seconds() / 60))
        self.minutes.setToolTip(
            "Planning allowance, not a forced disconnect time. The AI tanks to "
            "90% of internal fuel. Reset uses four minutes per aircraft plus one."
        )
        self.reset = QPushButton("Reset")
        row = QHBoxLayout()
        row.addWidget(QLabel("Minutes on the tanker"))
        row.addWidget(self.minutes)
        row.addWidget(self.reset)
        layout.addWidget(self.enabled)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.enabled.toggled.connect(self.toggle)
        self.minutes.valueChanged.connect(self.set_minutes)
        self.reset.clicked.connect(self.reset_minutes)
        self.supported = supported
        self.refresh()

    def refresh(self) -> None:
        flight = self.flight
        tanker = (
            prerefuel.planned_tanker(flight, flight.package.target.position)
            if self.supported
            else None
        )
        waiting = flight.state.is_waiting_for_start
        self.enabled.setEnabled(
            waiting
            and self.supported
            and (tanker is not None or self.enabled.isChecked())
        )
        self.minutes.setEnabled(waiting and self.enabled.isChecked())
        self.reset.setEnabled(self.minutes.isEnabled())
        if not self.supported:
            text = "Available for formation attacks, BARCAP and TARCAP."
        elif tanker is None:
            text = "No compatible theater tanker is planned (boom/probe profiles required)."
        else:
            text = f"Theater tanker: {tanker.unit_type}. Join/TOT and station times stay fixed."
        self.status.setText(text)

    def toggle(self, checked: bool) -> None:
        result = QMessageBox.question(
            self,
            "Rebuild route for refuelling?",
            "This changes the route and replaces manual waypoint edits. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            with QSignalBlocker(self.enabled):
                self.enabled.setChecked(not checked)
            return
        old = self.flight.refuel_before_push
        old_plan = self.flight._flight_plan_builder.existing_flight_plan
        self.flight.refuel_before_push = checked
        try:
            self.flight.recreate_flight_plan()
            prerefuel.remove_unneeded_post_stop(self.flight)
        except Exception as ex:
            self.flight.refuel_before_push = old
            self.flight._flight_plan_builder._flight_plan = old_plan
            with QSignalBlocker(self.enabled):
                self.enabled.setChecked(old)
            QMessageBox.warning(self, "Cannot plan refuelling", str(ex))
        else:
            self.changed()
        self.refresh()

    def set_minutes(self, minutes: int) -> None:
        self.flight.tanking_minutes = minutes
        self.changed()

    def reset_minutes(self) -> None:
        self.flight.tanking_minutes = None
        with QSignalBlocker(self.minutes):
            self.minutes.setValue(
                int(prerefuel.tanking_time(self.flight).total_seconds() / 60)
            )
        self.changed()
