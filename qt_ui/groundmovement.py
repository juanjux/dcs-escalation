"""Serialize player movement commands on the Qt campaign thread."""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError
from typing import Callable, TYPE_CHECKING, TypeVar
from uuid import UUID

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from game.groundmovement.dispatch import dispatch_armor, stop_armor
from game.groundmovement.base import preview_base_movement, dispatch_base_movement
from game.groundmovement.orders import MovementDestination, GroundPosition
from game.groundmovement.planning import preview_armor_movement
from game.groundmovement.report import preview_token
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game
    from game.groundmovement.dispatch import ArmorTransit
    from qt_ui.models import GameModel
    from game.dcs.groundunittype import GroundUnitType

T = TypeVar("T")


class MovementCommandError(ValueError):
    pass


class GroundMovementCommands(QObject):
    requested = Signal(object, object)

    def __init__(self, model: GameModel) -> None:
        super().__init__()
        self.model = model
        self.requested.connect(self._execute, Qt.ConnectionType.QueuedConnection)

    @Slot(object, object)
    def _execute(self, action: Callable[[], object], future: Future[object]) -> None:
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(action())
        except Exception as exc:
            future.set_exception(exc)

    def run(self, action: Callable[[], T]) -> T:
        if QThread.currentThread() == self.thread():
            return action()
        future: Future[T] = Future()
        self.requested.emit(action, future)
        try:
            return future.result(timeout=10)
        except TimeoutError as exc:
            # A command still waiting in the Qt queue must not run after timeout.
            if future.cancel():
                raise MovementCommandError("Campaign is busy; try again") from exc
            return future.result()

    def require_planning(self, game: Game) -> None:
        self.require_campaign(game)
        loop = self.model.sim_controller.game_loop
        if loop is not None and loop.started:
            raise MovementCommandError("Movement orders cannot change during a mission")

    def require_campaign(self, game: Game) -> None:
        if self.model.game is not game:
            raise MovementCommandError(
                "The campaign changed; reopen the movement dialog"
            )

    def inspect(self, game: Game, action: Callable[[], T]) -> T:
        self.require_campaign(game)
        return action()

    def dispatch(
        self,
        game: Game,
        source_id: UUID,
        owner: Player,
        selected: list[int],
        destination: MovementDestination,
        expected_preview: str,
    ) -> ArmorTransit:
        self.require_planning(game)
        preview = preview_armor_movement(game, source_id, owner, selected, destination)
        if preview_token(game, preview) != expected_preview:
            raise MovementCommandError("The movement changed; request a new preview")
        events = GameUpdateEvents()
        result = dispatch_armor(game, source_id, owner, selected, destination, events)
        self.publish(events)
        return result

    def stop(self, game: Game, order_id: UUID, owner: Player) -> None:
        self.require_planning(game)
        if order_id not in game.ground_movements.transits:
            raise ValueError("No such dispatched movement")
        events = GameUpdateEvents()
        stop_armor(game, order_id, owner, events)
        self.publish(events)

    def dispatch_base(
        self,
        game: Game,
        source_id: UUID,
        owner: Player,
        selected: dict[GroundUnitType, int],
        position: GroundPosition,
        expected_preview: str,
    ) -> ArmorTransit:
        self.require_planning(game)
        preview = preview_base_movement(game, source_id, owner, selected, position)
        if preview_token(game, preview) != expected_preview:
            raise MovementCommandError(
                "The base stock or movement changed; request a new preview"
            )
        events = GameUpdateEvents()
        result = dispatch_base_movement(
            game, source_id, owner, selected, position, events
        )
        self.publish(events)
        transfer_model = getattr(self.model, "transfer_model", None)
        if transfer_model is not None:
            transfer_model.inventory_changed.emit()
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            signal.budgetupdated.emit(game)
        return result

    @staticmethod
    def publish(events: GameUpdateEvents) -> None:
        from game.server import EventStream

        EventStream.put_nowait(events)
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        signal = GameUpdateSignal.get_instance()
        if signal is not None:
            signal.ground_movements_changed.emit()
