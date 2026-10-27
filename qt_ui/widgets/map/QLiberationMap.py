from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QFile, QIODevice, QUrl, QUrlQuery
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

from game.server.settings import ServerSettings
from qt_ui.liberation_install import server_port
from qt_ui.models import GameModel

if TYPE_CHECKING:
    from qt_ui.widgets.map.grounddestination import GroundDestinationBridge


class LoggingWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source: str,
    ) -> None:
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logging.error(message)
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            logging.warning(message)
        else:
            logging.info(message)


class QLiberationMap(QWebEngineView):
    def __init__(
        self,
        game_model: GameModel,
        dev: bool,
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self._ground_bridge: GroundDestinationBridge | None = None
        self._ground_channel: QWebChannel | None = None
        self._ground_session: str | None = None
        self.setMinimumSize(800, 600)

        page = LoggingWebPage(self)
        # Required to allow "cross-origin" access from file:// scoped canvas.html to the
        # localhost HTTP backend.
        page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        # The map copies coordinates to the clipboard through execCommand, which the web
        # view blocks unless this is on. The asynchronous clipboard API is not an
        # alternative: it is defined on a file:// page but rejects every write.
        page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )

        if dev:
            url = QUrl("http://localhost:3000")
        else:
            url = QUrl.fromLocalFile(str(Path("client/build/index.html").resolve()))
        server_settings = ServerSettings.get(server_port())
        host = server_settings.server_bind_address
        if host.startswith("::"):
            host = f"[{host}]"
        port = server_settings.server_port
        parameters = QUrlQuery()
        parameters.addQueryItem("server", f"{host}:{port}")
        url.setQuery(parameters)
        page.load(url)
        self.setPage(page)

    def begin_ground_selection(self, bridge: GroundDestinationBridge) -> None:
        if self._ground_bridge is not None:
            raise RuntimeError("A destination is already being selected")
        library = QFile(":/qtwebchannel/qwebchannel.js")
        if not library.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("Qt WebChannel is unavailable")
        source = bytes(library.readAll().data()).decode("utf-8")
        library.close()
        self._ground_bridge = bridge
        self._ground_session = str(uuid4())
        self._ground_channel = QWebChannel(self.page())
        self._ground_channel.registerObject("groundDestination", bridge)
        self.page().setWebChannel(self._ground_channel)
        self.loadStarted.connect(bridge.dismiss)
        self.renderProcessTerminated.connect(bridge.dismiss)
        session = json.dumps(self._ground_session)
        self.page().runJavaScript(
            source + "\nwindow.groundDestinationSession = " + session + ";"
            "new QWebChannel(qt.webChannelTransport, function(channel) {"
            f"if (window.groundDestinationSession !== {session}) return;"
            "const bridge = channel.objects.groundDestination;"
            "if (!window.groundDestinationModeReady) { bridge.dismiss(); return; }"
            "window.dispatchEvent(new CustomEvent('ground-destination-start',"
            f"{{detail: {{id: {session}, bridge: bridge}}}}));"
            "});"
        )

    def end_ground_selection(self, bridge: GroundDestinationBridge) -> None:
        if self._ground_bridge is not bridge:
            return
        session = json.dumps(self._ground_session)
        self.page().runJavaScript(
            f"if (window.groundDestinationSession === {session}) {{"
            "window.groundDestinationSession = null;"
            "window.dispatchEvent(new CustomEvent('ground-destination-end',"
            f"{{detail: {{id: {session}}}}}));}}"
        )
        self.loadStarted.disconnect(bridge.dismiss)
        self.renderProcessTerminated.disconnect(bridge.dismiss)
        self.page().setWebChannel(None)
        if self._ground_channel is not None:
            self._ground_channel.deregisterObject(bridge)
            self._ground_channel.deleteLater()
        self._ground_bridge = None
        self._ground_channel = None
        self._ground_session = None

    def discard_renderer(self) -> None:
        """Stop the QtWebEngine renderer process for this map.

        Hiding/reparenting the view does NOT kill the renderer; its live desktop-GL
        compositing is the peer the GUI thread's ``wglSwapLayerBuffers`` deadlocks on
        (a synchronous SendMessage that never returns -> "Not Responding"). Discarding
        the page lifecycle actually stops the renderer process. The page reloads
        automatically when the view is shown again. Used while the mission panel owns
        the map's splitter slot.
        """
        try:
            self.page().setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
            # setLifecycleState is a silent no-op (not an exception) if the page is
            # still visible or hasn't finished loading, so confirm it actually took --
            # otherwise the renderer stays alive and the panel can still deadlock.
            if self.page().lifecycleState() != QWebEnginePage.LifecycleState.Discarded:
                logging.warning(
                    "Map renderer not discarded (page still active/loading?); "
                    "the mission panel may still hit the desktop-GL deadlock."
                )
        except (AttributeError, RuntimeError):
            logging.exception("Failed to discard the map renderer")

    def restore_renderer(self) -> None:
        """Reactivate the renderer discarded by :meth:`discard_renderer` (reloads)."""
        try:
            self.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except (AttributeError, RuntimeError):
            logging.exception("Failed to reactivate the map renderer")
