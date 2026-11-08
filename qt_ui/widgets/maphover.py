"""Transient map highlighting for buttons that point to campaign locations."""

from typing import Any, Callable
from uuid import uuid4

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget

from game.server import EventStream
from game.sim.gameupdateevents import GameUpdateEvents


class _MapHover(QObject):
    def __init__(self, button: QWidget, target: Callable[[], Any]) -> None:
        super().__init__(button)
        self.button = button
        self.target = target
        self.owner = uuid4()
        self.active = False
        self.last_target: tuple[Any, float, float] | None = None
        button.setMouseTracking(True)
        button.installEventFilter(self)
        button.destroyed.connect(self.clear)

    def clear(self) -> None:
        if self.active:
            self.active = False
            self.last_target = None
            EventStream.put_nowait(GameUpdateEvents(map_hover=(self.owner, None, None)))

    def refresh(self) -> None:
        """Resolve a location again after a virtual control moves or changes rows."""
        target = self.target() if self.button.isEnabled() else None
        position = getattr(target, "position", target)
        if position is None:
            self.clear()
            return
        latlng = position.latlng()
        identity = (getattr(target, "id", None), latlng.lat, latlng.lng)
        if identity == self.last_target:
            return
        self.last_target = identity
        self.active = True
        EventStream.put_nowait(
            GameUpdateEvents(
                map_hover=(self.owner, getattr(target, "id", None), latlng)
            )
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove)
            and self.button.isEnabled()
        ):
            self.refresh()
        elif event.type() in (
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.EnabledChange,
        ):
            self.clear()
        return False


def bind_map_hover(button: QWidget, target: Callable[[], Any]) -> _MapHover:
    """Resolve the current target on entry; do not move the map or open dialogs."""
    return _MapHover(button, target)
