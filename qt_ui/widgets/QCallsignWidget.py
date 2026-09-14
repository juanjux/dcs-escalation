from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from game.radio.CallsignContainer import CallsignContainer, Callsign
from qt_ui.models import GameModel
from qt_ui.windows.QCallsignDialog import QCallsignDialog
from qt_ui.widgets.QFrequencyWidget import AUTO_CHIP, KEY_LABEL, SET_VALUE


class QCallsignWidget(QWidget):
    callsign_changed = Signal(QWidget)

    def __init__(self, container: CallsignContainer, game_model: GameModel) -> None:
        super().__init__()

        self.ct = container
        self.gm = game_model

        columns = QHBoxLayout()
        self.setLayout(columns)

        key = QLabel("Callsign")
        key.setFixedWidth(84)
        key.setStyleSheet(KEY_LABEL)
        columns.addWidget(key)

        self.callsign = QLabel(self._get_label_text())
        columns.addWidget(self.callsign)
        columns.addStretch()

        self.set_callsign_btn = QPushButton("Set Callsign")
        self.set_callsign_btn.setProperty("class", "comms")
        self.set_callsign_btn.setFixedWidth(100)
        columns.addWidget(self.set_callsign_btn)
        self.set_callsign_btn.clicked.connect(self.open_callsign_dialog)

        self.reset_callsign_btn = QPushButton("Reset Callsign")
        self.reset_callsign_btn.setProperty("class", "btn-danger comms")
        self.reset_callsign_btn.setFixedWidth(100)
        columns.addWidget(self.reset_callsign_btn)
        self.reset_callsign_btn.clicked.connect(self.reset_callsign)

        self._sync_state()

    def _get_label_text(self) -> str:
        if self.ct.callsign is None:
            return "AUTO"
        return f"{self.ct.callsign.name} {self.ct.callsign.nr}"

    def _sync_state(self) -> None:
        automatic = self.ct.callsign is None
        self.callsign.setText(self._get_label_text())
        self.callsign.setStyleSheet(AUTO_CHIP if automatic else SET_VALUE)
        self.reset_callsign_btn.setEnabled(not automatic)

    def open_callsign_dialog(self) -> None:
        self.callsign_dialog = QCallsignDialog(self, self.ct)
        self.callsign_dialog.accepted.connect(self.assign_callsign)
        self.callsign_dialog.show()

    def assign_callsign(self) -> None:
        name = self.callsign_dialog.callsign_name_input.currentText()
        nr = self.callsign_dialog.callsign_nr_input.value()
        self.ct.callsign = Callsign(name, nr)
        self._sync_state()
        self.callsign_changed.emit(self)

    def reset_callsign(self) -> None:
        self.ct.callsign = None
        self._sync_state()
        self.callsign_changed.emit(self)

    def _reset_color_and_tooltip(self):
        self._sync_state()
        self.callsign.setToolTip(None)
