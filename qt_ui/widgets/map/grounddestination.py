"""Read-only map selection using the same route preview as the dispatch dialog."""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Callable, TYPE_CHECKING

from dcs import Point
from dcs.mapping import LatLng
from PySide6.QtCore import QEvent, QEventLoop, QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from shiboken6 import isValid

from game.groundmovement.orders import GroundPosition

if TYPE_CHECKING:
    from game.groundmovement.base import BaseMovementPreview
    from game.groundmovement.planning import ArmorMovementPreview
    from qt_ui.models import GameModel


class GroundDestinationBridge(QObject):
    """Keep campaign access on the GUI thread; never dispatch from a map click."""

    connected = Signal()

    @Slot()
    def ready(self) -> None:
        if not self.closed:
            self.connected.emit()

    def __init__(
        self,
        model: GameModel,
        origin: Point,
        name: str,
        preview: Callable[
            [GroundPosition],
            ArmorMovementPreview | BaseMovementPreview | dict[str, Any],
        ],
        choose: Callable[[LatLng], None],
        cancel: Callable[[], None],
        parent: QObject | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self.game = model.get()
        self.turn = self.game.turn
        self.origin = origin
        self.name = name
        self.calculate = preview
        self.choose = choose
        self.cancel = cancel
        self.closed = False
        self.details = details or {}

    @Slot(result=str)
    def initial(self) -> str:
        at = self.origin.latlng()
        return json.dumps(
            {
                "origin": {"lat": at.lat, "lng": at.lng},
                "name": self.name,
                **self.details,
            }
        )

    def evaluate(self, lat: float, lng: float) -> dict[str, object]:
        if self.closed:
            raise ValueError("The destination selector is closed")
        self.model.ground_movement_commands.require_planning(self.game)
        if self.game.turn != self.turn:
            raise ValueError("The turn changed. Close and reopen the movement dialog")
        if not (math.isfinite(lat) and math.isfinite(lng)) or not (
            -90 <= lat <= 90 and -180 <= lng <= 180
        ):
            raise ValueError("Invalid latitude or longitude")
        point = Point.from_latlng(LatLng(lat, lng), self.game.theater.terrain)
        result = self.calculate(GroundPosition(point.x, point.y))
        if isinstance(result, dict):
            return {"valid": True, "position": {"lat": lat, "lng": lng}, **result}

        def coordinates(position: GroundPosition) -> dict[str, float]:
            at = Point(position.x, position.z, self.game.theater.terrain).latlng()
            return {"lat": at.lat, "lng": at.lng}

        return {
            "valid": True,
            "position": {"lat": lat, "lng": lng},
            "road_distance_m": result.road_distance_m,
            "offroad_distance_m": result.offroad_distance_m,
            "arrival_in_turns": result.arrival_in_turns,
            "segments": [
                {
                    "start": coordinates(segment.start),
                    "end": coordinates(segment.end),
                    "on_road": segment.on_road,
                }
                for segment in result.route.segments
            ],
        }

    @Slot(float, float, result=str)
    def preview(self, lat: float, lng: float) -> str:
        try:
            return json.dumps(self.evaluate(lat, lng))
        except (ValueError, PermissionError) as exc:
            return json.dumps({"valid": False, "error": str(exc)})
        except Exception:
            logging.exception("Cannot preview the ground destination")
            return json.dumps(
                {"valid": False, "error": "Could not calculate this route"}
            )

    @Slot(float, float, result=str)
    def pick(self, lat: float, lng: float) -> str:
        # Revalidate at click time, even if the hover preview was valid.
        response = self.preview(lat, lng)
        if json.loads(response)["valid"]:
            self.closed = True
            self.choose(LatLng(lat, lng))
        return response

    @Slot()
    def dismiss(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.cancel()


class GroundDestinationPicker(QObject):
    """Temporarily lend the main map to a movement dialog, without reloading it."""

    def __init__(
        self,
        model: GameModel,
        origin: Point,
        name: str,
        preview: Callable[
            [GroundPosition],
            ArmorMovementPreview | BaseMovementPreview | dict[str, Any],
        ],
        parent: QWidget,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.owner = parent
        ancestor: QWidget | None = parent
        while ancestor is not None and not hasattr(ancestor, "liberation_map"):
            ancestor = ancestor.parentWidget()
        if ancestor is None:
            raise RuntimeError("The main campaign map is unavailable")
        self.window = ancestor
        self.map = getattr(ancestor, "liberation_map")
        self.selected: LatLng | None = None
        self.loop = QEventLoop(self)
        self.finished = False
        self.closing: set[QObject] = set()
        self.error: str | None = None
        self.bridge = GroundDestinationBridge(
            model, origin, name, preview, self.choose, self.reject, self, details
        )
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.connection_failed)
        self.bridge.connected.connect(self.timeout.stop)
        self.owner.destroyed.connect(self.reject)

    def exec(self) -> QDialog.DialogCode:
        hidden: list[QDialog] = []
        disabled: list[QWidget] = []
        actions = [a for a in self.window.findChildren(QAction) if a.isEnabled()]
        focus = QApplication.focusWidget()
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.window)
        escape.setContext(Qt.ShortcutContext.WindowShortcut)
        escape.activated.connect(self.reject)
        self.window.installEventFilter(self)
        self.owner.installEventFilter(self)
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        signals = GameUpdateSignal.get_instance()
        if signals is not None:
            signals.gameupdated.connect(self.reject)
            signals.ground_movements_changed.connect(self.reject)
        try:
            for action in actions:
                action.setEnabled(False)
            # Disable siblings along the map's ancestry, not the map itself.
            # This prevents campaign edits while preserving map pan and zoom.
            child = self.map
            while child is not self.window:
                container = child.parentWidget()
                if container is None:
                    raise RuntimeError("The main campaign map is unavailable")
                for sibling in container.findChildren(
                    QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
                ):
                    if sibling is not child and not sibling.isWindow():
                        if sibling.isEnabled():
                            disabled.append(sibling)
                            sibling.setEnabled(False)
                child = container
            for widget in QApplication.topLevelWidgets():
                ancestor = widget.parentWidget()
                while ancestor is not None and ancestor is not self.window:
                    ancestor = ancestor.parentWidget()
                if (
                    isinstance(widget, QDialog)
                    and widget.isVisible()
                    and ancestor is self.window
                ):
                    hidden.append(widget)
                    widget.hide()
            self.timeout.start(10000)
            self.map.begin_ground_selection(self.bridge)
            self.map.setFocus()
            if not self.finished:
                self.loop.exec()
        finally:
            self.bridge.closed = True
            self.timeout.stop()
            if isValid(self.map):
                self.map.end_ground_selection(self.bridge)
            if isValid(escape):
                escape.setEnabled(False)
                escape.deleteLater()
            if isValid(self.window):
                self.window.removeEventFilter(self)
            if isValid(self.owner):
                self.owner.removeEventFilter(self)
            if signals is not None and isValid(signals):
                signals.gameupdated.disconnect(self.reject)
                signals.ground_movements_changed.disconnect(self.reject)
            for action in actions:
                if isValid(action):
                    action.setEnabled(True)
            for widget in disabled:
                if isValid(widget):
                    widget.setEnabled(True)
            if isValid(self.window) and self.window.isVisible():
                for dialog in hidden:
                    if isValid(dialog) and dialog not in self.closing:
                        dialog.show()
                if isValid(self.owner) and self.owner.isVisible():
                    self.owner.raise_()
                    self.owner.activateWindow()
                if focus is not None and isValid(focus):
                    focus.setFocus()
        if self.error:
            raise RuntimeError(self.error)
        return (
            QDialog.DialogCode.Accepted
            if self.selected is not None
            else QDialog.DialogCode.Rejected
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Close:
            self.closing.add(watched)
            self.reject()
        return False

    def reject(self) -> None:
        self.finished = True
        self.bridge.closed = True
        self.loop.quit()

    def connection_failed(self) -> None:
        self.error = (
            "The main map did not respond. Close and reopen the movement dialog"
        )
        self.reject()

    def choose(self, position: LatLng) -> None:
        self.selected = position
        # Let WebChannel return the click response before releasing this bridge.
        QTimer.singleShot(0, self, self.reject)
