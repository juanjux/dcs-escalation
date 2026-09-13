"""How he is: morale this week, hardening from everything before it, and his friends.

Morale and hardening share one caption row because they are meant to be read as a
pair -- the first moves every turn, the second never comes off. A pilot who is not
active has no morale worth showing, so his column is the same column with that card
missing and the rest frozen.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from game.squadrons import friendship
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot
from game.squadrons.squadron import Squadron
from qt_ui.widgets.cards import caption, shrinkable
from qt_ui.widgets.controls import wrapped_tooltip
from qt_ui.widgets.pilotrow import MORALE_COLOURS
from qt_ui.windows.pilot.common import (
    ACCENT,
    AMBER,
    BAR_TRACK,
    EMPTY,
    GREEN,
    HEADING_BG,
    RED,
    TAN,
    TAN_DIMMED,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    Bands,
    Bar,
    Elided,
    Row,
    Stack,
    chip,
    label,
    panel,
    rich,
    stars,
)

#: How many of a pilot's ups and downs the log shows before it is asked for the rest.
LOG_PREVIEW = 8

#: The bar behind a friend's name, and the one behind what he thinks back.
HIS_BAR = ACCENT
THEIR_BAR = "#6E93B0"
BAR_WIDTH = 100

#: Two bands apart is where a friendship stops being a friendship and starts being one
#: man's opinion.
NOT_RETURNED_GAP = 2

DOT = "<span style='color:#4F6070'> · </span>"

QSETTINGS_LOG_OPEN = "pilotDialog/moraleLogOpen"


def _store() -> QSettings:
    """The same store the dialogs keep their geometry in."""
    return QSettings("DCS Retribution", "Qt UI")


# --- morale ----------------------------------------------------------------------


def morale_card(pilot: Pilot, squadron: Squadron) -> QWidget:
    """The band he is in, the whole scale, and what moved him last turn."""
    settings = squadron.settings
    state = morale_rules.morale_state(pilot.morale, settings)
    colour = MORALE_COLOURS.get(state.name, TEXT_TERTIARY)

    inner = QWidget()
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(10)
    inner.setLayout(column)

    head = QHBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    head.setSpacing(8)
    dot = QLabel()
    dot.setFixedSize(10, 10)
    dot.setStyleSheet(f"background: {colour}; border-radius: 5px;")
    head.addWidget(dot)
    head.addWidget(label(state.name, 18, colour, bold=True))
    head.addStretch()
    head.addWidget(label(str(pilot.morale), 13, TEXT_TERTIARY, monospace=True))
    column.addLayout(head)

    column.addWidget(_scale(pilot, settings))

    moved = pilot.morale - pilot.morale_last_turn
    since = (
        f"<span style='color:{GREEN if moved > 0 else RED}'>{moved:+d}</span>"
        f"<span style='color:{TEXT_LABEL}'> since last turn</span>"
        if moved
        else f"<span style='color:{TEXT_LABEL}'>steady since last turn</span>"
    )
    foot = QHBoxLayout()
    foot.setContentsMargins(0, 0, 0, 0)
    foot.setSpacing(8)
    foot.addWidget(rich(since, 11))
    foot.addStretch()
    above = _next_band(pilot.morale, settings)
    if above is not None:
        foot.addWidget(label(f"{above.name} at {above.floor}", 11, TEXT_LABEL))
    column.addLayout(foot)
    return panel(inner)


def _scale(pilot: Pilot, settings: object) -> Bands:
    """The bands from worst to best, with the one he is in lit."""
    states = list(reversed(morale_rules.morale_states(settings)))
    here = morale_rules.morale_state(pilot.morale, settings)
    colours = [MORALE_COLOURS.get(state.name, TEXT_TERTIARY) for state in states]
    current = next(
        (index for index, state in enumerate(states) if state.name == here.name), 0
    )
    return Bands(colours, current)


def _next_band(morale: int, settings: object) -> Optional[morale_rules.MoraleState]:
    """The band above the one he is in, or nothing at the top of the scale."""
    above = [
        state for state in morale_rules.morale_states(settings) if state.floor > morale
    ]
    return above[-1] if above else None


# --- hardening -------------------------------------------------------------------

HARDENING_TOOLTIP = (
    "Earned by turns spent Shaken or worse. Never decreases.\n\n"
    "It does not make him cheerful: he feels the knocks as often, they land softer, "
    "and he is likelier to walk away from a wreck. The price is that he keeps the "
    "next man at arm's length."
)


def hardening_card(pilot: Pilot, squadron: Squadron, wide: bool = False) -> QWidget:
    """What the bad weeks left behind, and what the three of them are worth."""
    settings = squadron.settings
    ceiling = hardening.ceiling(settings)
    ink = TAN if pilot.alive else TAN_DIMMED

    inner = QWidget()
    if wide:
        # For a pilot with no morale card beside it, one line instead of three.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(_hardening_figure(pilot, ceiling, ink))
        row.addWidget(Bar(_fraction(pilot, ceiling), ink), 1)
        row.addWidget(label("earned turn by turn, and never lost", 11, TEXT_LABEL))
        inner.setLayout(row)
        widget = panel(inner, margins=(14, 12, 14, 12))
        widget.setToolTip(wrapped_tooltip(HARDENING_TOOLTIP))
        return widget

    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(10)
    column.addWidget(_hardening_figure(pilot, ceiling, ink))
    column.addWidget(Bar(_fraction(pilot, ceiling), ink))
    column.addWidget(rich(_effects(pilot, settings), 11))
    column.addStretch()
    inner.setLayout(column)
    widget = panel(inner)
    widget.setToolTip(wrapped_tooltip(HARDENING_TOOLTIP))
    return widget


def _hardening_figure(pilot: Pilot, ceiling: int, ink: str) -> QLabel:
    return rich(
        f"<span style='color:{ink};font-weight:600'>{pilot.hardened}</span>"
        f"<span style='color:{TEXT_LABEL};font-size:11.5px'> / {ceiling}</span>",
        18,
    )


def _fraction(pilot: Pilot, ceiling: int) -> float:
    return pilot.hardened / ceiling if ceiling else 0.0


def _effects(pilot: Pilot, settings: object) -> str:
    """The three percentages, worked out rather than written down.

    A player who reads "-18 % friendship" understands why the veteran has fewer
    friends than the new arrival.
    """
    relief = hardening.morale_relief(pilot.hardened, settings) * 100
    survival = hardening.survival_bonus(pilot.hardened, settings) * 100
    damping = hardening.friendship_damping(pilot.hardened, settings) * 100
    return (
        f"<span style='color:{GREEN}'>−{relief:.0f} %</span>"
        f"<span style='color:{TEXT_LABEL}'> morale knocks</span><br>"
        f"<span style='color:{GREEN}'>+{survival:.0f} %</span>"
        f"<span style='color:{TEXT_LABEL}'> survival</span><br>"
        f"<span style='color:{RED}'>−{damping:.0f} %</span>"
        f"<span style='color:{TEXT_LABEL}'> friendship</span>"
    )


# --- what moved him --------------------------------------------------------------


class MoraleLog(QWidget):
    """The log as a disclosure: closed by default, and it remembers being opened."""

    def __init__(self, pilot: Pilot) -> None:
        super().__init__()
        self.entries = list(reversed(pilot.morale_log))
        self.showing_all = False

        self.stack = Stack()
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self.stack)
        self.setLayout(column)

        self.head = Row(height=30, fill=HEADING_BG, interactive=True)
        self.arrow = label("▸", 10, TEXT_TERTIARY)
        self.arrow.setFixedWidth(12)
        self.head.add(self.arrow)
        heading = label("WHAT MOVED IT", 11, TEXT_MUTED, bold=True)
        heading.setStyleSheet(heading.styleSheet() + " letter-spacing: 1px;")
        self.head.add(heading)
        self.count = label("", 11, EMPTY)
        self.head.add(self.count)
        self.head.stretch()
        self.more = rich("", 11)
        self.more.setOpenExternalLinks(False)
        self.more.linkActivated.connect(lambda _href: self.show_all())
        self.head.add(self.more)
        self.head.clicked.connect(self.toggle)
        self.stack.append(self.head)

        self.rows = [self._row(index) for index in range(len(self.entries))]
        for row in self.rows:
            row.setVisible(False)
            self.stack.append(row)
        if not self.entries:
            self.empty = Row(height=28)
            self.empty.add(label("Nothing has moved him yet", 12, EMPTY))
            self.empty.setVisible(False)
            self.stack.append(self.empty)
            self.rows.append(self.empty)

        self.open = _store().value(QSETTINGS_LOG_OPEN, False, type=bool)
        self._apply()

    def toggle(self) -> None:
        self.open = not self.open
        _store().setValue(QSETTINGS_LOG_OPEN, self.open)
        self._apply()

    def show_all(self) -> None:
        self.showing_all = True
        self._apply()

    def _apply(self) -> None:
        shown = len(self.entries) if self.showing_all else LOG_PREVIEW
        for index, row in enumerate(self.rows):
            row.setVisible(self.open and index < shown)
        self.arrow.setText("▾" if self.open else "▸")
        total = len(self.entries)
        self.count.setText(
            f"last {min(shown, total)} of {total}"
            if self.open and total > shown
            else (f"{total} events" if total else "nothing yet")
        )
        self.more.setText(
            f"<a style='color:{ACCENT};text-decoration:none' href='#'>"
            f"Show all {total}</a>"
            if self.open and total > shown
            else ""
        )
        self.stack.refresh()

    def _row(self, index: int) -> Row:
        entry = self.entries[index]
        row = Row(height=28)
        row.body.setSpacing(0)
        turn = label(
            f"T{entry.turn}" if entry.turn >= 0 else "", 11, TEXT_MUTED, monospace=True
        )
        turn.setFixedWidth(38)
        row.add(turn)
        reason = label(entry.reason.capitalize(), 12, TEXT_BASE)
        row.add(shrinkable(reason))
        row.body.setStretchFactor(reason, 1)
        # A cheat leaves a row with no delta: it happened to him, but it did not move
        # him, and "+0" reads as an arithmetic error rather than as a fact.
        row.add(
            label(
                f"{entry.amount:+d}" if entry.amount else "",
                12,
                GREEN if entry.amount > 0 else RED,
                bold=True,
                monospace=True,
            )
        )
        return row


# --- friendships -----------------------------------------------------------------


class Friend:
    """One row of the friendships card, worked out before anything is drawn."""

    def __init__(
        self, pilot: Pilot, other: Pilot, same_squadron: bool, settings: object
    ):
        self.other = other
        self.same_squadron = same_squadron
        self.his = friendship.feeling(pilot, other)
        self.theirs = friendship.feeling(other, pilot)
        self.his_band = friendship.band(self.his, settings)
        self.their_band = friendship.band(self.theirs, settings)
        self.settings = settings

    @property
    def worth_showing(self) -> bool:
        """Above the Neutral band one way or the other.

        The band rather than the number: Neutral runs from 4 to 6, so a 5.5 is a man
        he has an opinion of no more than the campaign gave him.
        """
        neutral = friendship.band(friendship.FRIENDSHIP_START, self.settings).floor
        return self.his_band.floor > neutral or self.their_band.floor > neutral

    @property
    def line(self) -> str:
        """His band, and theirs, in plain English."""
        bands = friendship.bands(self.settings)
        names = [band.name for band in bands]
        gap = abs(names.index(self.his_band.name) - names.index(self.their_band.name))
        if self.his_band.name == self.their_band.name:
            back = f"<span style='color:{TEXT_TERTIARY}'>mutual</span>"
        elif gap >= NOT_RETURNED_GAP:
            back = (
                f"<span style='color:{TEXT_TERTIARY}'>and back: </span>"
                f"<span style='color:{AMBER}'>{self.their_band.name} — "
                "not returned</span>"
            )
        else:
            back = (
                f"<span style='color:{TEXT_TERTIARY}'>and back: "
                f"{self.their_band.name}</span>"
            )
        line = (
            f"<span style='color:{TEXT_TERTIARY}'>{self.his_band.name}</span>"
            f"{DOT}{back}"
        )
        if not self.same_squadron:
            line += f"{DOT}<span style='color:{TEXT_LABEL}'>another squadron</span>"
        return line


def friends_of(
    pilot: Pilot,
    wing: dict[UUID, tuple[Squadron, Pilot]],
    squadron: Squadron,
) -> list[Friend]:
    """Everyone he thinks anything of, strongest first.

    Both directions are looked at: a man who thinks nothing of somebody who thinks the
    world of him belongs on the list, because that is the interesting half.
    """
    settings = squadron.settings
    seen: dict[UUID, Friend] = {}
    for other_id in set(pilot.friendships) | _who_likes(pilot, wing):
        found = wing.get(other_id)
        if found is None or found[1] is pilot:
            continue
        their_squadron, other = found
        seen[other_id] = Friend(pilot, other, their_squadron is squadron, settings)
    friends = [friend for friend in seen.values() if friend.worth_showing]
    friends.sort(key=lambda friend: (-friend.his, friend.other.name))
    return friends


def _who_likes(pilot: Pilot, wing: dict[UUID, tuple[Squadron, Pilot]]) -> set[UUID]:
    return {
        other_id
        for other_id, (_squadron, other) in wing.items()
        if pilot.id in other.friendships
    }


def friendship_card(
    pilot: Pilot,
    squadron: Squadron,
    wing: dict[UUID, tuple[Squadron, Pilot]],
) -> tuple[QWidget, str]:
    """The rows, and the sentence under them explaining what the arrows mean."""
    friends = friends_of(pilot, wing, squadron)
    stack = Stack()
    if not friends:
        row = Row(height=44)
        row.add(label("No friendships yet", 12.5, EMPTY))
        stack.append(row)
        stack.refresh()
        return stack, ""

    alpha = 1.0 if pilot.alive else 0.7
    for friend in friends:
        stack.append(_friend_row(friend, squadron, alpha))
    stack.refresh()

    here = sum(
        1
        for their_squadron, other in wing.values()
        if their_squadron.location is squadron.location and other is not pilot
    )
    others = here - len(friends)
    note = "The top bar is what he feels, the bottom what they feel back."
    if others > 0:
        note += f" {others} others at {squadron.location.name} are Neutral or below."
    return stack, note


def _friend_row(friend: Friend, squadron: Squadron, alpha: float) -> Row:
    """Who he is on the left, what the two of them think on the right.

    The two halves are side by side rather than the arrows sitting on the name's line,
    because a pair of stacked bars is taller than one line of text and the digits
    beside them were being cut in half.
    """
    row = Row(height=44, margins=(14, 7, 14, 7), spacing=10)

    who = QVBoxLayout()
    who.setContentsMargins(0, 0, 0, 0)
    who.setSpacing(3)

    name_row = QHBoxLayout()
    name_row.setContentsMargins(0, 0, 0, 0)
    name_row.setSpacing(7)
    name_row.addWidget(
        stars(
            morale_rules.rank_level(squadron.pilot_skill(friend.other)),
            11,
            dimmed=not friend.other.alive,
        )
    )
    name_row.addWidget(Elided(friend.other.name, 13, TEXT_PRIMARY, bold=True))
    if friend.other.player:
        name_row.addWidget(chip("PLAYER", ACCENT, "#22384A"))
    name_row.addStretch()
    who.addLayout(name_row)
    who.addWidget(shrinkable(rich(friend.line, 11)))

    left = QWidget()
    left.setLayout(who)
    row.add(left)
    row.body.setStretchFactor(left, 1)

    arrows = QWidget()
    arrows.setLayout(_arrows(friend, alpha))
    row.add(arrows)
    return row


def _arrows(friend: Friend, alpha: float) -> QVBoxLayout:
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(5)
    column.addLayout(_arrow("→", friend.his, HIS_BAR, TEXT_SECONDARY, alpha))
    column.addLayout(_arrow("←", friend.theirs, THEIR_BAR, TEXT_TERTIARY, alpha))
    return column


def _arrow(mark: str, value: float, colour: str, ink: str, alpha: float) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(label(mark, 10, TEXT_MUTED))
    row.addWidget(
        Bar(
            value / friendship.FRIENDSHIP_MAX,
            colour,
            width=BAR_WIDTH,
            track=BAR_TRACK,
            alpha=alpha,
        )
    )
    figure = label(f"{value:.0f}", 11, ink, monospace=True)
    figure.setFixedWidth(18)
    figure.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(figure)
    return row


# --- the column ------------------------------------------------------------------


def state_column(
    pilot: Pilot,
    squadron: Squadron,
    wing: dict[UUID, tuple[Squadron, Pilot]],
) -> Optional[QVBoxLayout]:
    """Morale, hardening and friendships -- whichever of them this campaign has.

    Nothing at all when Live Pilots is switched off, and the dialog then gives the
    whole width to what he did, which is all there is to say about him.
    """
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(22)
    anything = False

    shows_morale = squadron.morale_in_play and pilot.has_morale and pilot.alive
    hardened_in_play = hardening.in_play(squadron.settings)

    if shows_morale:
        anything = True
        column.addWidget(_morale_captions(hardened_in_play))
        pair = QHBoxLayout()
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(10)
        pair.addWidget(morale_card(pilot, squadron), 1)
        if hardened_in_play:
            card = hardening_card(pilot, squadron)
            card.setFixedWidth(150)
            pair.addWidget(card)
        column.addLayout(pair)
        column.addWidget(MoraleLog(pilot))
    elif hardened_in_play:
        anything = True
        hint = (
            "morale is not shown for the fallen"
            if not pilot.alive
            else "the player's own morale is his own business"
        )
        column.addWidget(
            _captioned("Hardened", hardening_card(pilot, squadron, True), hint)
        )

    if squadron.friendship_in_play:
        anything = True
        card, note = friendship_card(pilot, squadron, wing)
        hint = "above Neutral · strongest first" if pilot.alive else "as they stood"
        holder = QWidget()
        inner = QVBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(10)
        inner.addWidget(caption("Friendships", hint))
        inner.addWidget(card)
        if note:
            explanation = label(note, 11, TEXT_MUTED)
            explanation.setWordWrap(True)
            inner.addWidget(explanation)
        holder.setLayout(inner)
        column.addWidget(holder)

    if not anything:
        return None
    column.addStretch()
    return column


def _morale_captions(with_hardening: bool) -> QWidget:
    """One caption row for the two cards: "this week" against "everything before it"."""
    holder = QWidget()
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    row.addWidget(caption("Morale", "this week"))
    row.addStretch()
    if with_hardening:
        row.addWidget(caption("Hardened", "everything before it"))
    holder.setLayout(row)
    return holder


def _captioned(name: str, content: QWidget, hint: str = "") -> QWidget:
    holder = QWidget()
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(10)
    column.addWidget(caption(name, hint))
    column.addWidget(content)
    holder.setLayout(column)
    return holder
