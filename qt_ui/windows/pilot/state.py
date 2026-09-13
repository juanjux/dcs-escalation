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
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from game.squadrons import friendship
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot
from game.squadrons.squadron import Squadron
from qt_ui.widgets.cards import make_transparent, shrinkable
from qt_ui.widgets.controls import wrapped_tooltip
from qt_ui.widgets.pilotrow import MORALE_COLOURS, affinity_tint
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
    CAPTION_GAP,
    Clickable,
    Elided,
    Row,
    Stack,
    captioned,
    chip,
    heading,
    label,
    panel,
    rich,
    stars,
)

#: How many men the relationships card holds. Everybody he has ever shared a base
#: with is a hundred rows of nothing; the ten he feels most strongly about is the
#: answer to the question being asked.
SHOWN = 10

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
    # The same shape as the figure in the card beside it: a number is worth more with
    # the top of its scale next to it.
    head.addWidget(
        rich(
            f"<span style='color:{TEXT_SECONDARY}'>{pilot.morale}</span>"
            f"<span style='color:{TEXT_LABEL};font-size:11.5px'>"
            f" / {morale_rules.MORALE_MAX}</span>",
            13,
        )
    )
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
    "Experience of bad weeks. He gains a point for every turn spent Shaken or"
    " worse, and never loses any."
    "\n\n"
    "The percentages are what those points are worth: morale hits land softer,"
    " he is likelier to survive being shot down, and he makes friends more"
    " slowly."
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

    A player who sees "-18 % friendship" understands why the veteran has fewer
    friends than the new arrival. A pilot who has been through nothing yet says so
    instead of saying "-0 %" three times.
    """
    relief = hardening.morale_relief(pilot.hardened, settings) * 100
    survival = hardening.survival_bonus(pilot.hardened, settings) * 100
    damping = hardening.friendship_damping(pilot.hardened, settings) * 100
    if not pilot.hardened:
        return (
            f"<span style='color:{TEXT_LABEL}'>Nothing yet. Every turn spent"
            " Shaken or worse earns a point.</span>"
        )
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
        heading = label("MORALE EVENTS", 11, TEXT_MUTED, bold=True)
        heading.setStyleSheet(heading.styleSheet() + " letter-spacing: 1px;")
        self.head.add(heading)
        self.count = label("", 11, EMPTY)
        self.head.add(self.count)
        self.head.stretch()
        self.more = Clickable("", 11)
        self.more.clicked.connect(self.show_all)
        self.more.setVisible(False)
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
        """Every event, or back to the recent ones. Never a way of shutting the card:
        the row it sits on toggles, and a press meant for this must not reach it."""
        self.showing_all = not self.showing_all
        self.open = True
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
        offered = self.open and total > LOG_PREVIEW
        self.more.setText(
            f"Show the last {LOG_PREVIEW}" if self.showing_all else f"Show all {total}"
        )
        self.more.setVisible(offered)
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
    def strength(self) -> float:
        """How far this pair is from where every pair starts, either way round.

        What decides whether the row is worth the space. Warm and cold both count:
        a man he cannot stand costs the flight what a friend earns it.
        """
        return max(
            abs(self.his - friendship.FRIENDSHIP_START),
            abs(self.theirs - friendship.FRIENDSHIP_START),
        )

    @property
    def tint(self) -> str:
        """The wash the pilot lists put behind this pair, as a stylesheet colour.

        The same one, so a player who has learnt the colour in the roster reads it
        here without being told.
        """
        colour = affinity_tint(self.his, settings=self.settings)
        if colour is None:
            return ""
        return (
            f"rgba({colour.red()}, {colour.green()}, {colour.blue()},"
            f" {colour.alpha() / 255:.3f})"
        )

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
    # The strongest opinions he holds, and then best to worst. Two passes because
    # they answer different questions: which rows are worth the card, and in what
    # order a player reads them. Filtering by band instead left a man whose whole
    # squadron is still Neutral -- the player's own pilot, most of a first campaign --
    # with an empty card, which is not what "no strong feelings either way" should
    # look like.
    friends = sorted(seen.values(), key=lambda friend: -friend.strength)[:SHOWN]
    friends.sort(key=lambda friend: (-friend.his, -friend.theirs, friend.other.name))
    return friends


def _who_likes(pilot: Pilot, wing: dict[UUID, tuple[Squadron, Pilot]]) -> set[UUID]:
    return {
        other_id
        for other_id, (_squadron, other) in wing.items()
        if pilot.id in other.friendships
    }


def relationship_card(
    pilot: Pilot,
    squadron: Squadron,
    wing: dict[UUID, tuple[Squadron, Pilot]],
) -> tuple[QWidget, str]:
    """The rows, and the sentence under them explaining what the arrows mean."""
    friends = friends_of(pilot, wing, squadron)
    stack = Stack()
    if not friends:
        row = Row(height=44)
        row.add(label("Nobody he has an opinion of yet", 12.5, EMPTY))
        stack.append(row)
        stack.refresh()
        return stack, ""

    alpha = 1.0 if pilot.alive else 0.7
    for friend in friends:
        stack.append(_friend_row(friend, squadron, alpha))
    stack.refresh()

    others = _known_to(pilot, wing) - len(friends)
    note = "The top bar is what he feels, the bottom what they feel back."
    if others > 0:
        note += f" {others} others he knows are closer to Neutral than these."
    return stack, note


def _known_to(pilot: Pilot, wing: dict[UUID, tuple[Squadron, Pilot]]) -> int:
    """How many men he has any opinion of, or who have one of him."""
    return len(
        {other_id for other_id in pilot.friendships if other_id in wing}
        | _who_likes(pilot, wing)
    )


def _friend_row(friend: Friend, squadron: Squadron, alpha: float) -> Row:
    """Who he is on the left, what the two of them think on the right.

    The two halves are side by side rather than the arrows sitting on the name's line,
    because a pair of stacked bars is taller than one line of text and the digits
    beside them were being cut in half.
    """
    row = Row(height=50, margins=(10, 4, 14, 4), spacing=10)

    who = QVBoxLayout()
    # The wash goes behind the man rather than across the whole row: a band of colour
    # running out under the bars reads as a highlighted line, and the colour is about
    # him.
    who.setContentsMargins(8, 5, 8, 5)
    who.setSpacing(2)

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
    if friend.tint:
        left.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left.setObjectName(f"pilotTile{id(friend)}")
        left.setStyleSheet(
            f"#{left.objectName()} {{ background: {friend.tint};"
            " border-radius: 3px; }"
        )
    else:
        make_transparent(left)
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


MORALE_TOOLTIP = (
    "How he is feeling, 0 to 100, and which band that puts him in. Missions,"
    " kills, promotions, losses and leave all move it."
    "\n\n"
    "It matters: a high band makes him fly better in the mission and a low one"
    " makes him fly worse. At the bottom of the scale he refuses to fly, and he"
    " may desert."
)

RELATIONSHIPS_TOOLTIP = (
    "What he thinks of the other pilots, 0 to 10, and what each of them thinks of him."
    " The two are separate: they do not have to agree."
    "\n\n"
    "A flight of pilots who get on performs better and looks after its own when one"
    " is shot down. Friends ask for leave together, and losing one costs more morale"
    " than losing a stranger."
)


def state_column(
    pilot: Pilot,
    squadron: Squadron,
    wing: dict[UUID, tuple[Squadron, Pilot]],
) -> Optional[QVBoxLayout]:
    """Morale, hardening and relationships -- whichever of them this campaign has.

    Nothing at all when Live Pilots is switched off, and the dialog then gives
    the whole width to what he did, which is all there is to say about him.
    """
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(22)
    anything = False

    shows_morale = squadron.morale_in_play and pilot.has_morale and pilot.alive
    hardened_in_play = hardening.in_play(squadron.settings)

    if shows_morale:
        anything = True
        pair = QWidget()
        make_transparent(pair)
        # Pinned to what it asks for: given room to grow, the two cards share it out
        # between themselves and stand a head taller than anything they say.
        pair.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        both = QVBoxLayout()
        both.setContentsMargins(0, 0, 0, 0)
        # The heading and its cards are one thing, the way captioned() makes one of
        # every other heading: laid straight into the column they were a whole
        # section's gap apart from it.
        both.setSpacing(CAPTION_GAP)
        both.addWidget(_morale_headings(hardened_in_play))

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)
        cards.addWidget(morale_card(pilot, squadron), 1)
        if hardened_in_play:
            card = hardening_card(pilot, squadron)
            card.setFixedWidth(150)
            cards.addWidget(card)
        both.addLayout(cards)
        pair.setLayout(both)

        column.addWidget(pair)
        column.addWidget(MoraleLog(pilot))
    elif hardened_in_play:
        anything = True
        # The one hint kept: a card that is not there needs saying, and this is
        # where morale would have been.
        hint = (
            "morale is not shown for the fallen"
            if not pilot.alive
            else "the player's own morale is his own business"
        )
        column.addWidget(
            captioned(
                "Hardened",
                hardening_card(pilot, squadron, True),
                hint,
                tooltip=HARDENING_TOOLTIP,
            )
        )

    if not anything:
        return None
    column.addStretch()
    return column


def _morale_headings(with_hardening: bool) -> QWidget:
    """One heading row for the two cards: they are meant to be read together."""
    holder = QWidget()
    make_transparent(holder)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    row.addWidget(heading("Morale", tooltip=MORALE_TOOLTIP))
    row.addStretch()
    if with_hardening:
        row.addWidget(heading("Hardened", tooltip=HARDENING_TOOLTIP))
    holder.setLayout(row)
    return holder


def relationships_section(
    pilot: Pilot,
    squadron: Squadron,
    wing: dict[UUID, tuple[Squadron, Pilot]],
) -> Optional[QWidget]:
    """The whole card with its heading and the line that explains the arrows.

    It lives in the wider of the two columns: the names, the bands and "and back:"
    are a sentence, and a sentence in a fixed 400 px is a sentence with its end cut
    off -- while the cards it used to sit under are figures, which are not.
    """
    if not squadron.friendship_in_play:
        return None
    card, note = relationship_card(pilot, squadron, wing)
    holder = QWidget()
    make_transparent(holder)
    inner = QVBoxLayout()
    inner.setContentsMargins(0, 0, 0, 0)
    inner.setSpacing(CAPTION_GAP)
    inner.addWidget(heading("Relationships", tooltip=RELATIONSHIPS_TOOLTIP))
    inner.addWidget(card)
    if note:
        explanation = label(note, 11, TEXT_MUTED)
        explanation.setWordWrap(True)
        inner.addWidget(explanation)
    holder.setLayout(inner)
    return holder
