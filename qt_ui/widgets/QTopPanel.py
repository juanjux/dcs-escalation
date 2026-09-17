import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QMovie
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QToolBar,
    QWidget,
)

import qt_ui.uiconstants as CONST
from qt_ui.liberation_theme import get_theme_icons
from qt_ui.widgets.controls import style_button
from game import Game, persistency
from game.ato.flight import Flight
from game.ato.flightstate import Uninitialized
from game.ato.package import Package
from game.ato.starttype import StartType
from game.ato.traveltime import TotEstimator
from game.profiling import logged_duration
from game.server import EventStream
from game.weather.atmosxliveweather import (
    live_weather_enabled,
    refresh_live_weather,
)
from game.sim import GameUpdateEvents
from qt_ui.models import GameModel
from qt_ui.simcontroller import SimController
from qt_ui.uiflags import UiFlags
from qt_ui.widgets import commandbar
from qt_ui.widgets.QConditionsDialog import QConditionsDialog
from qt_ui.widgets.QConditionsWidget import QConditionsWidget
from qt_ui.widgets.clientslots import MaxPlayerCount
from qt_ui.widgets.QMissionProgressPanel import MissionProgressPanel
from game.income import Income
from game.missiongenerator.realisticcascampaign import (
    RealisticCASConfigurationError,
    validate_compatibility,
)
from game.plugins.manager import LuaPluginManager
from game.theater import Player
from qt_ui.dialogs import open_once
from qt_ui.windows.AirWingDialog import AirWingDialog
from qt_ui.windows.finances.QFinancesMenu import QFinancesMenu
from qt_ui.windows.intel import IntelWindow
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.PendingTransfersDialog import PendingTransfersDialog
from qt_ui.windows.QWaitingForMissionResultWindow import DebriefingFileWrittenSignal


class QTopPanel(QFrame):
    def __init__(
        self, game_model: GameModel, sim_controller: SimController, ui_flags: UiFlags
    ) -> None:
        super(QTopPanel, self).__init__()
        self.game_model = game_model
        self.sim_controller = sim_controller
        # One reference each: they used to share a single `self.dialog`, so opening
        # one dropped the only reference the other had.
        self.air_wing_dialog: Optional[QDialog] = None
        self.transfers_dialog: Optional[QDialog] = None

        # One strip instead of six group boxes. See qt_ui/widgets/commandbar.py for
        # the cells; the mission-launch machinery below is untouched.
        self.setFixedHeight(commandbar.BAR_HEIGHT)
        self.setStyleSheet(f"QTopPanel {{ background: {commandbar.BAR_BG}; }}")

        # Kept alive but not shown: it holds the turn and weather widgets that
        # QConditionsDialog is built from, which the cells open on a double click.
        self.conditionsWidget = QConditionsWidget(sim_controller)
        self.conditionsWidget.refresh_weather_requested.connect(
            self.refresh_live_weather
        )
        self.conditionsWidget.hide()

        self.turn_cell = commandbar.TurnCell()
        self.weather_cell = commandbar.WeatherCell(self.refresh_live_weather)
        for cell in (self.turn_cell, self.weather_cell):
            cell.mouseDoubleClickEvent = self._open_conditions  # type: ignore[method-assign]
        self.factions_cell = commandbar.FactionsCell()
        self.budget_cell = commandbar.BudgetCell(self.open_finances)
        self.intel_cell = commandbar.IntelCell(self.open_intel)

        pass_turn_text = "Pass Turn"
        if not self.game or self.game.turn == 0:
            pass_turn_text = "Begin Campaign"
        self.passTurnButton = QPushButton(pass_turn_text)
        self.passTurnButton.setIcon(CONST.ICONS["PassTurn"])
        style_button(self.passTurnButton, "primary")
        self.passTurnButton.clicked.connect(self.passTurn)
        if not self.game:
            self.passTurnButton.setEnabled(False)

        self.proceedButton = QPushButton("Take off")
        self.proceedButton.setIcon(CONST.ICONS["Proceed"])
        style_button(self.proceedButton, "primary")
        self.proceedButton.clicked.connect(self.launch_mission)
        if not self.game or self.game.turn == 0:
            self.proceedButton.setEnabled(False)

        self.air_wing = QPushButton("Air Wing")
        self.air_wing.setDisabled(True)
        style_button(self.air_wing)
        self.air_wing.clicked.connect(self.open_air_wing)

        self.transfers = QPushButton("Transfers")
        self.transfers.setDisabled(True)
        style_button(self.transfers)
        self.transfers.clicked.connect(self.open_transfers)

        # The debriefing is modal and easily lost behind the main window on an alt-tab,
        # or closed before it has been read. This puts it back.
        self.debriefing = QPushButton("Debriefing")
        self.debriefing.setDisabled(True)
        style_button(self.debriefing)
        self.debriefing.setToolTip("Show the last debriefing again")
        self.debriefing.clicked.connect(self.open_debriefing)

        # OPFOR-AI commander indicator (only shown when the setting is on); lights up for
        # a few seconds on each API call the LLM makes (no manual on/off), and Take Off
        # is blocked while it's lit.
        self.ai_status_button = QPushButton("OPFOR AI: idle")
        style_button(self.ai_status_button)
        self.ai_status_button.setToolTip("LLM OPFOR commander — click for status")
        self.ai_status_button.clicked.connect(self._show_ai_status)
        self.ai_status_button.setVisible(False)
        # Robot-general icon, with a looping "thinking" animation while the LLM plans.
        theme = get_theme_icons()
        self._ai_idle_icon = QIcon(f"./resources/ui/misc/{theme}/opfor-commander.png")
        self.ai_status_button.setIcon(self._ai_idle_icon)
        self.ai_status_button.setIconSize(QSize(20, 20))
        self._ai_thinking_movie = QMovie(
            f"./resources/ui/misc/{theme}/opfor-commander-thinking.gif"
        )
        self._ai_thinking_movie.setScaledSize(QSize(20, 20))
        self._ai_thinking_movie.frameChanged.connect(
            lambda: self.ai_status_button.setIcon(
                QIcon(self._ai_thinking_movie.currentPixmap())
            )
        )

        self._ai_status_timer = QTimer(self)
        self._ai_status_timer.timeout.connect(self._refresh_ai_status)
        self._ai_status_timer.start(1000)

        self.controls = [
            self.air_wing,
            self.transfers,
            self.passTurnButton,
            self.proceedButton,
        ]

        for button in (
            self.air_wing,
            self.transfers,
            self.debriefing,
            self.ai_status_button,
            self.passTurnButton,
            self.proceedButton,
        ):
            button.setFixedHeight(30)

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(16, 0, 16, 0)
        self.layout.setSpacing(16)
        # Status on the left, in the order you read a turn: when, then who, then what
        # you have to spend it on.
        self._intel_divider = commandbar.Divider()
        for cell in (
            self.turn_cell,
            self.weather_cell,
            self.factions_cell,
            self.budget_cell,
            self.intel_cell,
        ):
            if cell is self.intel_cell:
                divider: Optional[commandbar.Divider] = self._intel_divider
            elif cell is self.turn_cell:
                divider = None
            else:
                divider = commandbar.Divider()
            if divider is not None:
                self.layout.addWidget(divider, 0, Qt.AlignmentFlag.AlignVCenter)
            self.layout.addWidget(cell, 0, Qt.AlignmentFlag.AlignVCenter)
        # The dialogs sit with the status they belong to, not across the window from
        # it; only what ends the turn is pinned to the right.
        self.layout.addWidget(commandbar.Divider(), 0, Qt.AlignmentFlag.AlignVCenter)
        dialogs = QHBoxLayout()
        dialogs.setContentsMargins(0, 0, 0, 0)
        dialogs.setSpacing(8)
        for widget in (self.air_wing, self.transfers, self.debriefing):
            dialogs.addWidget(widget)
        dialogs.addWidget(self.ai_status_button)
        self.layout.addLayout(dialogs)

        self.layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        players = MaxPlayerCount(self.game_model.ato_model)
        commandbar.blend_into_bar(players)
        actions.addLayout(players)
        actions.addWidget(self.passTurnButton)
        actions.addWidget(self.proceedButton)
        self.layout.addLayout(actions)

        self.setLayout(self.layout)

        GameUpdateSignal.get_instance().gameupdated.connect(self.setGame)
        GameUpdateSignal.get_instance().budgetupdated.connect(self.budget_update)

    def refresh_live_weather(self) -> None:
        """Fetch the observation again and redraw with it."""
        game = self.game
        if game is None:
            return
        # The fetch shells out to the ATMOS-X CLI and can take a few seconds.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            refreshed = refresh_live_weather(game)
        finally:
            QApplication.restoreOverrideCursor()
        if refreshed is not None:
            # The reason comes from the CLI itself ("No METAR data available for
            # UGKS."), so show it: the player asked for this fetch and can act on it,
            # by picking a station or waiting, without opening the log.
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("No observation")
            box.setText(
                "Could not fetch a METAR observation, so the turn keeps the "
                "weather it already had."
            )
            box.setInformativeText(refreshed)
            box.exec()
            return
        GameUpdateSignal.get_instance().updateGame(game)

    @property
    def game(self) -> Optional[Game]:
        return self.game_model.game

    def setGame(self, game: Optional[Game]):
        if game is None:
            return

        self.air_wing.setEnabled(True)
        self.transfers.setEnabled(True)
        self.refresh_debriefing_button()

        # The hidden conditions widget still does the work: it owns the icon, the
        # tooltip with everything the strip has no room for, and the two widgets
        # QConditionsDialog is built from.
        can_refresh = live_weather_enabled(game.settings)
        self.conditionsWidget.setCurrentTurn(game.turn, game.conditions, can_refresh)
        weather_widget = self.conditionsWidget.weather_widget

        self.turn_cell.set_turn(game.turn, game.conditions)
        self.weather_cell.set_weather(game.conditions, can_refresh)
        self.weather_cell.set_icon(weather_widget.weather_icon.pixmap())
        for cell in (self.turn_cell, self.weather_cell):
            cell.setToolTip(weather_widget.toolTip())
        self.factions_cell.set_factions(game.blue.faction.name, game.red.faction.name)
        self.budget_cell.set_budget(
            game.blue.budget, Income(game, player=Player.BLUE).total
        )
        self.budget_cell.set_enabled(True)
        self.intel_cell.set_intel(
            commandbar.intel_ratios(game), gathering=game.turn == 0
        )
        self.intel_cell.set_enabled(True)
        self._fit_cells()

        self.setControls(True)

        if game.turn > 0:
            self.passTurnButton.setText("Pass Turn")
        elif game.turn == 0:
            self.passTurnButton.setText("Begin Campaign")
            self.proceedButton.setEnabled(False)
        else:
            raise RuntimeError(f"game.turn out of bounds!\n  value = {game.turn}")

    def open_air_wing(self) -> None:
        self.air_wing_dialog = open_once(
            "air-wing", lambda: AirWingDialog(self.game_model, self.window())
        )

    def open_transfers(self) -> None:
        self.transfers_dialog = open_once(
            "transfers", lambda: PendingTransfersDialog(self.game_model)
        )

    def refresh_debriefing_button(self) -> None:
        """Offer the last mission's report whenever there is one.

        Called on a game update and the moment a debriefing arrives -- the arrival is
        exactly when it can go missing behind the main window -- and the report is kept
        on the game, so a campaign loaded in a later session still has it.
        """
        window = self.window()
        available = getattr(window, "has_debriefing_to_show", None)
        self.debriefing.setEnabled(bool(available and available()))

    def open_debriefing(self) -> None:
        window = self.window()
        show = getattr(window, "show_last_debriefing", None)
        if show is not None:
            show()

    def _refresh_ai_status(self) -> None:
        from game.agent.session import AI_SESSION

        s = self.game.settings if self.game else None
        enabled = bool(s and s.opfor_ai_enabled)
        self.ai_status_button.setVisible(enabled)
        if not enabled:
            return
        snap = AI_SESSION.snapshot()
        if snap["active"]:
            self.ai_status_button.setText(
                f"OPFOR AI: {snap['status'] or 'planning...'}"
            )
            self.ai_status_button.setStyleSheet(
                # red so the button contrasts with the green "thinking" animation balls
                "color: white; background-color: #c62828; font-weight: bold;"
            )
            if self._ai_thinking_movie.state() != QMovie.MovieState.Running:
                self._ai_thinking_movie.start()
        else:
            self.ai_status_button.setText("OPFOR AI: idle")
            self.ai_status_button.setStyleSheet("color: gray;")
            if self._ai_thinking_movie.state() == QMovie.MovieState.Running:
                self._ai_thinking_movie.stop()
                self.ai_status_button.setIcon(self._ai_idle_icon)

    def _show_ai_status(self) -> None:
        from game.agent import service
        from game.agent.session import AI_SESSION

        snap = AI_SESSION.snapshot()
        try:
            rest = service.connect_url()
            mcp = service.mcp_url()
        except Exception:
            rest = mcp = "(unavailable)"
        box = QMessageBox(self)
        box.setWindowTitle("OPFOR AI commander")
        box.setText(
            f"Active: {snap['active']}\n"
            f"Status: {snap['status'] or '(none)'}\n"
            f"Last update: {snap['updated_at'] or '(never)'}\n\n"
            f"Connect an LLM —\n"
            f"REST (any HTTP/REST client or curl): {rest}\n"
            f"MCP (any MCP-compatible client): {mcp}"
        )
        cancel_btn = None
        if snap["active"]:
            cancel_btn = box.addButton(
                "Cancel AI turn", QMessageBox.ButtonRole.DestructiveRole
            )
            style_button(cancel_btn, "danger")
        style_button(box.addButton(QMessageBox.StandardButton.Close))
        box.exec()
        if cancel_btn is not None and box.clickedButton() == cancel_btn:
            AI_SESSION.cancel()

    def passTurn(self):
        with logged_duration("Skipping turn"):
            self.game.pass_turn(no_action=True)
            GameUpdateSignal.get_instance().updateGame(self.game)
            state = self.game_model.game.check_win_loss()
            GameUpdateSignal.get_instance().gameStateChanged(state)
            self.proceedButton.setEnabled(True)

    def negative_start_packages(self, now: datetime) -> List[Package]:
        packages = []
        for package in self.game_model.ato_model.ato.packages:
            if not package.flights:
                continue
            for flight in package.flights:
                if isinstance(flight.state, Uninitialized):
                    flight.state.reinitialize(now)
                if flight.state.is_waiting_for_start:
                    startup = flight.flight_plan.startup_time()
                    if startup < now:
                        packages.append(package)
                        break
        return packages

    @staticmethod
    def fix_tots(packages: List[Package], now: datetime) -> None:
        for package in packages:
            estimator = TotEstimator(package)
            package.time_over_target = estimator.earliest_tot(now)

    def confirm_no_client_launch(self) -> bool:
        result = QMessageBox.question(
            self,
            "Continue without player pilots?",
            (
                "No player pilots have been assigned to flights. Continuing will allow "
                "the AI to perform the mission, but players will be unable to "
                "participate.<br />"
                "<br />"
                "To assign player pilots to a flight, select a package from the "
                "Packages panel on the left of the main window, and then a flight from "
                "the Flights panel below the Packages panel. The edit button below the "
                "Flights panel will allow you to assign specific pilots to the flight. "
                "If you have no player pilots available, the checkbox next to the "
                "name will convert them to a player.<br />"
                "<br />Click 'Yes' to continue with an AI only mission"
                "<br />Click 'No' if you'd like to make more changes."
            ),
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return result == QMessageBox.StandardButton.Yes

    def confirm_negative_start_time(
        self, negative_starts: List[Package], now: datetime
    ) -> bool:
        formatted = "<br />".join(
            [f"{p.primary_task} {p.target.name}" for p in negative_starts]
        )
        mbox = QMessageBox(
            QMessageBox.Icon.Question,
            "Continue with past start times?",
            (
                "Some flights in the following packages have start times set "
                "earlier than mission start time:<br />"
                "<br />"
                f"{formatted}<br />"
                "<br />"
                "Flight start times are estimated based on the package TOT, so it "
                "is possible that not all flights will be able to reach the "
                "target area at their assigned times.<br />"
                "<br />"
                "You can either continue with the mission as planned, with the "
                "misplanned flights potentially flying too fast and/or missing "
                "their rendezvous; automatically fix negative TOTs; or cancel "
                "mission start and fix the packages manually."
            ),
            parent=self,
        )
        auto = mbox.addButton(
            "Fix TOTs automatically", QMessageBox.ButtonRole.ActionRole
        )
        ignore = mbox.addButton(
            "Continue without fixing", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel = mbox.addButton(QMessageBox.StandardButton.Cancel)
        mbox.setEscapeButton(cancel)
        mbox.exec_()
        clicked = mbox.clickedButton()
        if clicked == auto:
            self.fix_tots(negative_starts, now)
            return True
        elif clicked == ignore:
            return True
        return False

    def check_no_missing_pilots(self) -> bool:
        missing_pilots = []
        for package in self.game.blue.ato.packages:
            for flight in package.flights:
                if flight.missing_pilots > 0:
                    missing_pilots.append((package, flight))

        if not missing_pilots:
            return False

        formatted = "<br />".join(
            [f"{p.primary_task} {p.target}: {f}" for p, f in missing_pilots]
        )
        mbox = QMessageBox(
            QMessageBox.Icon.Critical,
            "Flights are missing pilots",
            (
                "The following flights are missing one or more pilots:<br />"
                "<br />"
                f"{formatted}<br />"
                "<br />"
                "You must either assign pilots to those flights or cancel those "
                "missions."
            ),
            parent=self,
        )
        mbox.setEscapeButton(mbox.addButton(QMessageBox.StandardButton.Close))
        mbox.exec_()
        return True

    def launch_mission(self):
        """Finishes planning and waits for mission completion."""
        from game.agent.session import AI_SESSION

        if AI_SESSION.active:
            QMessageBox.warning(
                self,
                "OPFOR AI is planning",
                "The OPFOR AI commander is still planning red's turn.\n\n"
                "Wait for it to finish (the OPFOR AI indicator goes idle) or "
                "cancel it before taking off.",
            )
            return

        try:
            validate_compatibility(LuaPluginManager.plugins())
        except RealisticCASConfigurationError as ex:
            QMessageBox.warning(self, "Incompatible mission plugins", str(ex))
            return

        # OPFOR-AI fallback: if red was left for the LLM but it never played, run the
        # scripted commander so red's turn is never empty.
        try:
            from game.agent import service

            service.run_opfor_fallback_if_needed()
        except Exception:
            logging.exception("OPFOR-AI scripted fallback failed; continuing")

        if not self.game.ato_has_clients() and not self.confirm_no_client_launch():
            return

        if self.check_no_missing_pilots():
            return

        now = self.sim_controller.current_time_in_sim
        negative_starts = self.negative_start_packages(now)
        if negative_starts:
            if not self.confirm_negative_start_time(negative_starts, now):
                return

        self.sim_controller.generate_miz(
            persistency.mission_path_for("retribution_nextturn.miz")
        )

        self._begin_mission_panel()

    # ------------------------------------------------------------------ #
    # Embedded "mission in progress" panel (replaces the old waiting dialog).
    # The live QtWebEngine map is DETACHED (reparented out, not just hidden) and
    # the panel takes its splitter slot; the rest of the UI is covered with dim
    # scrims so the panel reads as modal.
    # ------------------------------------------------------------------ #
    def _begin_mission_panel(self) -> None:
        if getattr(self, "_mp_panel", None) is not None:
            return  # a mission is already in progress; ignore re-entry

        window = self.window()
        self._mp_map = getattr(window, "liberation_map", None)
        self._mp_info_panel = getattr(window, "info_panel", None)
        self._mp_splitter = (
            self._mp_map.parentWidget() if self._mp_map is not None else None
        )
        self._mp_map_index = -1
        self._mp_splitter_sizes = None
        self._mp_debriefing = None
        self._mp_real_start = datetime.now()
        self._mp_disabled: List[QWidget] = []
        self._mp_disabled_actions: List[QAction] = []

        panel = MissionProgressPanel()
        self._mp_panel = panel
        if self.game is not None:
            panel.set_doctrine(self.game.settings.ignore_non_combat_air_losses)

        if self._mp_splitter is not None and self._mp_map is not None:
            self._mp_map_index = self._mp_splitter.indexOf(self._mp_map)
            self._mp_splitter_sizes = self._mp_splitter.sizes()
            # DETACH the QtWebEngine map, don't just hide it. setVisible(False)
            # leaves its native HWND a child of the main window, so subsequent
            # window ops keep issuing synchronous SendMessage to the Chromium
            # renderer process and deadlock the GUI thread (NtUserMessageCall).
            # Reparenting to None takes that HWND out of the main window's tree, so
            # the renderer can't be messaged. Do it BEFORE adding the panel/scrims.
            # GPU acceleration stays on (software GL makes the map unusable).
            self._mp_map.setParent(None)
            self._mp_map.hide()
            # Reparenting/hiding does NOT kill the QtWebEngine renderer process, and
            # the live renderer's desktop-GL compositing is the peer the GUI thread's
            # wglSwapLayerBuffers swap deadlocks on. Discard it so the renderer stops
            # while the panel is up (it reloads when the map is shown again).
            self._mp_map.discard_renderer()
            self._mp_splitter.insertWidget(self._mp_map_index, panel)
            # Hide the info panel too so the mission panel owns the whole splitter
            # column (no leftover strip, no live splitter handle to drag it away).
            if self._mp_info_panel is not None:
                self._mp_info_panel.setVisible(False)

        # The old waiting dialog was WindowModal: it blocked the menu bar, toolbars
        # and their shortcuts (New/Open/Save...). Loading a different game mid-mission
        # would swap the game underneath the still-running poll thread. Reproduce that
        # block by disabling those + the top-panel controls for the panel's lifetime.
        self.setControls(False)
        # The menu lives in a strip with the toolbar icons now; disabling the
        # strip blocks both, which is what the block below is for.
        menu_bar = getattr(window, "menu_strip", None)
        if menu_bar is None and hasattr(window, "menuBar"):
            menu_bar = window.menuBar()
        chrome = [
            w for w in [menu_bar, *window.findChildren(QToolBar)] if w is not None
        ]
        for w in chrome:
            if w.isEnabled():
                w.setEnabled(False)
                self._mp_disabled.append(w)
        for action in window.findChildren(QAction):
            if action.isEnabled():
                action.setEnabled(False)
                self._mp_disabled_actions.append(action)

        overlay_parent = (
            window.centralWidget() if hasattr(window, "centralWidget") else window
        )
        panel.install_scrims(
            [self, getattr(window, "ato_panel", None)],
            overlay_parent,
        )
        # The menu bar + toolbars live outside the central widget; disabling alone
        # doesn't grey them under the custom QSS, so dim them with their own scrims.
        if chrome:
            panel.install_scrims(chrome, window)

        panel.accept_btn.clicked.connect(self._mp_accept)
        panel.manually_submit_btn.clicked.connect(self._mp_submit_manually)
        panel.abort_btn.clicked.connect(self._mp_abort)

        DebriefingFileWrittenSignal.get_instance().debriefingReceived.connect(
            self._mp_on_debriefing
        )
        self._mp_wait_thread = self.sim_controller.wait_for_debriefing(
            lambda d: DebriefingFileWrittenSignal.get_instance().sendDebriefing(d)
        )
        # Stop the (non-daemon) poll thread if the app quits mid-mission, else it
        # keeps polling state.json and blocks interpreter shutdown (orphaned process).
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._mp_on_quit)

        self._mp_timer = QTimer(self)
        self._mp_timer.timeout.connect(self._mp_tick)
        self._mp_timer.start(1000)
        self._mp_tick()

    def _mp_on_quit(self) -> None:
        thread = getattr(self, "_mp_wait_thread", None)
        if thread is not None:
            thread.stop()
        timer = getattr(self, "_mp_timer", None)
        if timer is not None:
            timer.stop()

    def _mp_on_debriefing(self, debriefing) -> None:
        try:
            self._mp_debriefing = debriefing
            self._mp_panel.ingest_debriefing(debriefing)
        except Exception:
            logging.exception("Failed to ingest debriefing into mission panel")

    def _mp_tick(self) -> None:
        panel = getattr(self, "_mp_panel", None)
        if panel is None:
            return
        try:
            sim_time = self.sim_controller.current_time_in_sim_if_game_loaded
        except Exception:
            sim_time = None
        try:
            # DCS mission elapsed is fed from the debriefing's model_time in
            # ingest_debriefing; the campaign sim clock is paused during the mission.
            panel.update_clocks(
                self._mp_real_start,
                datetime.now(),
                sim_time,
                None,
                self.game.turn,
            )
        except Exception:
            logging.exception("mission panel: clock update failed")
        try:
            self._mp_update_conditions(panel)
        except Exception:
            logging.exception("mission panel: conditions update failed")
        try:
            self._mp_update_flights(panel)
        except Exception:
            logging.exception("mission panel: flights update failed")

    def _mp_update_conditions(self, panel: MissionProgressPanel) -> None:
        cond = self.game.conditions
        weather = cond.weather
        wind = weather.wind.at_0m
        speed_kt = round(getattr(wind, "speed", 0) * 1.94384)
        wind_str = f"{round(getattr(wind, 'direction', 0)):03d}° {speed_kt} kt"
        preset = getattr(weather.clouds, "preset", None)
        clouds = preset.name if preset is not None else "Clear"
        temp = getattr(weather.atmospheric, "temperature_celsius", None)
        tod = cond.time_of_day.name.replace("_", " ").title()
        panel.update_conditions(wind_str, clouds, temp, tod)

    def _mp_update_flights(self, panel: MissionProgressPanel) -> None:
        airborne = combat = waiting = 0
        for _, flight in self.game.db.flights.objects.items():
            try:
                if not flight.blue.is_blue:
                    continue  # the panel reports own-force (BLUE) flights only
            except Exception:
                continue
            state = flight.state
            if state is None or not state.alive:
                continue
            if state.in_combat:
                combat += 1
                airborne += 1
            elif state.in_flight:
                airborne += 1
            elif state.is_waiting_for_start:
                waiting += 1
        panel.update_flights(airborne, combat, waiting)

    def _mp_accept(self) -> None:
        debriefing = getattr(self, "_mp_debriefing", None)
        if debriefing is None:
            return
        # Turn processing blocks the UI; show an indeterminate busy dialog meanwhile.
        progress = QProgressDialog(
            "End of Mission Detected, processing Mission Data",
            "",
            0,
            0,
            self.window(),
        )
        progress.setWindowTitle("Processing")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        QApplication.processEvents()
        try:
            with logged_duration("Turn processing"):
                self.sim_controller.process_results(debriefing)
                self.game.pass_turn()
                GameUpdateSignal.get_instance().sendDebriefing(debriefing)
                GameUpdateSignal.get_instance().updateGame(self.game)
        finally:
            progress.close()
        self._mp_teardown()

    def _mp_submit_manually(self) -> None:
        file = QFileDialog.getOpenFileName(
            self, "Select game file to open", filter="json(*.json)", dir="."
        )
        if file[0] == "":
            return
        logging.debug("Processing manually submitted %s", file[0])
        wait_thread = getattr(self, "_mp_wait_thread", None)
        if wait_thread is not None:
            wait_thread.stop()
            self._mp_wait_thread = None
        DebriefingFileWrittenSignal.get_instance().sendDebriefing(
            self.sim_controller.debrief_current_state(Path(file[0]), force_end=True)
        )

    def _mp_abort(self) -> None:
        self.sim_controller.set_game(self.game)
        events = GameUpdateEvents()
        for _, f in self.game.db.flights.objects.items():
            f.state = Uninitialized(f, self.game.settings)
            events.update_flight(f)
        for cp in self.game.theater.controlpoints:
            cp.release_parking_slots()
        GameUpdateSignal.get_instance().updateGame(self.game)
        EventStream().put_nowait(events)
        self._mp_teardown()

    def _mp_teardown(self) -> None:
        timer = getattr(self, "_mp_timer", None)
        if timer is not None:
            timer.stop()
            self._mp_timer = None
        wait_thread = getattr(self, "_mp_wait_thread", None)
        if wait_thread is not None:
            wait_thread.stop()
            self._mp_wait_thread = None
        try:
            DebriefingFileWrittenSignal.get_instance().debriefingReceived.disconnect(
                self._mp_on_debriefing
            )
        except (RuntimeError, TypeError):
            pass
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.disconnect(self._mp_on_quit)
            except (RuntimeError, TypeError):
                pass
        panel = getattr(self, "_mp_panel", None)
        if panel is not None:
            panel.remove_scrims()
            panel.setParent(None)
            panel.deleteLater()
            self._mp_panel = None
        if getattr(self, "_mp_info_panel", None) is not None:
            self._mp_info_panel.setVisible(True)
            self._mp_info_panel = None
        if getattr(self, "_mp_map", None) is not None:
            # Reactivate the renderer we discarded in _begin_mission_panel (reloads
            # the map when it becomes visible again).
            self._mp_map.restore_renderer()
            # Re-attach the detached map into its old splitter slot (the panel was
            # already removed above, so the index lines up with the original layout).
            # Show it BEFORE setSizes, else the still-hidden widget gets 0px.
            if self._mp_splitter is not None and self._mp_map_index >= 0:
                self._mp_splitter.insertWidget(self._mp_map_index, self._mp_map)
                self._mp_map.setVisible(True)
                if self._mp_splitter_sizes is not None:
                    self._mp_splitter.setSizes(self._mp_splitter_sizes)
            else:
                self._mp_map.setVisible(True)
        self._mp_map = None
        self._mp_splitter = None
        # Re-enable the chrome we disabled while the panel was up.
        for w in getattr(self, "_mp_disabled", []):
            w.setEnabled(True)
        self._mp_disabled = []
        for action in getattr(self, "_mp_disabled_actions", []):
            action.setEnabled(True)
        self._mp_disabled_actions = []
        self.setControls(True)

    def budget_update(self, game: Game):
        self.budget_cell.set_budget(
            game.blue.budget, Income(game, player=Player.BLUE).total
        )

    def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._fit_cells()

    def _fit_cells(self) -> None:
        """Narrow windows give up Intel first, then the winds."""
        width = self.width()
        shows_intel = width >= commandbar.MIN_WIDTH_FOR_INTEL
        self.intel_cell.setVisible(shows_intel)
        self._intel_divider.setVisible(shows_intel)
        self.weather_cell.show_winds(width >= commandbar.MIN_WIDTH_FOR_WINDS)

    def _open_conditions(self, event: Any) -> None:
        """Double-clicking the turn or weather opens the full conditions dialog."""
        QConditionsDialog(
            self.conditionsWidget.time_turn_widget,
            self.conditionsWidget.weather_widget,
        ).exec()

    def open_finances(self) -> None:
        self.finances_dialog = QFinancesMenu(self.game)
        self.finances_dialog.show()

    def open_intel(self) -> None:
        self.intel_dialog = IntelWindow(self.game)
        self.intel_dialog.show()

    def setControls(self, enabled: bool):
        for controller in self.controls:
            controller.setEnabled(enabled)

    def check_for_contact(self) -> bool:
        if (
            len(self.game.blue.ato.packages) == 0
            and len(self.game.red.ato.packages) == 0
        ):
            mbox = QMessageBox(
                QMessageBox.Icon.Critical,
                "No flights planned",
                (
                    "No flights are planned and fast forward to first contact "
                    "is enabled. You must either plan flights or disable fast forward."
                ),
                parent=self,
            )
            mbox.setEscapeButton(mbox.addButton(QMessageBox.StandardButton.Close))
            mbox.exec_()
            return False
        return True
