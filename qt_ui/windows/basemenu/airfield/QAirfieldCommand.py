from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from game.theater import ControlPoint
from qt_ui.models import GameModel
from qt_ui.widgets.cards import HINT
from qt_ui.windows.basemenu.airfield.QAircraftRecruitmentMenu import (
    QAircraftRecruitmentMenu,
)


class QAirfieldCommand(QFrame):
    """Buying aircraft, and nothing else.

    What is fragged from here has its own tab now: it answers a different question
    and was taking a third of the width from the list you came to read. The four-line
    paragraph about transferring squadrons becomes the one line under it that says
    where to go.
    """

    def __init__(self, cp: ControlPoint, game_model: GameModel):
        super(QAirfieldCommand, self).__init__()
        self.cp = cp
        self.game_model = game_model
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(QAircraftRecruitmentMenu(self.cp, self.game_model))

        note = QLabel(
            "Only squadrons based here can take aircraft. To base another squadron "
            "here, move it from the Air Wing."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size: 11px; color: {HINT}; background: transparent; border: none;"
        )
        layout.addWidget(note)

        self.setLayout(layout)
