"""Read-only map selection using the same route preview as the dispatch dialog."""

from __future__ import annotations

import json
import logging
import math
from typing import Callable, TYPE_CHECKING

from dcs import Point
from dcs.mapping import LatLng
from PySide6.QtCore import QFile, QIODevice, QObject, QTimer, Slot
from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout, QWidget

from game.groundmovement.orders import GroundPosition

if TYPE_CHECKING:
    from game.groundmovement.base import BaseMovementPreview
    from game.groundmovement.planning import ArmorMovementPreview
    from qt_ui.models import GameModel


class GroundDestinationBridge(QObject):
    """Keep campaign access on the GUI thread; never dispatch from a map click."""

    def __init__(
        self,
        model: GameModel,
        origin: Point,
        name: str,
        preview: Callable[[GroundPosition], ArmorMovementPreview | BaseMovementPreview],
        choose: Callable[[LatLng], None],
        cancel: Callable[[], None],
        parent: QObject | None = None,
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

    @Slot(result=str)
    def initial(self) -> str:
        at = self.origin.latlng()
        return json.dumps({"origin": {"lat": at.lat, "lng": at.lng}, "name": self.name})

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
        self.closed = True
        self.cancel()


class GroundDestinationDialog(QDialog):
    def __init__(
        self,
        model: GameModel,
        origin: Point,
        name: str,
        preview: Callable[[GroundPosition], ArmorMovementPreview | BaseMovementPreview],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        # Import lazily: tests of campaign previews need no WebEngine renderer.
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineScript
        from qt_ui.widgets.map.QLiberationMap import QLiberationMap

        self.selected: LatLng | None = None
        self.setWindowTitle("Choose ground movement destination")
        self.resize(1200, 800)
        layout = QVBoxLayout(self)
        self.map = QLiberationMap(model, False, self, query={"groundDestination": "1"})
        layout.addWidget(self.map)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.bridge = GroundDestinationBridge(
            model, origin, name, preview, self.choose, self.reject, self
        )
        self.finished.connect(lambda _: setattr(self.bridge, "closed", True))
        self.channel = QWebChannel(self.map.page())
        self.channel.registerObject("groundDestination", self.bridge)
        self.map.page().setWebChannel(self.channel)
        library = QFile(":/qtwebchannel/qwebchannel.js")
        if not library.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Qt WebChannel is unavailable")
        source = bytes(library.readAll().data()).decode("utf-8")
        library.close()
        script = QWebEngineScript()
        script.setName("ground-destination-bridge")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(
            source + "\nnew QWebChannel(qt.webChannelTransport, function(channel) {"
            "window.groundDestinationBridge = channel.objects.groundDestination;"
            "window.dispatchEvent(new Event('ground-destination-ready'));"
            "});"
        )
        self.map.page().scripts().insert(script)

    def choose(self, position: LatLng) -> None:
        self.selected = position
        QTimer.singleShot(0, self.accept)
