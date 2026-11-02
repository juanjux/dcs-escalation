"""The leave requests dialog.

Shown once at the end of a turn, after the debriefing, when any pilot has asked. Granting
leave costs the pilot for the turns granted; refusing costs him morale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QStyleOptionButton,
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


class _GrantAllCheckBox(QCheckBox):
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.checkState() != Qt.CheckState.PartiallyChecked:
            return
        # Paint the dash directly rather than loading a stylesheet SVG image.
        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, option, self
        )
        painter = QPainter(self)
        try:
            painter.fillRect(indicator, QColor("#83a56a"))
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(
                indicator.left() + 3,
                indicator.center().y(),
                indicator.right() - 3,
                indicator.center().y(),
            )
        finally:
            painter.end()


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
    cover: QLabel
    cells: list[QWidget] = field(default_factory=list)
    cover_explanation: str = ""

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
            cell.setToolTip(
                "\n\n".join(filter(None, (text, self.cover_explanation)))
                if cell is self.cover
                else text
            )


class LeaveRequestsDialog(QDialog):
    def __init__(self, game: "Game", requests: list[tuple["Squadron", Pilot]]) -> None:
        super().__init__()
        self.game = game
        self.requests = requests
        self.rows: list[_Row] = []
        self.selected: Optional[int] = None
        self.grant_all = _GrantAllCheckBox("Grant all")
        self.grant_all.setTristate(True)
        self.grant_all.setStyleSheet(
            "QCheckBox::indicator:indeterminate { image: none; }"
        )
        self.grant_all.setToolTip(
            "Check or clear Grant for every request. Decisions apply only when "
            "Answer them is pressed. Defaults keep at least one pilot per aircraft; "
            "manual grants may leave aircraft without pilots."
        )

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
                "back steadier. Refuse and they take it badly.<br>"
                "Requests are preselected while enough pilots remain for every "
                "aircraft, with the lowest-morale pilots first." + hint
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
            if column == COLUMNS - 1:
                make_transparent(self.grant_all)
                grid.addWidget(self.grant_all, 0, column)
            else:
                grid.addWidget(QLabel(f"<b>{heading}</b>"), 0, column)

        for row, (squadron, pilot) in enumerate(requests, start=1):
            # First, so everything else is drawn over it rather than under it.
            backdrop = QFrame()
            backdrop.setObjectName(f"leaveRow{row}")
            backdrop.setFrameShape(QFrame.Shape.NoFrame)
            grid.addWidget(backdrop, row, 0, 1, COLUMNS)

            rank = squadron.pilot_rank(pilot)
            name = pilot.name if rank is None else f"{rank.abbreviation} {pilot.name}"
            cells: list[QWidget] = [
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

            cover = QLabel()
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
            make_transparent(grant)
            grid.addWidget(grant, row, 6, Qt.AlignmentFlag.AlignCenter)

            self.rows.append(
                _Row(squadron, pilot, grant, turns, backdrop, cover, cells)
            )
            grant.toggled.connect(self._sync_grant_all)

        for row in sorted(self.rows, key=lambda row: row.pilot.morale):
            if self._remaining_pilots(row.squadron) > row.squadron.owned_aircraft:
                with QSignalBlocker(row.grant):
                    row.grant.setChecked(True)
        self.grant_all.stateChanged.connect(self._set_all_grants)
        self.grant_all.setEnabled(bool(self.rows))
        self._sync_grant_all()

        # The squadron name is the one that varies; everything else is a short word.
        grid.setColumnStretch(1, 1)

        apply_button = QPushButton("Answer them")
        apply_button.clicked.connect(self.answer)
        outer.addWidget(apply_button)

    def _set_all_grants(self, state: int) -> None:
        checked = state != Qt.CheckState.Unchecked.value
        for row in self.rows:
            with QSignalBlocker(row.grant):
                row.grant.setChecked(checked)
        self._sync_grant_all()

    def _sync_grant_all(self) -> None:
        checked = sum(row.grant.isChecked() for row in self.rows)
        state = Qt.CheckState.Unchecked
        if checked:
            state = (
                Qt.CheckState.Checked
                if checked == len(self.rows)
                else Qt.CheckState.PartiallyChecked
            )
        with QSignalBlocker(self.grant_all):
            self.grant_all.setCheckState(state)
        self._refresh_cover()

    def _remaining_pilots(self, squadron: Squadron) -> int:
        # Pending requests still count as present unless their Grant is checked.
        granted = {
            id(row.pilot)
            for row in self.rows
            if row.squadron is squadron and row.grant.isChecked()
        }
        return sum(
            1
            for pilot in squadron.current_roster
            if pilot.alive
            and not pilot.wounded
            and not pilot.on_leave
            and id(pilot) not in granted
        )

    def _refresh_cover(self) -> None:
        for row in self.rows:
            spare = self._remaining_pilots(row.squadron)
            aircraft = row.squadron.owned_aircraft
            row.cover.setText(f"{spare} free · {aircraft} aircraft")
            row.cover_explanation = (
                "Pilots remaining after all checked requests in this squadron. "
                "The aircraft total is unchanged."
            )
            if spare < aircraft:
                row.cover.setText(f"<b>{spare} free</b> · {aircraft} aircraft")
                row.cover_explanation += (
                    " These grants leave fewer pilots than airframes: some aircraft "
                    "will sit on the ground."
                )
            row.cover.setToolTip(row.cover_explanation)
        if self.selected is not None:
            self.select(self.selected)

    # --- picking a man out --------------------------------------------------

    @property
    def friendship_in_play(self) -> bool:
        return any(
            squadron.friendship_in_play for squadron, _ in self.requests
        ) and bool(self.requests)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """A click anywhere on a row selects that row.

        The cells are labels and do not take mouse events, so the press arrives at the
        body they sit in and the row is worked out from where it landed. The check box
        and the spinner take their own clicks.

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

        The bonus for leave taken in company applies within a squadron, so a close
        friend from another squadron buys nothing -- which the colour alone would not
        say.

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
