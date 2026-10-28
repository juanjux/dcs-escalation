"""Apply missile assignments on the existing Qt campaign command queue."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from game import missiletargets
from game.server import EventStream
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

if TYPE_CHECKING:
    from game import Game
    from qt_ui.groundmovement import GroundMovementCommands


def apply(
    game: Game,
    commands: GroundMovementCommands,
    source_id: UUID,
    owner: Player,
    selection: dict[str, Any] | None,
) -> dict[str, Any]:
    commands.require_planning(game)
    if selection is None:
        missiletargets.clear(game, source_id, owner)
        result: dict[str, Any] = {"source_id": str(source_id), "cleared": True}
    else:
        result = missiletargets.assign(game, source_id, owner, **selection)
    EventStream.put_nowait(GameUpdateEvents().update_tgo(game.db.tgos.get(source_id)))
    signal = GameUpdateSignal.get_instance()
    if signal is not None:
        signal.missile_targets_changed.emit()
    return result
