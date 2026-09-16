from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from game.server.settings import ServerSettings
from qt_ui.liberation_install import server_port
from qt_ui.models import GameModel


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
    def __init__(self, game_model: GameModel, dev: bool, parent) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self.setMinimumSize(800, 600)

        self.page = LoggingWebPage(self)
        # Required to allow "cross-origin" access from file:// scoped canvas.html to the
        # localhost HTTP backend.
        self.page.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )

        # The map copies coordinates to the clipboard through execCommand, which the web
        # view blocks unless this is on. The asynchronous clipboard API is not an
        # alternative: it is defined on a file:// page but rejects every write.
        self.page.settings().setAttribute(
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
        url.setQuery(f"server={host}:{port}")
        self.page.load(url)
        self.setPage(self.page)

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
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
            # setLifecycleState is a silent no-op (not an exception) if the page is
            # still visible or hasn't finished loading, so confirm it actually took --
            # otherwise the renderer stays alive and the panel can still deadlock.
            if self.page.lifecycleState() != QWebEnginePage.LifecycleState.Discarded:
                logging.warning(
                    "Map renderer not discarded (page still active/loading?); "
                    "the mission panel may still hit the desktop-GL deadlock."
                )
        except (AttributeError, RuntimeError):
            logging.exception("Failed to discard the map renderer")

    def restore_renderer(self) -> None:
        """Reactivate the renderer discarded by :meth:`discard_renderer` (reloads)."""
        try:
            self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
        except (AttributeError, RuntimeError):
            logging.exception("Failed to reactivate the map renderer")
