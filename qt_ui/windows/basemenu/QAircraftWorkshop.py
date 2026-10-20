"""Base mechanics and the shared queue of damaged aircraft."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.aircraftmaintenance import hire_mechanic, sell_damaged, workshop_view
from game.theater import ControlPoint
from qt_ui.models import GameModel
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal


class QAircraftWorkshop(QWidget):
    changed = Signal(int)

    def __init__(self, base: ControlPoint, model: GameModel) -> None:
        super().__init__()
        self.base, self.model = base, model
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.hire = QPushButton()
        self.hire.clicked.connect(self._hire)
        layout.addWidget(self.hire)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Aircraft / squadron",
                "Health",
                "Status",
                "Repair turns",
                "Ready in turns",
                "Resale ($M)",
                "Action",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)
        hint = QLabel(
            "Spare mechanics help assigned aircraft and add their repair capacity. "
            "Each mechanic works on only one aircraft per turn. New damage cannot be repaired "
            "at the end of the same mission. Damaged aircraft still occupy parking."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        signals = GameUpdateSignal.get_instance()
        signals.budgetupdated.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        signals.gameupdated.connect(self.refresh, Qt.ConnectionType.QueuedConnection)
        self.refresh()

    def refresh(self, *_: object) -> None:
        game = self.model.game
        if game is None:
            return
        view = workshop_view(game, self.base)
        self.summary.setText(
            f"Mechanics: {view['mechanics']} total · {view['busy']} busy · {view['free']} free "
            f"| Each mechanic: up to {view['repair_percent_per_turn']:.1f}% of maximum health per turn"
        )
        self.hire.setText(f"Hire one mechanic — ${view['mechanic_cost_dollars']:,.0f}")
        self.hire.setEnabled(
            view["enabled"]
            and not self.base.sunk
            and self.base.captured.is_blue
            and game.blue.budget >= view["mechanic_price_m"]
        )
        # Qt defers deleting replaced cell widgets until the next event-loop
        # cycle. Hide them first so a refresh never paints two overlapping bars.
        for row in range(self.table.rowCount()):
            for column in (1, 6):
                old = self.table.cellWidget(row, column)
                if old is not None:
                    old.hide()
        self.table.clearContents()
        self.table.setRowCount(len(view["aircraft"]))
        for row, entry in enumerate(view["aircraft"]):
            health = entry["health_percent"]
            values = [
                f"{entry['aircraft']} — {entry['squadron']}",
                "Unknown" if health is None else f"{health:.1f}%",
                (
                    f"Repairing ({entry['assigned_mechanics']} mechanic{'s' if entry['assigned_mechanics'] != 1 else ''})"
                    if entry["assigned_mechanics"]
                    else "Queued"
                ),
                str(entry["working_turns_remaining"]),
                str(entry["turns_until_ready"]),
                f"{entry['sale_price_m']:.3f}",
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            if health is not None:
                bar = QProgressBar()
                bar.setRange(0, 1000)
                bar.setValue(round(health * 10))
                bar.setFormat(f"{health:.1f}%")
                bar.setStyleSheet("QProgressBar::chunk { background-color: #D9953B; }")
                self.table.setCellWidget(row, 1, bar)
            button = QPushButton("Sell…")
            button.setToolTip(
                "Sell this damaged aircraft at the configured discounted price."
            )
            button.setEnabled(not self.base.sunk and self.base.captured.is_blue)
            button.clicked.connect(lambda checked=False, item=entry: self._sell(item))
            self.table.setCellWidget(row, 6, button)
        self.changed.emit(len(view["aircraft"]))

    def _hire(self) -> None:
        game = self.model.game
        if game is None or not self.base.captured.is_blue:
            return
        try:
            hire_mechanic(game, self.base)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot hire mechanic", str(exc))
        GameUpdateSignal.get_instance().updateBudget(game)
        self.refresh()

    def _sell(self, entry: dict) -> None:
        game = self.model.game
        if game is None or not self.base.captured.is_blue:
            return
        if (
            QMessageBox.question(
                self,
                "Sell damaged aircraft",
                f"Sell this damaged {entry['aircraft']} for ${entry['sale_price_m']:.3f}M? "
                "This removes it from the workshop and squadron immediately.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        squadron = next(
            (
                sq
                for sq in game.blue.air_wing.iter_squadrons()
                if str(sq.id) == entry["squadron_id"]
            ),
            None,
        )
        if squadron is None:
            return
        try:
            sell_damaged(game, squadron, entry["id"])
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot sell aircraft", str(exc))
        GameUpdateSignal.get_instance().updateBudget(game)
        self.refresh()


def confirm_workshop_sale(parent: QWidget, squadron: object) -> bool:
    from game.aircraftmaintenance import repairs, sale_value

    # Shared by normal transfers, instant-transfer cheats and the Air Wing editor.
    from typing import cast
    from game.squadrons import Squadron

    sq = cast(Squadron, squadron)
    count = len(repairs(sq))
    if not count:
        return True
    value = count * sale_value(sq.coalition.game, sq)
    return (
        QMessageBox.question(
            parent,
            "Damaged aircraft cannot transfer",
            f"{sq.owned_aircraft - count} operational aircraft will transfer. "
            f"{count} damaged aircraft (repairing or queued) cannot transfer and will "
            f"be sold automatically for ${value:.3f}M. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )
