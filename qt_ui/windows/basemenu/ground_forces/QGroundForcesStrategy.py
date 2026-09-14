"""What the units here do about each neighbour they share a front with.

It was a group box called "Frontline operations :" holding a bare base name and a
combo of enum constants, which named neither what the decision was about nor what
either side had to fight with. A stance is a decision about a specific enemy, so each
row names that enemy and shows the odds.
"""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.server import EventStream
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater import ControlPoint
from qt_ui.widgets.cards import HINT, card, carded, make_transparent, shrinkable
from qt_ui.widgets.controls import KEY, mono
from qt_ui.windows.airwingconfig.common import CHEAT_BG, CHEAT_BORDER, CHEAT_HEADER
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.basemenu.buylist import BRIGHT, QUIET
from qt_ui.windows.basemenu.ground_forces.QGroundForcesStrategySelector import (
    QGroundForcesStrategySelector,
)


class QGroundForcesStrategy(QWidget):
    def __init__(self, cp: ControlPoint, game: Game):
        super().__init__()
        self.cp = cp
        self.game = game

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(
            carded("Front lines", self._rows(), "stance per enemy neighbour")
        )
        self.setLayout(layout)

    def neighbours(self) -> list[ControlPoint]:
        """The enemy bases this one shares a front with."""
        return [
            other
            for other in self.cp.connected_points
            if other.captured != self.cp.captured and not other.captured.is_neutral
        ]

    def _rows(self) -> QWidget:
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)

        neighbours = self.neighbours()
        if not neighbours:
            nobody = QLabel("No front line here: this base has no enemy neighbour.")
            nobody.setStyleSheet(
                f"font-size: 11.5px; color: {HINT}; background: transparent;"
                " border: none;"
            )
            column.addWidget(shrinkable(nobody))
        for enemy in neighbours:
            column.addLayout(self._row(enemy))

        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(column)
        return holder

    def _row(self, enemy: ControlPoint) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(8)

        name = QLabel(f"→ {enemy.name}")
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {BRIGHT};"
            " background: transparent; border: none;"
        )
        heading.addWidget(name)
        heading.addStretch()

        odds = QLabel()
        odds.setFont(mono(12))
        odds.setStyleSheet(f"color: {KEY}; background: transparent; border: none;")
        odds.setText(f"{self.cp.base.total_armor} vs {enemy.base.total_armor}")
        heading.addWidget(odds)

        units = QLabel("units")
        units.setStyleSheet(
            f"font-size: 11px; color: {QUIET}; background: transparent; border: none;"
        )
        heading.addWidget(units)
        row.addLayout(heading)

        row.addWidget(QGroundForcesStrategySelector(self.cp, enemy))
        if self.game.settings.enable_frontline_cheats:
            row.addWidget(self._cheats(enemy))
        return row

    def _cheats(self, enemy: ControlPoint) -> QWidget:
        def move(advance: bool) -> Callable[[], None]:
            def cheat() -> None:
                self.cheat_alter_front_line(enemy, advance)

            return cheat

        line = QHBoxLayout()
        line.setContentsMargins(8, 4, 8, 4)
        line.setSpacing(6)

        tag = QLabel("CHEAT")
        tag.setStyleSheet(
            f"color: {CHEAT_HEADER}; font-size: 10px; font-weight: bold;"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        line.addWidget(tag)
        for label, advance in (("Advance", True), ("Retreat", False)):
            button = QPushButton(label)
            button.clicked.connect(move(advance))
            line.addWidget(button)
        line.addStretch()

        holder = card()
        holder.setStyleSheet(
            f"#{holder.objectName()} {{ background: {CHEAT_BG};"
            f" border: 1px solid {CHEAT_BORDER}; border-radius: 3px; }}"
        )
        holder.setLayout(line)
        return holder

    def cheat_alter_front_line(self, enemy_point: ControlPoint, advance: bool) -> None:
        amount = 0.2
        if not advance:
            amount *= -1
        self.cp.base.affect_strength(amount)
        enemy_point.base.affect_strength(-amount)
        front_line = self.cp.front_line_with(enemy_point)
        front_line.update_position()
        events = GameUpdateEvents().update_front_line(front_line)
        # Clear the ATO to replan missions affected by the front line.
        self.game.initialize_turn(events)
        EventStream.put_nowait(events)
        GameUpdateSignal.get_instance().updateGame(self.game)
