"""Who he is, and the three figures a player would brag about.

The name is the only large text. Beside it the rung he stands on and one chip saying
where he is -- active, wounded, on leave, killed, gone -- in the same six words the
roster uses, so the list and the dialog can never disagree about a pilot.

The figures are missions, kills and experience, and experience carries a bar to the
next rank because rank is derived from it and this is the only place in the program
where that relationship is visible.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.dcs.skills import SKILL_LADDER, experience_for_skill
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot, PilotStatus
from game.squadrons.pilotranks import rank_for_skill
from game.squadrons.squadron import Squadron
from qt_ui.uiconstants import AIRCRAFT_ICONS
from qt_ui.widgets.cards import make_transparent, shrinkable_widget
from qt_ui.windows.pilot.common import (
    ACCENT,
    AMBER,
    GREEN,
    LINE,
    PANEL,
    RED,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    Bar,
    Clickable,
    Elided,
    chip,
    label,
    rich,
    stars,
)

HEADER_HEIGHT = 104
NAME_LIVING = "#FFFFFF"
NAME_GONE = TEXT_BASE

PLAYER_CHIP_FILL = "#22384A"

#: What each fate is called, and the two colours it is called it in. The six the roster
#: paints, so a pilot who reads as WOUNDED in the list cannot read as ACTIVE here.
FATE_CHIPS: dict[PilotStatus, tuple[str, str, str]] = {
    PilotStatus.Active: ("ACTIVE", GREEN, "#23372D"),
    PilotStatus.Wounded: ("WOUNDED", "#C08A72", "#3B2D21"),
    PilotStatus.OnLeave: ("ON LEAVE", ACCENT, PLAYER_CHIP_FILL),
    PilotStatus.Dead: ("KIA", RED, "#3B2523"),
    PilotStatus.Deserted: ("DESERTED", AMBER, "#3B2D21"),
    PilotStatus.Discharged: ("DISCHARGED", "#9FADB9", ""),
}

XP_BAR_WIDTH = 360


def fate_of(pilot: Pilot) -> tuple[str, str, str]:
    """The chip, with the number that makes it worth reading.

    "Wounded" on its own is a colour; what a player wants to know is how long, and for
    a dead man, when.
    """
    words, ink, fill = FATE_CHIPS.get(
        pilot.status, (str(pilot.status.value).upper(), TEXT_LABEL, "")
    )
    if pilot.status is PilotStatus.Wounded and pilot.wounded_turns:
        words = f"{words} · {pilot.wounded_turns} TURNS"
    elif pilot.status is PilotStatus.OnLeave and pilot.leave_turns:
        words = f"{words} · {pilot.leave_turns} TURNS"
    elif pilot.status is PilotStatus.Dead and pilot.record.killed_by is not None:
        turn = pilot.record.killed_by.turn
        if turn:
            words = f"{words} · TURN {turn}"
    return words, ink, fill


def next_rung(squadron: Squadron, pilot: Pilot) -> tuple[Optional[str], int, int]:
    """The rank above him, what it costs, and what the one he holds cost.

    Nothing at the top of the ladder, and nothing at all when experience does not
    decide rank in this campaign -- a bar towards a promotion that cannot happen is
    worse than no bar.
    """
    settings = squadron.settings
    if not settings.live_pilots_enabled or not settings.ai_pilot_levelling:
        return None, 0, 0
    level = morale_rules.rank_level(squadron.pilot_skill(pilot))
    if level >= len(SKILL_LADDER):
        return None, 0, 0
    held = experience_for_skill(SKILL_LADDER[level - 1], settings)
    skill = SKILL_LADDER[level]
    rank = rank_for_skill(skill, _ladder_of(squadron))
    return rank.abbreviation, experience_for_skill(skill, settings), held


def _ladder_of(squadron: Squadron) -> tuple:
    """The rank names this squadron promotes through.

    Read back off the squadron rather than rebuilt: it is the one that knows whether
    the campaign is using national names, the skill levels or the player's own.
    """
    # pilot_rank builds the ladder for the pilot it is given, so one throwaway pilot at
    # each rung would be the only other way to ask.
    from game.squadrons.pilotranks import ranks_for

    return ranks_for(
        squadron.settings.live_pilots_rank_names,
        squadron.country,
        (
            (
                squadron.settings.live_pilots_rank_cadet_short,
                squadron.settings.live_pilots_rank_cadet_full,
            ),
            (
                squadron.settings.live_pilots_rank_average_short,
                squadron.settings.live_pilots_rank_average_full,
            ),
            (
                squadron.settings.live_pilots_rank_good_short,
                squadron.settings.live_pilots_rank_good_full,
            ),
            (
                squadron.settings.live_pilots_rank_high_short,
                squadron.settings.live_pilots_rank_high_full,
            ),
            (
                squadron.settings.live_pilots_rank_excellent_short,
                squadron.settings.live_pilots_rank_excellent_full,
            ),
        ),
    )


def _dot() -> QLabel:
    """The separator between the pieces of the line under the name."""
    return label("·", 12.5, "#4F6070")


def figure(caption: str, value: QWidget, hint: str = "") -> QWidget:
    """One of the three: its name above it, its footnote below, all right-aligned.

    The footnote is under the figure rather than beside it. Beside it is what the
    design drew and what reads best, but three figures at 26 px and a sentence next to
    one of them is wider than the header has, and the first thing a row that wide
    takes it out of is the pilot's own name.
    """
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(4)

    name = label(caption.upper(), 10.5, TEXT_MUTED, bold=True)
    name.setStyleSheet(name.styleSheet() + " letter-spacing: 1px;")
    column.addWidget(name, alignment=Qt.AlignmentFlag.AlignRight)
    column.addWidget(value, alignment=Qt.AlignmentFlag.AlignRight)
    if hint:
        column.addWidget(
            label(hint, 11.5, TEXT_LABEL), alignment=Qt.AlignmentFlag.AlignRight
        )
    column.addStretch()

    holder = QWidget()
    make_transparent(holder)
    holder.setLayout(column)
    return holder


class PilotHeader(QWidget):
    """The top of the dialog: who, then how much."""

    def __init__(self, pilot: Pilot, squadron: Squadron) -> None:
        super().__init__()
        self.pilot = pilot
        self.squadron = squadron
        self.living = pilot.status is PilotStatus.Active

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("pilotHeader")
        self.setStyleSheet(
            f"#pilotHeader {{ background: {PANEL};"
            f" border-bottom: 1px solid {LINE}; }}"
        )
        self.setFixedHeight(HEADER_HEIGHT)

        column = QVBoxLayout()
        column.setContentsMargins(20, 16, 20, 12)
        column.setSpacing(6)
        self.setLayout(column)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(22)
        top.addLayout(self._identity(), 1)
        for cell in self._figures():
            top.addWidget(cell, alignment=Qt.AlignmentFlag.AlignTop)
        column.addLayout(top, 1)
        column.addLayout(self._experience_bar())

    # -- who he is ------------------------------------------------------------

    def _identity(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        title = QHBoxLayout()
        title.setContentsMargins(0, 0, 0, 0)
        title.setSpacing(10)
        title.addWidget(
            Elided(self.pilot.name, 26, NAME_LIVING if self.living else NAME_GONE, True)
        )

        rung = QHBoxLayout()
        rung.setContentsMargins(0, 0, 0, 0)
        rung.setSpacing(7)
        rung.addWidget(stars(self._level(), 13, dimmed=not self.living))
        rank = self.squadron.pilot_rank(self.pilot)
        if rank is not None:
            rung.addWidget(
                Elided(rank.name, 14, TEXT_BASE if self.living else "#9FADB9")
            )
        title.addLayout(rung)

        if self.pilot.player:
            title.addWidget(chip("PLAYER", ACCENT, PLAYER_CHIP_FILL))
        words, ink, fill = fate_of(self.pilot)
        title.addWidget(chip(words, ink, fill, outline=not fill))
        title.addStretch()
        column.addLayout(title)

        column.addLayout(self._where())
        column.addStretch()
        return column

    def _level(self) -> int:
        return morale_rules.rank_level(self.squadron.pilot_skill(self.pilot))

    def _where(self) -> QHBoxLayout:
        """What he flies, who with, and from where. The squadron knows all of it.

        Separate labels rather than one line of rich text with a link in it: a link
        inside a label that has been told to give up its width is a small target that
        does not always take the press, and a squadron you can open should look like
        something you can press.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        banner = self._banner()
        if banner is not None:
            row.addWidget(banner)

        line = QWidget()
        make_transparent(line)
        pieces = QHBoxLayout()
        pieces.setContentsMargins(0, 0, 0, 0)
        pieces.setSpacing(6)
        line.setLayout(pieces)

        pieces.addWidget(
            label(self.squadron.aircraft.display_name, 12.5, TEXT_SECONDARY)
        )
        pieces.addWidget(_dot())

        self.squadron_link = Clickable(self.squadron.name, 12.5, ACCENT)
        self.squadron_link.setToolTip("Open the Air Wing")
        self.squadron_link.clicked.connect(lambda: open_air_wing(self))
        pieces.addWidget(self.squadron_link)

        pieces.addWidget(_dot())
        pieces.addWidget(label(self.squadron.location.name, 12.5, TEXT_TERTIARY))
        if self.living or self.pilot.player:
            pieces.addWidget(_dot())
            pieces.addWidget(
                label("PLAYER" if self.pilot.player else "AI", 12.5, TEXT_TERTIARY)
            )
        pieces.addStretch()

        row.addWidget(shrinkable_widget(line), 1)
        return row

    def _banner(self) -> Optional[QLabel]:
        icon = AIRCRAFT_ICONS.get(self.squadron.aircraft.dcs_id.replace("/", "_"))
        if icon is None:
            return None
        banner = QLabel()
        banner.setPixmap(icon)
        banner.setFixedSize(91, 24)
        banner.setScaledContents(True)
        if not self.living:
            # Half-lit, the way the roll of the fallen dims everything about a man
            # who is not coming back.
            banner.setStyleSheet("background: transparent; border: none;")
            effect = banner.graphicsEffect()
            if effect is None:
                from PySide6.QtWidgets import QGraphicsOpacityEffect

                opacity = QGraphicsOpacityEffect(banner)
                opacity.setOpacity(0.5)
                banner.setGraphicsEffect(opacity)
        return banner

    # -- what he has to show for it -------------------------------------------

    def _figures(self) -> list[QWidget]:
        record = self.pilot.record
        ink = TEXT_PRIMARY if self.living else TEXT_BASE

        flown = label(str(record.missions_flown), 26, ink, True, monospace=True)
        kills = rich(
            f"<span style='color:{ink}'>{record.total_air_kills}</span>"
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'> air </span>"
            f"<span style='color:{ink}'>{record.total_ground_kills}</span>"
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'> ground</span>",
            26,
        )
        kills.setFont(flown.font())
        kills.setStyleSheet("background: transparent; border: none;")

        # Flown and completed differ by how often he was shot down, which is the more
        # interesting of the two and is worth the line.
        flew = record.missions_flown
        came_back = record.missions_completed
        return [
            figure(
                "Missions",
                flown,
                f"{came_back} came home" if came_back != flew else "",
            ),
            figure("Kills", kills),
            figure("XP", self._experience(ink), self._to_next()),
        ]

    def _to_next(self) -> str:
        name, price, _held = next_rung(self.squadron, self.pilot)
        return "" if name is None else f"{price:,} to {name}"

    def _experience(self, ink: str) -> QWidget:
        return label(f"{self.pilot.record.xp:,}", 26, ink, True, monospace=True)

    def _experience_bar(self) -> QHBoxLayout:
        """How far along he is towards the next rank, or nothing at the top."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        name, price, held = next_rung(self.squadron, self.pilot)
        if name is None or not self.living or price <= held:
            return row
        earned = self.pilot.record.xp - held
        row.addWidget(
            Bar(earned / (price - held), "#E0C070", width=XP_BAR_WIDTH, height=4)
        )
        return row


def open_air_wing(widget: QWidget) -> None:
    """The Air Wing dialog, or the one already open brought to the front.

    Asked of the main window's top panel rather than built here: that is the thing
    that keeps there being exactly one Air Wing window however many times it is asked
    for, and a second one showing the same roster is a bug players have reported
    before.
    """
    node: Optional[QWidget] = widget
    while node is not None:
        panel = getattr(node, "top_panel", None)
        if panel is not None and hasattr(panel, "open_air_wing"):
            panel.open_air_wing()
            return
        node = node.parentWidget()

    # Opened from somewhere with no main window above it -- the command palette, a
    # test. The application has one all the same.
    for window in QApplication.topLevelWidgets():
        panel = getattr(window, "top_panel", None)
        if panel is not None and hasattr(panel, "open_air_wing"):
            panel.open_air_wing()
            return
