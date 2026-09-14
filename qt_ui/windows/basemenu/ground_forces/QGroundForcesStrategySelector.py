"""Choosing what the units here do about one neighbour.

The combo used to list the enum's own names -- DEFENSIVE, BREAKTHROUGH, ELIMINATION --
which say what the constant is called rather than what the units will do. Each one now
carries a line of plain English and a colour, so the six can be told apart at a glance
and picking one does not need the source.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QComboBox, QSizePolicy

from game.theater import CombatStance, ControlPoint

#: What each stance does, in the words a player would use.
STANCES: dict[CombatStance, tuple[str, str, str]] = {
    CombatStance.AGGRESSIVE: (
        "Aggressive",
        "advance and take ground",
        "#D9645E",
    ),
    CombatStance.BREAKTHROUGH: (
        "Breakthrough",
        "rush forward in strength",
        "#D97B4F",
    ),
    CombatStance.ELIMINATION: (
        "Elimination",
        "hunt down the enemy force",
        "#E0A86B",
    ),
    CombatStance.AMBUSH: (
        "Ambush",
        "hold, with the anti-tank teams forward",
        "#86C39A",
    ),
    CombatStance.DEFENSIVE: (
        "Defensive",
        "hold, do not advance",
        "#8FC3F0",
    ),
    CombatStance.RETREAT: (
        "Retreat",
        "give ground and fall back",
        "#8E9DAA",
    ),
}


def swatch(colour: str, side: int = 10) -> QPixmap:
    """The stance's colour as a square, so the list reads as a scale."""
    pixmap = QPixmap(side, side)
    pixmap.fill(QColor(colour))
    return pixmap


class QGroundForcesStrategySelector(QComboBox):
    def __init__(self, cp: ControlPoint, enemy_cp: ControlPoint):
        super(QGroundForcesStrategySelector, self).__init__()
        self.cp = cp
        self.enemy_cp = enemy_cp

        if enemy_cp.id not in self.cp.stances:
            self.cp.stances[enemy_cp.id] = CombatStance.DEFENSIVE

        # In the order above -- most aggressive to least -- rather than the enum's,
        # which is the order the constants happened to be written in.
        for index, (stance, (name, gloss, colour)) in enumerate(STANCES.items()):
            self.addItem(swatch(colour), f"{name} — {gloss}", userData=stance)
            if self.cp.stances[enemy_cp.id] == stance:
                self.setCurrentIndex(index)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # A combo box asks for the width of its longest line, and these are lines.
        # The popup still shows them in full.
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(14)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.currentIndexChanged.connect(self.on_change)

    def on_change(self) -> None:
        self.cp.stances[self.enemy_cp.id] = self.currentData()
