from typing import Optional

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from game.ato.flighttype import FlightType
from game.config import RUNWAY_REPAIR_COST
from game.radio.ICLSContainer import ICLSContainer
from game.radio.RadioFrequencyContainer import RadioFrequencyContainer
from game.radio.TacanContainer import TacanContainer
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.theater import (
    ControlPoint,
    ControlPointType,
    NavalControlPoint,
    Player,
)
from qt_ui.dialogs import Dialog
from qt_ui.widgets.controls import button
from qt_ui.windows.airwingconfig.common import CHEAT_BORDER, CHEAT_HINT
from qt_ui.windows.basemenu.header import BaseHeader, FiguresStrip, kind_of
from qt_ui.models import GameModel
from qt_ui.uiconstants import app_settings, EVENT_ICONS
from qt_ui.widgets.QFrequencyWidget import QFrequencyWidget
from qt_ui.widgets.QICLSWidget import QICLSWidget
from qt_ui.widgets.QLink4Widget import QLink4Widget
from qt_ui.widgets.QTacanWidget import QTacanWidget
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.basemenu.NewUnitTransferDialog import NewUnitTransferDialog
from qt_ui.windows.basemenu.QBaseMenuTabs import QBaseMenuTabs

#: What it opens at, and the floor it cannot be dragged under. The floor is raised
#: per base to whatever that base's own content needs, because a window asked for a
#: size its layout will not fit into grows itself the moment it is shown.
DEFAULT_SIZE = QSize(1280, 900)
MINIMUM_SIZE = QSize(1200, 760)


class QBaseMenu2(QDialog):
    def __init__(self, parent, cp: ControlPoint, game_model: GameModel):
        super(QBaseMenu2, self).__init__(parent)

        # Attrs
        self.cp = cp
        self.game_model = game_model
        self.objectName = "menuDialogue"

        if self.cp.captured.is_blue:
            self.deliveryEvent = None

        self.setWindowIcon(EVENT_ICONS["capture"])

        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)

        self.setWindowTitle(self.cp.name)

        header = BaseHeader(self.cp, self.game_model)
        header.comms_rows = self._comms_rows()
        header.setLayout(header.layout())
        banner = header.findChild(QLabel)
        if banner is not None:
            pixmap = QPixmap(self.get_base_image())
            if not pixmap.isNull():
                banner.setPixmap(
                    pixmap.scaledToWidth(
                        1280, Qt.TransformationMode.SmoothTransformation
                    )
                )

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(header)
        self.figures = FiguresStrip(self.cp, self.game_model)
        main_layout.addWidget(self.figures)
        # Every purchase and sale emits this, and the strip is what the player checks
        # to decide whether to make another one.
        GameUpdateSignal.get_instance().budgetupdated.connect(self.on_budget_changed)

        tabs_holder = QVBoxLayout()
        tabs_holder.setContentsMargins(16, 0, 16, 0)
        tabs_holder.addWidget(QBaseMenuTabs(cp, self.game_model))
        main_layout.addLayout(tabs_holder, 1)
        main_layout.addLayout(self._footer())
        self.setLayout(main_layout)

        # Sized once, at the end, to something the layout will accept. Asking for a
        # size the content will not fit into means Qt grows the window again the
        # moment it is shown, which is the window dancing its way open; and the
        # content can demand a surprising amount, so the floor is what was asked for
        # or what the layout needs, whichever is larger.
        floor = MINIMUM_SIZE.expandedTo(main_layout.minimumSize())
        self.setMinimumSize(floor)
        if self._restore_geometry():
            self.resize(self.size().expandedTo(floor))
        else:
            self.resize(DEFAULT_SIZE.expandedTo(floor))

    def _comms_rows(self) -> list:
        """The radio, TACAN, ICLS and Link 4 editors this base actually has.

        Built here because they need the game model; the header only lays them out.
        """
        rows: list = []
        self.freq_widget = None
        self.link4_widget = None
        cp = self.cp
        if not cp.is_friendly(Player.BLUE):
            return rows
        if isinstance(cp, RadioFrequencyContainer):
            self.freq_widget = QFrequencyWidget(cp, self.game_model)
            rows.append(("Frequency", self.freq_widget))
        if isinstance(cp, TacanContainer):
            self.tacan_widget = QTacanWidget(cp, self.game_model)
            rows.append(("TACAN", self.tacan_widget))
        if isinstance(cp, ICLSContainer):
            self.icls_widget = QICLSWidget(cp, self.game_model)
            rows.append(("ICLS", self.icls_widget))
        if isinstance(cp, NavalControlPoint):
            self.link4_widget = QLink4Widget(cp, self.game_model)
            rows.append(("Link 4", self.link4_widget))
        if self.freq_widget and self.link4_widget:
            # They have to agree, so each checks the other when it changes.
            self.freq_widget.freq_changed.connect(self.link4_widget.check_freq)
            self.link4_widget.freq_changed.connect(self.freq_widget.check_freq)
        return rows

    def _footer(self) -> QHBoxLayout:
        """One primary action per owner, and the cheats in a block of their own.

        They used to sit in the same row as the real controls, which is how you end
        up capturing a base you meant to close the window on.
        """
        row = QHBoxLayout()
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(10)

        cheats = self._cheat_block()
        if cheats is not None:
            row.addWidget(cheats)
        row.addStretch()

        if self.cp.runway_is_destroyable and self.cp.runway_status is not None:
            if self.cp.runway_status.damaged:
                self.repair_button = button("", "normal", self.begin_runway_repair)
                self.update_repair_button()
                row.addWidget(self.repair_button)

        if FlightType.OCA_RUNWAY in self.cp.mission_types(for_player=Player.BLUE):
            row.addWidget(button("Plan airfield strike…", "danger", self.new_package))

        if self.cp.captured.is_blue and self.has_transfer_destinations:
            row.addWidget(
                button("Transfer units…", "normal", self.open_transfer_dialog)
            )

        row.addWidget(button("Close", "primary", self.close))
        return row

    def _cheat_block(self) -> Optional[QWidget]:
        buttons = []
        if (
            self.cp.runway_is_destroyable
            and self.game_model.game.settings.enable_runway_state_cheat
        ):
            self.cheat_runway_state = button("", "normal", self.on_cheat_runway_state)
            self.update_cheat_runway_state_text()
            buttons.append(self.cheat_runway_state)
        if self.cheat_capturable:
            label = "Sink/Resurrect" if self.cp.is_fleet else "Capture"
            buttons.append(button(label, "normal", self.cheat_capture))
        if not buttons:
            return None

        row = QHBoxLayout()
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)
        tag = QLabel("CHEAT")
        tag.setStyleSheet(
            f"color: {CHEAT_HINT}; font-size: 11px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        row.addWidget(tag)
        for cheat in buttons:
            row.addWidget(cheat)

        # Marked off with an amber outline rather than filled with one. The Air Wing
        # card's amber fill sits on a card two shades darker than this footer; against
        # this one the same brown reads as a mud puddle in the corner of the window.
        holder = QWidget()
        holder.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        holder.setObjectName("baseCheats")
        holder.setStyleSheet(
            f"#baseCheats {{ background: transparent;"
            f" border: 1px dashed {CHEAT_BORDER}; border-radius: 3px; }}"
        )
        holder.setLayout(row)
        return holder

    @property
    def cheat_capturable(self) -> bool:
        return self.game_model.game.settings.enable_base_capture_cheat

    def cheat_capture(self) -> None:
        events = GameUpdateEvents()
        if self.cp.is_fleet:
            for go in self.cp.ground_objects:
                if go.is_naval_control_point:
                    if go.alive_unit_count > 0:
                        for u in go.units:
                            u.kill(events)
                    else:
                        for u in go.units:
                            u.revive(events)
        else:
            self.cp.capture(
                self.game_model.game, events, for_player=self.cp.captured.opponent
            )
            mrp = MissionResultsProcessor(self.game_model.game)
            mrp.redeploy_units(self.cp)
        # Reinitialized ground planners and the like. The ATO needs to be reset because
        # missions planned against the flipped base (or killed carrier) are no longer valid.
        self.game_model.game.initialize_turn(events)
        EventStream.put_nowait(events)
        GameUpdateSignal.get_instance().updateGame(self.game_model.game)
        state = self.game_model.game.check_win_loss()
        GameUpdateSignal.get_instance().gameStateChanged(state)
        self.close()

    @property
    def has_transfer_destinations(self) -> bool:
        return self.game_model.game.transit_network_for(
            self.cp.captured
        ).has_destinations(self.cp)

    def update_cheat_runway_state_text(self) -> None:
        if self.cp.runway_can_be_repaired:
            self.cheat_runway_state.setText("CHEAT: Repair runway")
        else:
            self.cheat_runway_state.setText("CHEAT: Destroy runway")

    def on_cheat_runway_state(self) -> None:
        if self.cp.runway_can_be_repaired:
            self.cp.runway_status.repair()
        else:
            self.cp.runway_status.damage()
        self.update_cheat_runway_state_text()
        self.update_repair_button()
        self.figures.refresh()
        with EventStream.event_context() as events:
            events.update_control_point(self.cp)

    @property
    def can_repair_runway(self) -> bool:
        return self.cp.captured.is_blue and self.cp.runway_can_be_repaired

    @property
    def can_afford_runway_repair(self) -> bool:
        return self.game_model.game.blue.budget >= RUNWAY_REPAIR_COST

    def begin_runway_repair(self) -> None:
        if not self.can_afford_runway_repair:
            QMessageBox.critical(
                self,
                "Cannot repair runway",
                f"Runway repair costs ${RUNWAY_REPAIR_COST}M but you have "
                f"only ${self.game_model.game.blue.budget}M available.",
                QMessageBox.StandardButton.Ok,
            )
            return
        if not self.can_repair_runway:
            QMessageBox.critical(
                self,
                "Cannot repair runway",
                f"Cannot repair this runway.",
                QMessageBox.StandardButton.Ok,
            )
            return

        self.cp.begin_runway_repair()
        self.game_model.game.blue.budget -= RUNWAY_REPAIR_COST
        self.update_repair_button()
        self.figures.refresh()
        GameUpdateSignal.get_instance().updateGame(self.game_model.game)

    def update_repair_button(self) -> None:
        self.repair_button.setVisible(True)
        turns_remaining = self.cp.runway_status.repair_turns_remaining
        if self.cp.captured.is_blue and turns_remaining is not None:
            self.repair_button.setText("Repairing...")
            self.repair_button.setDisabled(True)
            return

        if self.can_repair_runway:
            if self.can_afford_runway_repair:
                self.repair_button.setText(f"Repair ${RUNWAY_REPAIR_COST}M")
                self.repair_button.setDisabled(False)
                return
            else:
                self.repair_button.setText(
                    f"Cannot afford repair ${RUNWAY_REPAIR_COST}M"
                )
                self.repair_button.setDisabled(True)
                return

        self.repair_button.setVisible(False)
        self.repair_button.setDisabled(True)

    def on_budget_changed(self, _game: object) -> None:
        self.figures.refresh()

    # --- the size you chose -------------------------------------------------

    #: Per kind rather than per base: a carrier holds different things from a FOB and
    #: wants a different size, but every FOB wants the same one.
    def geometry_key(self) -> str:
        return f"baseMenuGeometry/{kind_of(self.cp)}"

    @staticmethod
    def _qsettings() -> QSettings:
        return app_settings()

    def _restore_geometry(self) -> bool:
        """Whether there was a remembered size to go back to."""
        saved = self._qsettings().value(self.geometry_key())
        return saved is not None and self.restoreGeometry(saved)

    def closeEvent(self, close_event: QCloseEvent):
        self._qsettings().setValue(self.geometry_key(), self.saveGeometry())
        GameUpdateSignal.get_instance().updateGame(self.game_model.game)

    def get_base_image(self):
        if (
            self.cp.cptype == ControlPointType.AIRCRAFT_CARRIER_GROUP
            or self.cp.cptype == ControlPointType.LHA_GROUP
        ):
            carrier_type = self.cp.get_carrier_group_type(always_supercarrier=True)
            # A hull whose class the lookup does not recognise gives None; show the
            # generic art rather than taking the whole dialog down.
            if carrier_type is not None:
                return f"./resources/ui/units/ships/{carrier_type.id}.png"
            return "./resources/ui/airbase.png"
        elif self.cp.cptype == ControlPointType.FOB and self.cp.has_helipads:
            return "./resources/ui/heliport.png"
        elif self.cp.cptype == ControlPointType.FOB:
            return "./resources/ui/fob.png"
        else:
            return "./resources/ui/airbase.png"

    def new_package(self) -> None:
        Dialog.open_new_package_dialog(self.cp, parent=self.window())

    def open_transfer_dialog(self) -> None:
        NewUnitTransferDialog(self.game_model, self.cp, parent=self.window()).show()
