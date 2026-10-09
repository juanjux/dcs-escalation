"""Refresh map pins and the open Player Aircrafts dialog after a saved-point edit."""

from game.server import EventStream
from game.sim import GameUpdateEvents


def publish_points_changed() -> None:
    EventStream.put_nowait(GameUpdateEvents(saved_points_updated=True))
    from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

    signal = GameUpdateSignal.get_instance()
    if signal is not None:
        signal.saved_points_changed.emit()
