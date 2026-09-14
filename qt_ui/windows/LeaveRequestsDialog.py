"""The pilots who have asked for a rest, and your answer.

Shown once at the end of a turn, after the debriefing, when anybody asked. A pilot asks
more often the worse he is holding up, but a contented one asks now and then too. Saying
yes costs you the man for the turns you grant; saying no costs him morale.

Clicking a row picks a man out, and the rest of the list colours itself by what they
make of him -- because leave is worth more taken in company, and the point of seeing it
here is to send friends off together rather than one at a time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from game.squadrons import friendship
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.pilotrow import SELECTED_FILL, affinity_tint

if TYPE_CHECKING:
    from game.game import Game
    from game.squadrons.squadron import Squadron

#: The columns a row spans, so its backdrop covers the lot.
COLUMNS = 7


def pending_leave_requests(game: "Game") -> list[tuple["Squadron", Pilot]]:
    """Everyone on the player's side waiting to be told yes or no."""
    requests: list[tuple[Squadron, Pilot]] = []
    for squadron in game.blue.air_wing.iter_squadrons():
        for pilot in squadron.pilots_asking_for_leave():
            requests.append((squadron, pilot))
    # The one in the worst state first: he is the one the answer matters most to.
    requests.sort(key=lambda pair: pair[1].morale)
    return requests


@dataclass
class _Row:
    """One request, and everything the dialog needs to paint or read it."""

    squadron: "Squadron"
    pilot: Pilot
    grant: QCheckBox
    turns: QSpinBox
    backdrop: QFrame
    cells: list[QWidget] = field(default_factory=list)

    def fill(self, colour: Optional[str]) -> None:
        name = self.backdrop.objectName()
        background = colour or "transparent"
        self.backdrop.setStyleSheet(
            f"QFrame#{name} {{ background-color: {background}; border: none; }}"
        )

    def explain(self, text: str) -> None:
        """The same words on every cell: a tooltip on the backdrop alone would never
        be seen, because the labels sit on top of it."""
        for cell in self.cells:
            cell.setToolTip(text)


class LeaveRequestsDialog(QDialog):
    def __init__(self, game: "Game", requests: list[tuple["Squadron", Pilot]]) -> None:
        super().__init__()
        self.game = game
        self.requests = requests
        self.rows: list[_Row] = []
        self.selected: Optional[int] = None

        self.setModal(True)
        self.setWindowTitle("Leave requests")
        self.setWindowIcon(QIcon("./resources/icon.png"))
        self.setMinimumWidth(940)

        outer = QVBoxLayout()
        self.setLayout(outer)
        hint = (
            "<br>Click a pilot to see who else here gets on with him: leave is worth "
            "more taken with the men he likes."
            if self.friendship_in_play
            else ""
        )
        outer.addWidget(
            QLabel(
                "<b>These pilots have asked for leave.</b><br>"
                "Grant it and they are off the roster for the turns you set, coming "
                "back steadier. Refuse and they take it badly." + hint
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.installEventFilter(self)
        self.body = body
        scroll.setWidget(body)
        grid = QGridLayout()
        body.setLayout(grid)
        outer.addWidget(scroll, 1)

        for column, heading in enumerate(
            (
                "Pilot",
                "Squadron",
                "Aircraft",
                "Morale",
                "Cover left",
                "Asked",
                "Grant",
            )
        ):
            grid.addWidget(QLabel(f"<b>{heading}</b>"), 0, column)

        for row, (squadron, pilot) in enumerate(requests, start=1):
            # First, so everything else is drawn over it rather than under it.
            backdrop = QFrame()
            backdrop.setObjectName(f"leaveRow{row}")
            backdrop.setFrameShape(QFrame.Shape.NoFrame)
            grid.addWidget(backdrop, row, 0, 1, COLUMNS)

            rank = squadron.pilot_rank(pilot)
            name = pilot.name if rank is None else f"{rank.abbreviation} {pilot.name}"
            cells = [
                QLabel(name),
                QLabel(str(squadron)),
                QLabel(str(squadron.aircraft)),
            ]

            state = morale_rules.morale_state(pilot.morale, self.game.settings)
            morale = QLabel(state.name)
            if state.severity:
                morale.setText(f"<b>{state.name}</b>")
                morale.setToolTip("He is close to being no use to you at all.")
            cells.append(morale)

            # Saying yes to two men costs a squadron of sixteen pilots and four
            # aircraft nothing, and one of ten and twelve a mission it cannot fly.
            spare = squadron.spare_pilots(excluding=pilot)
            aircraft = squadron.owned_aircraft
            cover = QLabel(f"{spare} free · {aircraft} aircraft")
            if spare < aircraft:
                cover.setText(f"<b>{spare} free</b> · {aircraft} aircraft")
                cover.setToolTip(
                    "Granting this leaves fewer pilots than airframes: something will "
                    "sit on the ground."
                )
            cells.append(cover)

            for column, cell in enumerate(cells):
                # Or the stylesheet's blanket background paints a box over the tint.
                make_transparent(cell)
                grid.addWidget(cell, row, column)

            # He asked for a number; the player may hand him less. The box opens on
            # what he asked for so saying yes is one click.
            asked = pilot.leave_turns_requested or morale_rules.DEFAULT_LEAVE_TURNS
            turns = QSpinBox()
            turns.setRange(1, morale_rules.MAX_LEAVE_TURNS)
            turns.setValue(min(asked, morale_rules.MAX_LEAVE_TURNS))
            turns.setToolTip(f"He asked for {asked}.")
            grid.addWidget(turns, row, 5)

            grant = QCheckBox()
            grant.setChecked(bool(state.severity))
            make_transparent(grant)
            grid.addWidget(grant, row, 6, Qt.AlignmentFlag.AlignCenter)

            self.rows.append(_Row(squadron, pilot, grant, turns, backdrop, cells))

        # The squadron name is the one that varies; everything else is a short word.
        grid.setColumnStretch(1, 1)

        apply_button = QPushButton("Answer them")
        apply_button.clicked.connect(self.answer)
        outer.addWidget(apply_button)

    # --- picking a man out --------------------------------------------------

    @property
    def friendship_in_play(self) -> bool:
        return any(
            squadron.friendship_in_play for squadron, _ in self.requests
        ) and bool(self.requests)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """A click anywhere on a row picks that row.

        The cells are labels, which do not take mouse events, so the press arrives at
        the body they sit in and the row is worked out from where it landed. The
        check box and the spinner take their own clicks, which is what should happen:
        answering a request is not the same act as looking at one.
        """
        if watched is self.body and event.type() == QEvent.Type.MouseButtonPress:
            assert isinstance(event, QMouseEvent)
            self.select_at(int(event.position().y()))
            return True
        return super().eventFilter(watched, event)

    def select_at(self, y: int) -> None:
        for index, row in enumerate(self.rows):
            geometry = row.backdrop.geometry()
            if geometry.top() <= y <= geometry.bottom():
                self.select(None if index == self.selected else index)
                return
        self.select(None)

    def select(self, index: Optional[int]) -> None:
        """Paint the list as it looks from where this man is standing."""
        self.selected = index
        if index is None or not self.friendship_in_play:
            for row in self.rows:
                row.fill(None)
                row.explain("")
            return

        chosen = self.rows[index]
        for position, row in enumerate(self.rows):
            if position == index:
                row.fill(SELECTED_FILL.name())
                row.explain(f"What the others here make of {chosen.pilot.name}.")
                continue
            row.fill(self._tint(chosen.pilot, row.pilot))
            row.explain(self._explanation(chosen, row))

    def _tint(self, chosen: Pilot, other: Pilot) -> Optional[str]:
        colour = affinity_tint(
            friendship.group_affinity(other, [chosen]),
            settings=self.game.settings,
        )
        if colour is None:
            return None
        return f"rgba({colour.red()},{colour.green()},{colour.blue()},{colour.alpha()})"

    def _explanation(self, chosen: _Row, other: _Row) -> str:
        """What the colour means, and whether it is worth anything here.

        The bonus for leave taken in company is a squadron's, so a man from another
        squadron can be the best friend he has and it will still buy nothing -- which
        is exactly the kind of thing a colour on its own would let you get wrong.
        """
        value = friendship.group_affinity(other.pilot, [chosen.pilot])
        band = friendship.band_name(value, self.game.settings)
        if other.squadron is not chosen.squadron:
            return (
                f"{band} with {chosen.pilot.name}, but a different squadron:"
                " leave together is worth nothing extra."
            )
        multiplier = friendship.leave_multiplier(
            friendship.feeling(other.pilot, chosen.pilot), self.game.settings
        )
        extra = round((multiplier - 1.0) * 100)
        if extra <= 0:
            return f"{band} with {chosen.pilot.name}."
        return (
            f"{band} with {chosen.pilot.name}: a week off at the same time is worth"
            f" {extra}% more to him."
        )

    # --- the answer ----------------------------------------------------------

    def answer(self) -> None:
        """Grant the ticked ones and refuse the rest. Unanswered is an answer."""
        turn = self.game.turn
        for row in self.rows:
            squadron, pilot = row.squadron, row.pilot
            pilot.wants_leave = False
            if row.grant.isChecked():
                try:
                    squadron.send_on_leave(pilot, row.turns.value(), turn)
                except RuntimeError:
                    logging.exception(f"Could not send {pilot.name} on leave")
                continue
            pilot.leave_turns_requested = 0
            pilot.move_morale(
                morale_rules.LEAVE_REFUSED,
                squadron.pilot_skill(pilot),
                self.game.settings,
                turn,
            )
            logging.info(f"{pilot.name} was refused leave")
        self.accept()
