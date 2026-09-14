"""The amber strip: rename him, promote him, put him back on his feet.

One strip, always in the same place, in the colours the Air Wing Configuration cheat
header already uses. Rename and rank are always live; Heal and Revive light up only
when they would do something, so a player never presses one and wonders why nothing
happened.

The informative half of the dialog never changes with the setting. This is the whole
of what switching cheats on adds.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from game.dcs.skills import SKILL_LADDER, experience_for_skill
from game.squadrons.morale import MoraleLogEntry
from game.squadrons.pilot import Pilot, PilotStatus
from game.squadrons.pilotranks import rank_for_skill
from game.squadrons.squadron import Squadron
from qt_ui.rankstars import rank_stars_text
from qt_ui.windows.airwingconfig.common import (
    AMBER,
    CHEAT_BG,
    CHEAT_BORDER,
    CHEAT_CHIP_BG,
    CHEAT_HEADER,
    CHEAT_HEADER_LINE,
)
from qt_ui.windows.pilot.common import chip
from qt_ui.windows.pilot.header import _ladder_of

STRIP_HEIGHT = 52
NAME_WIDTH = 220
CONTROL_HEIGHT = 28

FIELD = (
    f"background: {CHEAT_BG}; color: #F2F7FA; border: 1px solid #5A4630;"
    " border-radius: 3px; padding: 0 8px; font-size: 12px;"
)
QUIET = "#9A7A55"

#: The revival of a man who is only gone because the player said so reads as a
#: reinstatement rather than a resurrection.
REINSTATED = (PilotStatus.Deserted, PilotStatus.Discharged)


def _button(text: str, enabled: bool, primary: bool) -> QPushButton:
    widget = QPushButton(text)
    widget.setFixedHeight(CONTROL_HEIGHT)
    widget.setEnabled(enabled)
    if enabled:
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
    fill, ink, border = (
        (AMBER, "#2A1F12", AMBER)
        if enabled and primary
        else (CHEAT_BG, "#D3DFE8" if enabled else "#7A6A4E", CHEAT_BORDER)
    )
    widget.setStyleSheet(
        f"QPushButton {{ background: {fill}; color: {ink};"
        f" border: 1px solid {border}; border-radius: 3px; padding: 0 12px;"
        " font-size: 12px; font-weight: 600; }"
        f"QPushButton:disabled {{ background: {CHEAT_BG}; color: #7A6A4E;"
        f" border-color: {CHEAT_BORDER}; }}"
    )
    return widget


class CheatStrip(QWidget):
    """What a player may do to a pilot that the campaign would not."""

    changed = Signal()

    def __init__(self, pilot: Pilot, squadron: Squadron) -> None:
        super().__init__()
        self.pilot = pilot
        self.squadron = squadron

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("pilotCheats")
        self.setStyleSheet(
            f"#pilotCheats {{ background: {CHEAT_HEADER};"
            f" border-bottom: 1px solid {CHEAT_HEADER_LINE}; }}"
        )
        self.setFixedHeight(STRIP_HEIGHT)

        row = QHBoxLayout()
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(10)
        self.setLayout(row)

        row.addWidget(chip("CHEAT", AMBER, CHEAT_CHIP_BG))
        row.addWidget(self._name_field())
        rank = self._rank_combo()
        if rank is not None:
            row.addWidget(rank)
            hint = chip("sets xp to the rank's floor", QUIET)
            hint.setStyleSheet(
                f"background: transparent; color: {QUIET}; border: none;"
                " font-size: 11px; font-weight: normal; letter-spacing: 0;"
            )
            row.addWidget(hint)
        row.addStretch()

        self.heal = _button("Heal", pilot.status is PilotStatus.Wounded, True)
        self.heal.clicked.connect(self._heal)
        row.addWidget(self.heal)

        revivable = not pilot.alive
        self.revive = _button(
            "Reinstate" if pilot.status in REINSTATED else "Revive", revivable, True
        )
        self.revive.clicked.connect(self._revive)
        row.addWidget(self.revive)

    # -- rename ---------------------------------------------------------------

    def _name_field(self) -> QLineEdit:
        field = QLineEdit(self.pilot.name)
        field.setFixedSize(NAME_WIDTH, CONTROL_HEIGHT)
        field.setPlaceholderText("rename")
        field.setStyleSheet(FIELD)
        field.editingFinished.connect(self._rename)
        self.name_field = field
        return field

    def _rename(self) -> None:
        name = self.name_field.text().strip()
        if not name or name == self.pilot.name:
            return
        self.pilot.name = name
        self.changed.emit()

    # -- rank -----------------------------------------------------------------

    def _rank_combo(self) -> Optional[QComboBox]:
        """The five rungs, or nothing when experience does not decide rank here."""
        settings = self.squadron.settings
        if not settings.live_pilots_enabled or not settings.ai_pilot_levelling:
            return None
        ladder = _ladder_of(self.squadron)
        combo = QComboBox()
        combo.setFixedHeight(CONTROL_HEIGHT)
        combo.setStyleSheet(FIELD + " QComboBox::drop-down { border: none; }")
        for level, skill in enumerate(SKILL_LADDER):
            rank = rank_for_skill(skill, ladder)
            combo.addItem(
                f"{rank_stars_text(level + 1)}  {rank.abbreviation}",
                experience_for_skill(skill, settings),
            )
        combo.setCurrentIndex(self._current_rung())
        combo.activated.connect(self._promote)
        self.rank_combo = combo
        return combo

    def _current_rung(self) -> int:
        try:
            return SKILL_LADDER.index(self.squadron.pilot_skill(self.pilot))
        except ValueError:
            return 0

    def _promote(self, index: int) -> None:
        """Rank is derived from experience, so the cheat writes the experience."""
        floor = self.rank_combo.itemData(index)
        if floor is None or floor == self.pilot.record.xp:
            return
        self.pilot.record.xp = int(floor)
        self.changed.emit()

    # -- putting him back on his feet -----------------------------------------

    def _heal(self) -> None:
        self.pilot.wounded_turns = 0
        self.pilot.wounded_on_turn = -1
        self.pilot.status = PilotStatus.Active
        self.squadron.joins_the_pool(self.pilot)
        self._note("Healed (cheat)")
        self.changed.emit()

    def _revive(self) -> None:
        word = "Reinstate" if self.pilot.status in REINSTATED else "Revive"
        answer = QMessageBox.question(
            self,
            f"{word} pilot",
            f"{word} {self.pilot.name}? He keeps his record and his log, and goes "
            f"back on the roster of {self.squadron}.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.pilot.status = PilotStatus.Active
        self.pilot.wounded_turns = 0
        self.pilot.wounded_on_turn = -1
        self.pilot.leave_turns = 0
        self.pilot.leave_on_turn = -1
        self.squadron.joins_the_pool(self.pilot)
        self._note(f"{word}d (cheat)")
        self.changed.emit()

    def _note(self, reason: str) -> None:
        """Say so in the log, with no delta: it is a thing that happened to him, and
        the log is what the dialog reads back."""
        if not self.pilot.has_morale:
            return
        self.pilot.morale_log.append(
            MoraleLogEntry(
                turn=-1,
                amount=0,
                reason=reason,
                morale_after=self.pilot.morale,
            )
        )
