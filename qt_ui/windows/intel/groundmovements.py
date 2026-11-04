"""Active ground deployments projected into Intel without inventory copies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    QObject,
)

from game.groundmovement.orders import GroundMovementOrders
from game.groundmovement.report import destination_label, movement_reports
from game.theater import Player
from qt_ui.models import TransferModel
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal


@dataclass(frozen=True)
class GroundMovementEntry:
    order_id: UUID
    player: Player
    title: str
    description: str


class GroundMovementsModel(QAbstractListModel):
    def __init__(self, transfers: TransferModel, parent: QObject) -> None:
        super().__init__(parent)
        self.transfers = transfers
        self.entries: list[GroundMovementEntry] = []
        transfers.modelReset.connect(self.refresh)
        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            signal.ground_movements_changed.connect(
                self.refresh, Qt.ConnectionType.QueuedConnection
            )
        self.refresh()

    def refresh(self) -> None:
        entries = []
        model = getattr(self.transfers, "game_model", None)
        game = model.game if model is not None else None
        store = getattr(game, "ground_movements", None)
        if game is not None and isinstance(store, GroundMovementOrders):
            owners = [Player.BLUE]
            if game.settings.enable_enemy_buy_sell:
                owners.append(Player.RED)
            sources = {cp.id: cp.name for cp in game.theater.controlpoints}
            sources.update({t.id: t.name for t in game.db.tgos.objects.values()})
            for owner in owners:
                for report in movement_reports(game, None, owner, active_only=True):
                    tgo = game.db.tgos.get(report.detachment_id)
                    count = report.surviving_units
                    units = str(count if count is not None else report.original_units)
                    if count is not None and count != report.original_units:
                        units += f"/{report.original_units}"
                    destination = destination_label(game, report.destination)
                    if report.destination.target_id is None:
                        destination = "GPS " + destination
                    source = sources.get(report.source_id, "Unavailable source")
                    status = report.status.capitalize()
                    if report.pause_reason:
                        status += f": {report.pause_reason}"
                    progress = (
                        f"{status} · {report.progress:.0%} complete · "
                        f"{report.remaining_distance_m / 1000:.1f} km remaining"
                    )
                    if report.remaining_turns is not None:
                        progress += f" · ETA {report.remaining_turns} turn(s)"
                    entries.append(
                        GroundMovementEntry(
                            report.order_id,
                            owner,
                            f"{units} units — {tgo.name}",
                            f"{source} → {destination}\n{progress}",
                        )
                    )
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.entries):
            return None
        entry = self.entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return entry.title
        if role == TransferModel.TransferRole:
            return entry
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.title + "\n" + entry.description
        return None
