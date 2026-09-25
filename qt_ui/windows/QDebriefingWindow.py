"""The debriefing window.

A fixed summary strip at the top, with the detail sections below it. Pilots come first:
aircraft can be replaced with money and a pilot record cannot, and it is the only section
that carries decisions into the dialogs this window chains on the way out.

The palette and the vocabulary (stars for a rank, a coloured dot for morale) are the Air
Wing's.
"""

from functools import partial
from typing import Any, Optional, Sequence

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from game.debriefingreport import DebriefingReport, LossCosts
from game.highcommand.wording import counted, money
from game.squadrons.experience import (
    MoraleShift,
    XP_AIR,
    XP_BUILDINGS,
    XP_COMPANY,
    XP_DAMAGE,
    XP_GROUND,
    XP_HELD_BACK,
    XP_LEARNING,
    XP_MISSION,
    XP_MORALE,
    XP_SHIPS,
    XP_WOUND,
    XpAward,
    PilotDeath,
    PilotPromotion,
    PilotWound,
    turns_phrase,
)
from game.squadrons.morale import morale_state
from game.theater import Player
from qt_ui.rankstars import (
    STAR_EMPTY,
    STAR_EMPTY_DIMMED,
    STAR_FILLED,
    STAR_FILLED_DIMMED,
    paint_rank_stars,
)
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

# --- the palette ------------------------------------------------------------

PAGE = "#2D3E50"
BAND = "#26343F"
CARD = "#14202B"
HEADER = "#1B2732"
LINE = "#1D2731"

TITLE = "#F2F7FA"
BODY = "#D3DFE8"
SUBDUED = "#B7C6D2"
MUTED = "#8E9DAA"
DIM = "#7C8B99"
CAPTION = "#6B7A87"
FAINT = "#4F6070"

OURS = "#D9645E"
THEIRS = "#86C39A"
WOUNDED = "#C08A72"
WOUNDED_DETAIL = "#8A6C5C"
UNHURT = "#5F8A6C"
ACCENT = "#8FC3F0"
AMBER = "#E0A86B"

#: The five groups of the pilots section, in the order they are read: the worst news
#: first, so a long list of promotions never buries a death.
GROUP_COLOURS = {
    "KILLED IN ACTION": OURS,
    "SHOT DOWN & RECOVERED": AMBER,
    "WOUNDED": WOUNDED,
    "PROMOTIONS": ACCENT,
    "MORALE CHANGES": CAPTION,
    "OURS": ACCENT,
    "ENEMY": OURS,
}

MORALE_COLOURS = {
    "Triumphant": "#8FC3F0",
    "Confident": "#86C39A",
    "Normal": "#8E9DAA",
    "Shaken": "#E0A86B",
    "Shattered": "#D97B4F",
    "Broken": "#D9645E",
}

MARGIN = 14
PILOT_ROW_HEIGHT = 44
GROUP_HEADER_HEIGHT = 24
#: Where the middle column starts. Wide enough for the longest aircraft-and-squadron
#: line the fork ships without either colliding.
DETAIL_X = 520


def _font(
    size: float, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False
) -> QFont:
    font = QFont("Consolas") if mono else QFont()
    font.setPixelSize(int(size))
    font.setWeight(weight)
    return font


def _label(text: str, size: float, colour: str, bold: bool = False) -> QLabel:
    label = QLabel(text)
    weight = "bold" if bold else "normal"
    label.setStyleSheet(f"font-size: {size}px; font-weight: {weight}; color: {colour};")
    return label


def _caption(text: str, hint: str = "") -> QWidget:
    """A section's name, above its card rather than inside a frame."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    name = QLabel(text.upper())
    name.setStyleSheet(
        f"font-size: 11px; font-weight: bold; letter-spacing: 1px; color: {CAPTION};"
    )
    row.addWidget(name)
    if hint:
        row.addWidget(_label(hint, 11, FAINT))
    row.addStretch()
    holder = QWidget()
    holder.setFixedHeight(20)
    holder.setLayout(row)
    return holder


def aircrew_reported(debriefing: DebriefingReport, records: list) -> list:
    """Whether this campaign reports what happened to the aircrew.

    The loss of an aircraft is always reported. What happened to the pilot inside it is
    not observable, so it is off by default.

    """
    if getattr(debriefing.game.settings, "live_pilots_debrief_enemy", False):
        return list(records)
    return [record for record in records if getattr(record, "blue", True)]


def _fold(rows: list[QWidget], folded: bool) -> None:
    for row in rows:
        row.setVisible(not folded)


def _card() -> QWidget:
    card = QWidget()
    card.setStyleSheet(
        f"background: {CARD}; border: 1px solid {LINE}; border-radius: 3px;"
    )
    return card


# --- the strip that answers the question ------------------------------------


class SummaryStrip(QWidget):
    """Four numbers and a verdict, before anything is scrolled."""

    def __init__(self, debriefing: DebriefingReport) -> None:
        super().__init__()
        self.setFixedHeight(96)
        self.setStyleSheet(f"background: {BAND}; border-bottom: 1px solid {LINE};")

        row = QHBoxLayout()
        row.setContentsMargins(24, 14, 24, 14)
        row.setSpacing(36)
        self.setLayout(row)

        status = QVBoxLayout()
        status.setSpacing(2)
        status.addWidget(_label("MISSION STATUS", 11, CAPTION, bold=True))
        ended = debriefing.state_data.mission_ended
        status.addWidget(
            _label(
                (
                    "Mission ended normally"
                    if ended
                    else "Mission ended early or state data was incomplete"
                ),
                20,
                TITLE,
                bold=True,
            )
        )
        status.addWidget(
            _label(
                f"{debriefing.player_country} vs {debriefing.enemy_country}", 12, MUTED
            )
        )
        row.addLayout(status)
        row.addStretch()

        blue = debriefing.loss_counts(Player.BLUE)
        red = debriefing.loss_counts(Player.RED)
        outcomes = debriefing.pilot_outcomes
        # The pilot figures have to count what the list below them shows, or the strip
        # promises casualties the report never accounts for.
        deaths = aircrew_reported(debriefing, outcomes.deaths)
        wounded = aircrew_reported(debriefing, outcomes.wounded)
        promotions = aircrew_reported(debriefing, outcomes.promotions)
        for caption, figures in (
            (
                "AIRCRAFT LOST",
                ((blue.aircraft, "ours", OURS), (red.aircraft, "theirs", THEIRS)),
            ),
            (
                "GROUND UNITS LOST",
                (
                    (blue.front_line + blue.ground_objects, "ours", OURS),
                    (red.front_line + red.ground_objects, "theirs", THEIRS),
                ),
            ),
            (
                "PILOTS",
                (
                    (len(deaths), "KIA", OURS),
                    (len(wounded), "wounded", WOUNDED),
                    (len(promotions), "promoted", ACCENT),
                ),
            ),
            (
                "BASES",
                ((len(debriefing.base_captures), "changed hands", MUTED),),
            ),
        ):
            row.addLayout(self._stat_group(caption, figures))

    @staticmethod
    def _stat_group(
        caption: str, figures: tuple[tuple[int, str, str], ...]
    ) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(2)
        column.addWidget(_label(caption, 10.5, DIM))
        numbers = QHBoxLayout()
        numbers.setSpacing(10)
        for value, unit, colour in figures:
            # A zero is not news, whatever it is a zero of.
            shown = colour if value else MUTED
            pair = QHBoxLayout()
            pair.setSpacing(4)
            figure = QLabel(str(value))
            figure.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 24px;"
                f" font-weight: 600; color: {shown};"
            )
            pair.addWidget(figure)
            pair.addWidget(
                _label(unit, 11.5, DIM), alignment=Qt.AlignmentFlag.AlignBottom
            )
            numbers.addLayout(pair)
        numbers.addStretch()
        column.addLayout(numbers)
        column.addStretch()
        return column


# --- the pilots -------------------------------------------------------------


#: The groups that fold, folded when the window opens: gains, which can run long and
#: would push the losses down. The dead and the wounded are always open.
FOLDED_GROUPS = ("PROMOTIONS", "MORALE CHANGES", "EXPERIENCE")


class GroupHeader(QWidget):
    """The name of one group of pilots, and how many are in it. A group that folds
    opens and closes on a click."""

    #: Emitted with whether the group is now folded.
    toggled = Signal(bool)

    def __init__(
        self, title: str, count: int, foldable: bool = False, folded: bool = False
    ) -> None:
        super().__init__()
        self.title = title
        self.count = count
        self.foldable = foldable
        self.folded = folded
        self.setFixedHeight(GROUP_HEADER_HEIGHT)
        if foldable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        if self.foldable and event.button() == Qt.MouseButton.LeftButton:
            self.folded = not self.folded
            self.update()
            self.toggled.emit(self.folded)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(HEADER))
        left = MARGIN
        if self.foldable:
            painter.setFont(_font(10, QFont.Weight.Bold))
            painter.setPen(QColor(CAPTION))
            painter.drawText(left, 16, "▸" if self.folded else "▾")
            left += 14
        painter.setFont(_font(10, QFont.Weight.Bold))
        painter.setPen(QColor(GROUP_COLOURS.get(self.title, CAPTION)))
        painter.drawText(left, 16, self.title)
        after = left + painter.fontMetrics().horizontalAdvance(self.title) + 10
        painter.setFont(_font(11, mono=True))
        painter.setPen(QColor(CAPTION))
        painter.drawText(after, 16, str(self.count))
        painter.end()


#: The ACHIEVED chip, by whose request it was: good news green, bad news red.
ACHIEVED_CHIP = {True: (THEIRS, "#1E3829"), False: (OURS, "#3D2326")}


def request_summary(request: Any) -> str:
    """What the request asked: "Medium tier · Oil field · Every unit destroyed".
    Empty for a request from a report saved before that was kept."""
    text = " · ".join(
        part for part in (request.tier, request.kind, request.taken) if part
    )
    return text[:1].upper() + text[1:]


class RequestRow(QWidget):
    """A request achieved: the objective and what it asked on the first line, what it
    pays on the second, and whether that is a ticket."""

    def __init__(self, request: Any) -> None:
        super().__init__()
        self.request = request
        self.setFixedHeight(PILOT_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:
        from qt_ui.windows.highcommand import palette as hc

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, self.height() - 1, self.width(), 1, QColor(LINE))

        word = "TICKET" if self.request.ticket else "INSTANT"
        ink, fill = (
            (hc.ORANGE, hc.TICKET_FILL)
            if self.request.ticket
            else (hc.INSTANT, hc.INSTANT_FILL)
        )
        painter.setFont(_font(10, QFont.Weight.Bold))
        width = painter.fontMetrics().horizontalAdvance(word) + 16
        right = self.width() - MARGIN
        chip = QRectF(right - width, 13, width, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(chip, 4, 4)
        painter.setPen(QColor(ink))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, word)
        end = chip.left() - 16

        painter.setFont(_font(14, QFont.Weight.DemiBold))
        painter.setPen(QColor(TITLE))
        painter.drawText(MARGIN, 19, self.request.objective)
        x = MARGIN + painter.fontMetrics().horizontalAdvance(self.request.objective) + 8
        x += self._paint_achieved(painter, x) + 10

        painter.setFont(_font(12))
        painter.setPen(QColor(MUTED))
        painter.drawText(
            int(x), 19, _elided(painter, request_summary(self.request), end - x)
        )
        painter.setPen(QColor(SUBDUED))
        painter.drawText(MARGIN, 37, _elided(painter, self.request.prize, end - MARGIN))
        painter.end()

    def _paint_achieved(self, painter: QPainter, x: float) -> float:
        ink, fill = ACHIEVED_CHIP[bool(self.request.blue)]
        painter.setFont(_font(9.5, QFont.Weight.Bold))
        label = "ACHIEVED"
        width = painter.fontMetrics().horizontalAdvance(label) + 12
        rect = QRectF(x, 5, width, 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setPen(QColor(ink))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        return width


def _elided(painter: QPainter, text: str, width: float) -> str:
    return painter.fontMetrics().elidedText(
        text, Qt.TextElideMode.ElideRight, max(int(width), 0)
    )


class PilotRow(QWidget):
    """One pilot in three columns: identity, what happened, and the result.

    The middle column changes meaning by group: who shot him down, the rank he came out
    with, or the state he ended in.

    """

    #: Two lines of identity. A row with more to say raises it.
    row_height = PILOT_ROW_HEIGHT

    def __init__(self, name: str, rank: str, level: int, aircraft: str, squadron: str):
        super().__init__()
        self.name = name
        self.rank = rank
        self.level = level
        self.aircraft = aircraft
        self.squadron = squadron
        self.player = False
        self.setFixedHeight(self.row_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, self.row_height - 1, self.width(), 1, QColor(LINE))
        self._paint_identity(painter)
        self.paint_detail(painter, DETAIL_X)
        self.paint_outcome(painter, self.width() - MARGIN)
        painter.end()

    def _paint_identity(self, painter: QPainter) -> None:
        painter.setFont(_font(14, QFont.Weight.DemiBold))
        painter.setPen(QColor(TITLE))
        painter.drawText(MARGIN, 19, self.name)
        x = MARGIN + painter.fontMetrics().horizontalAdvance(self.name) + 8

        x += paint_rank_stars(painter, x, 19, self.level) + 8
        painter.setFont(_font(12))
        painter.setPen(QColor(DIM))
        painter.drawText(int(x), 19, self.rank)
        if self.player:
            x += painter.fontMetrics().horizontalAdvance(self.rank) + 8
            self._paint_player_chip(painter, x)

        painter.setFont(_font(12))
        painter.setPen(QColor(SUBDUED))
        painter.drawText(MARGIN, 37, self.aircraft)
        x = MARGIN + painter.fontMetrics().horizontalAdvance(self.aircraft) + 6
        painter.setPen(QColor(FAINT))
        painter.drawText(int(x), 37, "·")
        x += painter.fontMetrics().horizontalAdvance("·") + 6
        painter.setPen(QColor(MUTED))
        painter.drawText(int(x), 37, self.squadron)

    @staticmethod
    def _paint_player_chip(painter: QPainter, x: float) -> None:
        painter.setFont(_font(9.5, QFont.Weight.Bold))
        label = "PLAYER"
        width = painter.fontMetrics().horizontalAdvance(label) + 12
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#22384A"))
        painter.drawRoundedRect(QRectF(x, 5, width, 16), 3, 3)
        painter.setPen(QColor(ACCENT))
        painter.drawText(QRectF(x, 5, width, 16), Qt.AlignmentFlag.AlignCenter, label)

    def paint_detail(self, painter: QPainter, x: int) -> None:
        """What happened to him. Overridden per group."""

    def paint_outcome(self, painter: QPainter, right: int) -> None:
        """What it left him with, right-aligned. Overridden per group."""

    @staticmethod
    def _right(painter: QPainter, right: int, baseline: int, parts) -> None:
        """Draw ``(text, colour, font)`` triples ending at ``right``."""
        total = 0.0
        for text, _, font in parts:
            painter.setFont(font)
            total += painter.fontMetrics().horizontalAdvance(text)
        x = right - total
        for text, colour, font in parts:
            painter.setFont(font)
            painter.setPen(QColor(colour))
            painter.drawText(int(x), baseline, text)
            x += painter.fontMetrics().horizontalAdvance(text)


class ShotDownRow(PilotRow):
    """A man who was hit: who did it, and whether he walked away."""

    def __init__(self, record: PilotDeath, outcome: str, colour: str, detail: str = ""):
        super().__init__(
            record.pilot_name,
            record.rank,
            record.level,
            record.aircraft,
            record.squadron,
        )
        self.record = record
        self.outcome = outcome
        self.colour = colour
        self.detail = detail

    def paint_detail(self, painter: QPainter, x: int) -> None:
        self.paint_attribution(painter, x, self.record)

    @staticmethod
    def paint_attribution(painter: QPainter, x: int, record: Any) -> None:
        """Who brought him down. Shared with the wounded, who were brought down too."""
        if record.friendly_fire:
            lead, killer = "lost to friendly fire from ", record.killed_by or ""
        elif record.killed_by:
            lead, killer = "shot down by ", record.killed_by
        else:
            lead, killer = "lost, with nobody credited", ""
        painter.setFont(_font(12))
        painter.setPen(QColor(DIM))
        painter.drawText(x, 27, lead)
        if killer:
            after = x + painter.fontMetrics().horizontalAdvance(lead)
            painter.setFont(_font(12, QFont.Weight.Medium))
            painter.setPen(QColor(OURS if record.friendly_fire else BODY))
            painter.drawText(int(after), 27, killer)

    def paint_outcome(self, painter: QPainter, right: int) -> None:
        if self.outcome == "KIA":
            painter.setFont(_font(10, QFont.Weight.Bold))
            width = painter.fontMetrics().horizontalAdvance("KIA") + 16
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#3B2523"))
            painter.drawRoundedRect(QRectF(right - width, 13, width, 18), 4, 4)
            painter.setPen(QColor(OURS))
            painter.drawText(
                QRectF(right - width, 13, width, 18),
                Qt.AlignmentFlag.AlignCenter,
                "KIA",
            )
            return
        parts = [(self.outcome, self.colour, _font(11.5))]
        if self.detail:
            parts.append((f" · {self.detail}", WOUNDED_DETAIL, _font(11.5)))
        self._right(painter, right, 27, parts)


class WoundedRow(PilotRow):
    """Who put him in the hospital, and for how long.

    That the medics reached him is already the heading; what is worth the column is the
    same thing the dead get -- who did it.
    """

    def __init__(self, record: PilotWound):
        super().__init__(
            record.pilot_name,
            record.rank,
            record.level,
            record.aircraft,
            record.squadron,
        )
        self.record = record
        self.turns = record.turns

    def paint_detail(self, painter: QPainter, x: int) -> None:
        ShotDownRow.paint_attribution(painter, x, self.record)

    def paint_outcome(self, painter: QPainter, right: int) -> None:
        self._right(
            painter,
            right,
            27,
            [
                ("Wounded", WOUNDED, _font(11.5)),
                (f" · {turns_phrase(self.turns)}", WOUNDED_DETAIL, _font(11.5)),
            ],
        )


class PromotionRow(PilotRow):
    """A promotion drawn as the transition it is: dim stars to gold."""

    def __init__(self, record: PilotPromotion):
        super().__init__(
            record.pilot_name,
            record.from_rank,
            record.from_level,
            record.aircraft,
            record.squadron,
        )
        self.record = record
        self.player = record.player

    def paint_detail(self, painter: QPainter, x: int) -> None:
        cursor = float(x)
        cursor += paint_rank_stars(
            painter,
            cursor,
            27,
            self.record.from_level,
            filled=STAR_FILLED_DIMMED,
            empty=STAR_EMPTY_DIMMED,
        )
        cursor += 6
        painter.setFont(_font(12))
        painter.setPen(QColor(DIM))
        painter.drawText(int(cursor), 27, self.record.from_rank)
        cursor += painter.fontMetrics().horizontalAdvance(self.record.from_rank) + 8
        painter.setPen(QColor(ACCENT))
        painter.drawText(int(cursor), 27, "→")
        cursor += painter.fontMetrics().horizontalAdvance("→") + 8
        cursor += paint_rank_stars(
            painter,
            cursor,
            27,
            self.record.to_level,
            filled=STAR_FILLED,
            empty=STAR_EMPTY,
        )
        cursor += 6
        painter.setFont(_font(12, QFont.Weight.Medium))
        painter.setPen(QColor(TITLE))
        painter.drawText(
            int(cursor), 27, self.record.to_rank_full or self.record.to_rank
        )


#: How tall a row with reasons is: the two identity lines plus one for the reasons.
REASONS_ROW_HEIGHT = PILOT_ROW_HEIGHT + 22

#: The reason lines, coloured by what kind of thing earned them, so a glance separates
#: what he shot at from what the sortie and the company he kept were worth.
XP_REASON_COLOURS: dict[str, str] = {
    XP_AIR: ACCENT,
    XP_GROUND: ACCENT,
    XP_SHIPS: ACCENT,
    XP_BUILDINGS: ACCENT,
    XP_DAMAGE: SUBDUED,
    XP_MISSION: UNHURT,
    XP_WOUND: WOUNDED,
    XP_MORALE: AMBER,
    XP_LEARNING: AMBER,
    XP_COMPANY: AMBER,
    XP_HELD_BACK: OURS,
}


class ReasonsRow(PilotRow):
    """A pilot with what moved him on a line of its own.

    Each reason is drawn as its own chip, with its amount when the record has one; when
    they do not fit, the ones that are left are counted rather than truncated, so the
    line never lies about what it is showing.
    """

    row_height = REASONS_ROW_HEIGHT

    def reasons(self) -> Sequence[tuple[str, Optional[int]]]:
        """The chips, in the order they are drawn."""
        return ()

    def amount_colour(self, reason: str, amount: int) -> str:
        return SUBDUED

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_reasons(painter)
        painter.end()

    def _paint_reasons(self, painter: QPainter) -> None:
        baseline = PILOT_ROW_HEIGHT + 11
        limit = self.width() - MARGIN
        cursor = float(MARGIN)
        reasons = self.reasons()
        for index, (reason, amount) in enumerate(reasons):
            width = self._chip_width(painter, reason, amount)
            remaining = len(reasons) - index
            if cursor + width > limit and index:
                self._paint_overflow(painter, cursor, baseline, remaining)
                return
            cursor = self._paint_chip(painter, cursor, baseline, reason, amount)

    @staticmethod
    def _chip_width(painter: QPainter, reason: str, amount: Optional[int]) -> float:
        painter.setFont(_font(11))
        width = painter.fontMetrics().horizontalAdvance(reason)
        if amount is not None:
            painter.setFont(_font(11, QFont.Weight.DemiBold))
            width += 6 + painter.fontMetrics().horizontalAdvance(f"{amount:+,}")
        return width + 14

    def _paint_chip(
        self,
        painter: QPainter,
        x: float,
        baseline: int,
        reason: str,
        amount: Optional[int],
    ) -> float:
        painter.setFont(_font(11))
        painter.setPen(QColor(MUTED))
        painter.drawText(int(x), baseline, reason)
        x += painter.fontMetrics().horizontalAdvance(reason)
        if amount is not None:
            x += 6
            painter.setFont(_font(11, QFont.Weight.DemiBold))
            painter.setPen(QColor(self.amount_colour(reason, amount)))
            text = f"{amount:+,}"
            painter.drawText(int(x), baseline, text)
            x += painter.fontMetrics().horizontalAdvance(text)
        return x + 14

    @staticmethod
    def _paint_overflow(
        painter: QPainter, x: float, baseline: int, remaining: int
    ) -> None:
        painter.setFont(_font(11))
        painter.setPen(QColor(FAINT))
        painter.drawText(int(x), baseline, f"+{remaining} more")


class XpRow(ReasonsRow):
    """What a pilot was paid, and the reasons on a line of their own.

    A total says a man gained 1,400 and nothing about whether that was two MiGs or a
    long afternoon of trucks, and the multipliers do not show up in it at all.
    """

    def __init__(self, record: XpAward):
        super().__init__(
            record.pilot_name,
            record.rank,
            record.level,
            record.aircraft,
            record.squadron,
        )
        self.record = record

    def reasons(self) -> Sequence[tuple[str, Optional[int]]]:
        return self.record.ordered_reasons

    def amount_colour(self, reason: str, amount: int) -> str:
        return XP_REASON_COLOURS.get(reason, SUBDUED)

    def paint_detail(self, painter: QPainter, x: int) -> None:
        """Nothing in the middle column: the reasons get the width instead."""

    def paint_outcome(self, painter: QPainter, right: int) -> None:
        gained = self.record.gained
        self._right(
            painter,
            right,
            27,
            [
                (
                    f"{gained:+,}",
                    UNHURT if gained >= 0 else OURS,
                    _font(15, QFont.Weight.DemiBold),
                ),
                (" XP", MUTED, _font(11)),
            ],
        )
        self._right(
            painter,
            right,
            43,
            [(f"{self.record.after:,} total", FAINT, _font(10.5))],
        )


class MoraleRow(ReasonsRow):
    """Old state to new, with only the new one coloured, and what moved him on a line
    of its own."""

    def __init__(self, record: MoraleShift):
        super().__init__(
            record.pilot_name,
            record.rank,
            record.level,
            record.aircraft,
            record.squadron,
        )
        self.record = record

    def paint_detail(self, painter: QPainter, x: int) -> None:
        # Named when the turn was scored; only a report from before that was recorded
        # has to be worked out here, and then from the standard bands.
        was = self.record.before_state or morale_state(self.record.before).name
        now = self.record.after_state or morale_state(self.record.after).name
        cursor = float(x)
        colour = MORALE_COLOURS.get(now, MUTED)
        cursor = self._paint_state(painter, cursor, was, DIM, DIM)
        painter.setFont(_font(12))
        painter.setPen(QColor(DIM))
        painter.drawText(int(cursor), 27, "→")
        cursor += painter.fontMetrics().horizontalAdvance("→") + 8
        self._paint_state(painter, cursor, now, colour, colour, medium=True)

    def reasons(self) -> Sequence[tuple[str, Optional[int]]]:
        return self.record.ordered_reasons

    def amount_colour(self, reason: str, amount: int) -> str:
        return UNHURT if amount > 0 else OURS

    @staticmethod
    def _paint_state(
        painter: QPainter,
        x: float,
        text: str,
        dot: str,
        label: str,
        medium: bool = False,
    ) -> float:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(dot))
        painter.drawEllipse(QRectF(x, 19, 8, 8))
        x += 8 + 6
        painter.setFont(
            _font(12, QFont.Weight.Medium if medium else QFont.Weight.Normal)
        )
        painter.setPen(QColor(label))
        painter.drawText(int(x), 27, text)
        return x + painter.fontMetrics().horizontalAdvance(text) + 8

    def paint_outcome(self, painter: QPainter, right: int) -> None:
        change = self.record.after - self.record.before
        self._right(
            painter,
            right,
            27,
            [
                (
                    f"{change:+}",
                    UNHURT if change >= 0 else OURS,
                    _font(15, QFont.Weight.DemiBold),
                ),
                (" morale", MUTED, _font(11)),
            ],
        )
        if self.record.after <= 0:
            self._right(
                painter, right, 43, [("▲ will refuse to fly", OURS, _font(10.5))]
            )


# --- the ledgers ------------------------------------------------------------


#: What a total says, how much, and a note when there is something to add.
Total = tuple[str, float, str]


class FactionLosses(QWidget):
    """One side's losses: aircraft over ground, with the total in the header."""

    def __init__(self, debriefing: DebriefingReport, player: Player) -> None:
        super().__init__()
        ours = player.is_blue
        counts = debriefing.loss_counts(player)
        total = counts.aircraft + counts.front_line + counts.ground_objects
        name = debriefing.player_country if ours else debriefing.enemy_country

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)
        self.setStyleSheet(
            f"background: {CARD}; border: 1px solid {LINE}; border-radius: 3px;"
        )

        head = QWidget()
        head.setFixedHeight(30)
        head.setStyleSheet(f"background: {HEADER}; border: none;")
        head_row = QHBoxLayout()
        head_row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        head.setLayout(head_row)
        head_row.addWidget(_label(str(name), 11, TITLE, bold=True))
        head_row.addStretch()
        figure = QLabel(str(total))
        figure.setStyleSheet(
            f"font-family: Consolas, monospace; font-size: 14px; font-weight: 600;"
            f" color: {OURS if ours else THEIRS}; border: none;"
        )
        head_row.addWidget(figure)
        head_row.addWidget(_label("units lost", 11, DIM))
        outer.addWidget(head)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 6)
        body.setSpacing(0)
        outer.addLayout(body)

        air = self._air_rows(debriefing, player)
        ground = self._ground_rows(debriefing, player)
        costs = debriefing.loss_costs(player)
        self._add_group(body, "AIRCRAFT", air, self._air_totals(costs))
        self._add_group(body, "GROUND", ground, self._ground_totals(costs))
        if not air and not ground:
            body.addWidget(self._row("Nothing lost", "", FAINT, ""))

    def _add_group(
        self, body: QVBoxLayout, title: str, rows: list, totals: list[Total]
    ) -> None:
        if not rows:
            return
        head = QWidget()
        head.setFixedHeight(22)
        head.setStyleSheet("border: none;")
        row = QHBoxLayout()
        row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        head.setLayout(row)
        row.addWidget(_label(title, 10, CAPTION, bold=True))
        row.addStretch()
        count = QLabel(str(sum(n for _, n, _ in rows)))
        count.setStyleSheet(
            f"font-family: Consolas, monospace; font-size: 11px; color: {DIM};"
            " border: none;"
        )
        row.addWidget(count)
        body.addWidget(head)
        for name, number, note in rows:
            body.addWidget(
                self._row(name, str(number), BODY if number else CAPTION, note)
            )
        if totals:
            body.addWidget(self._divider())
        for words, amount, note in totals:
            body.addWidget(self._total(words, amount, note))
        if totals:
            body.addSpacing(6)

    @staticmethod
    def _divider() -> QWidget:
        holder = QWidget()
        holder.setFixedHeight(7)
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout()
        row.setContentsMargins(MARGIN, 3, MARGIN, 3)
        holder.setLayout(row)
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {LINE}; border: none;")
        row.addWidget(line)
        return holder

    @staticmethod
    def _air_totals(costs: Optional[LossCosts]) -> list[Total]:
        # A report kept before the costs were has none to show.
        if costs is None or costs.aircraft <= 0:
            return []
        return [("Cost to replace", costs.aircraft, "")]

    @staticmethod
    def _ground_totals(costs: Optional[LossCosts]) -> list[Total]:
        if costs is None:
            return []
        totals: list[Total] = []
        if costs.ground > 0 or costs.ships:
            note = (
                f"not counting {counted(costs.ships, 'ship')}, which cannot be replaced"
                if costs.ships
                else ""
            )
            totals.append(("Cost to replace", costs.ground, note))
        if costs.income > 0:
            totals.append(("Income lost while repairing", costs.income, ""))
        return totals

    @staticmethod
    def _total(words: str, amount: float, note: str) -> QWidget:
        holder = QWidget()
        holder.setFixedHeight(24)
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout()
        row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        row.setSpacing(8)
        holder.setLayout(row)
        row.addWidget(_label(words, 11.5, DIM))
        if note:
            row.addWidget(_label(note, 11, CAPTION))
        row.addStretch()
        figure = QLabel(money(amount))
        figure.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12.5px; font-weight: 600;"
            f" color: {BODY}; border: none;"
        )
        row.addWidget(figure)
        return holder

    @staticmethod
    def _row(name: str, number: str, colour: str, note: str) -> QWidget:
        holder = QWidget()
        holder.setFixedHeight(28)
        holder.setStyleSheet("border: none;")
        row = QHBoxLayout()
        row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        row.setSpacing(8)
        holder.setLayout(row)
        row.addWidget(_label(name, 12.5, colour))
        if note:
            row.addWidget(_label(note, 11, CAPTION))
        row.addStretch()
        if number:
            figure = QLabel(number)
            figure.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 13px;"
                f" font-weight: 600; color: {TITLE if number != '0' else CAPTION};"
                " border: none;"
            )
            row.addWidget(figure)
        return holder

    @staticmethod
    def _air_rows(debriefing: DebriefingReport, player: Player) -> list:
        # Counted when the mission was flown; see game/debriefingreport.py.
        return debriefing.air_rows(player)

    @staticmethod
    def _ground_rows(debriefing: DebriefingReport, player: Player) -> list:
        # Counted when the mission was flown; see game/debriefingreport.py.
        return debriefing.ground_rows(player)


# --- the window -------------------------------------------------------------


class QDebriefingWindow(QDialog):
    def __init__(self, debriefing: DebriefingReport):
        super(QDebriefingWindow, self).__init__()
        self.debriefing = debriefing
        # This window can be put back up from the Misc bar, so the promotion box is
        # told once and not on every reopening. The leave requests are not guarded:
        # that dialog reads who is still waiting, so it simply has nothing to ask.
        self._congratulated = False

        self.setModal(True)
        # The report's own turn, not the game's: the turn is passed before the
        # window is shown, and a report reopened later belongs to an older one.
        self.setWindowTitle(f"Debriefing — Turn {debriefing.turn}")
        self.setWindowIcon(QIcon("./resources/icon.png"))
        self.setStyleSheet(f"QDialog {{ background: {PAGE}; }}")

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        outer.addWidget(SummaryStrip(debriefing))

        # The report scrolls as a whole. It used not to, and a mission with a busy
        # Pilots box squeezed every section until the lines overlapped each other.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {PAGE};")
        outer.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(30)
        body.setLayout(layout)

        for section in (
            self._pilots_section(debriefing),
            self._high_command_section(debriefing),
            self._losses_section(debriefing),
            self._front_line_section(debriefing),
            self._missiles_section(debriefing),
        ):
            if section is not None:
                layout.addLayout(section)
        layout.addStretch(1)

        outer.addWidget(self._footer(debriefing))

        available = self.screen().availableGeometry() if self.screen() else None
        if available is not None:
            self.resize(
                min(1130, available.width() - 80),
                min(920, available.height() - 80),
            )

    # --- sections -----------------------------------------------------------

    @staticmethod
    def _section(caption: str, hint: str, card: QWidget) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(10)
        column.addWidget(_caption(caption, hint))
        column.addWidget(card)
        return column

    def _pilots_section(self, debriefing: DebriefingReport) -> Optional[QVBoxLayout]:
        """The aircrew section: who was lost, who was wounded, and who gained.

        Omitted entirely when nothing happened to the aircrew, and so is any group
        inside it.

        """
        outcomes = debriefing.pilot_outcomes
        if outcomes.empty:
            return None

        def shown(records: list) -> list:
            return aircrew_reported(debriefing, records)

        card = _card()
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        card.setLayout(column)

        groups: list[tuple[str, list[QWidget]]] = [
            (
                "KILLED IN ACTION",
                [ShotDownRow(d, "KIA", OURS) for d in shown(outcomes.deaths)],
            ),
            (
                "SHOT DOWN & RECOVERED",
                [ShotDownRow(s, "Unhurt", UNHURT) for s in shown(outcomes.survivors)],
            ),
            ("WOUNDED", [WoundedRow(w) for w in shown(outcomes.wounded)]),
            ("PROMOTIONS", [PromotionRow(p) for p in shown(outcomes.promotions)]),
            ("MORALE CHANGES", [MoraleRow(m) for m in shown(outcomes.morale_shifts)]),
            # Every man who flew is paid, so this is the one group that is routinely
            # long. Biggest gain first, because the turn's story is at the top of it.
            (
                "EXPERIENCE",
                [
                    XpRow(a)
                    for a in sorted(
                        shown(outcomes.xp_awards),
                        key=lambda award: award.gained,
                        reverse=True,
                    )
                ],
            ),
        ]
        drawn = 0
        for title, rows in groups:
            if not rows:
                continue
            drawn += len(rows)
            folds = title in FOLDED_GROUPS
            header = GroupHeader(title, len(rows), foldable=folds, folded=folds)
            column.addWidget(header)
            for row in rows:
                row.setVisible(not folds)
                column.addWidget(row)
            if folds:
                header.toggled.connect(partial(_fold, rows))
        if not drawn:
            # Everything that happened, happened to the other side, and this campaign
            # does not report their aircrew.
            return None
        return self._section("Pilots", "only groups with entries are drawn", card)

    def _high_command_section(
        self, debriefing: DebriefingReport
    ) -> Optional[QVBoxLayout]:
        """The High Command requests the mission achieved, and what each pays; the
        enemy's too, when the campaign reports them."""
        requests = list(getattr(debriefing, "high_command", []))
        ours = [request for request in requests if request.blue]
        theirs = [request for request in requests if not request.blue]
        settings = getattr(debriefing.game, "settings", None)
        if not getattr(settings, "high_command_report_enemy", True):
            theirs = []
        if not ours and not theirs:
            return None
        card = _card()
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        card.setLayout(column)
        for title, side in (("OURS", ours), ("ENEMY", theirs)):
            if not side:
                continue
            if theirs:
                column.addWidget(GroupHeader(title, len(side)))
            for request in side:
                column.addWidget(RequestRow(request))
        return self._section("High Command", "requests achieved · what each pays", card)

    def _losses_section(self, debriefing: DebriefingReport) -> QVBoxLayout:
        """Both sides side by side: stacked, the exchange took a scroll to read."""
        card = QWidget()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        card.setLayout(grid)
        grid.addWidget(FactionLosses(debriefing, Player.BLUE), 0, 0)
        grid.addWidget(FactionLosses(debriefing, Player.RED), 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return self._section(
            "Losses", "both sides, side by side · aircraft first, then ground", card
        )

    def _front_line_section(
        self, debriefing: DebriefingReport
    ) -> Optional[QVBoxLayout]:
        captured = [
            capture.control_point.name
            for capture in debriefing.base_captures
            if capture.captured_by_player.is_blue
        ]
        lost = [
            capture.control_point.name
            for capture in debriefing.base_captures
            if capture.captured_by_player.is_red
        ]
        runways = [airfield.name for airfield in debriefing.damaged_runways]
        rows = [
            ("Bases captured", ", ".join(captured), BODY),
            ("Bases lost", ", ".join(lost), OURS),
            ("Runways damaged", ", ".join(runways), AMBER),
        ]
        if not any(value for _, value, _ in rows):
            return None

        card = _card()
        column = QVBoxLayout()
        column.setContentsMargins(0, 4, 0, 4)
        column.setSpacing(0)
        card.setLayout(column)
        for key, value, colour in rows:
            holder = QWidget()
            holder.setFixedHeight(32)
            holder.setStyleSheet("border: none;")
            row = QHBoxLayout()
            row.setContentsMargins(MARGIN, 0, MARGIN, 0)
            holder.setLayout(row)
            row.addWidget(_label(key, 12.5, SUBDUED))
            row.addSpacing(160)
            row.addWidget(_label(value or "none", 12.5, colour if value else FAINT))
            row.addStretch()
            column.addWidget(holder)
        return self._section(
            "Front line & bases", "rows with nothing to report say none", card
        )

    def _missiles_section(self, debriefing: DebriefingReport) -> Optional[QVBoxLayout]:
        """Shown after the turn-boundary debit, so what remains is next turn's stock.

        Enemy remainders stay hidden: a launch is observable, a magazine is not.
        """
        # Read at the turn boundary and kept: a shooter that has since sailed on,
        # been sunk or been rearmed would answer differently now.
        expenditures = debriefing.missile_rows
        if not expenditures:
            return None

        card = _card()
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 6)
        column.setSpacing(0)
        card.setLayout(column)

        head = QWidget()
        head.setFixedHeight(22)
        head.setStyleSheet("border: none;")
        head_row = QHBoxLayout()
        head_row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        head.setLayout(head_row)
        head_row.addWidget(_label("LAUNCHER", 10, CAPTION, bold=True))
        head_row.addStretch()
        head_row.addWidget(_label("FIRED", 10, CAPTION, bold=True))
        head_row.addSpacing(60)
        head_row.addWidget(_label("REMAINING", 10, CAPTION, bold=True))
        column.addWidget(head)

        for group_name, fired, remaining in expenditures:
            holder = QWidget()
            holder.setFixedHeight(32)
            holder.setStyleSheet("border: none;")
            row = QHBoxLayout()
            row.setContentsMargins(MARGIN, 0, MARGIN, 0)
            holder.setLayout(row)
            row.addWidget(_label(group_name, 12.5, BODY))
            row.addStretch()
            fired_label = QLabel(str(fired))
            fired_label.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 13px; color: {TITLE};"
                " border: none;"
            )
            row.addWidget(fired_label)
            row.addSpacing(60)
            left = QLabel("—" if remaining is None else str(remaining))
            left.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 13px;"
                f" color: {SUBDUED if remaining else DIM}; border: none;"
            )
            left.setToolTip(
                "Only your own magazines are known."
                if remaining is None
                else "What sails into next turn. There is no resupply."
            )
            row.addWidget(left)
            column.addWidget(holder)
        return self._section("Cruise missiles expended", "", card)

    def _footer(self, debriefing: DebriefingReport) -> QWidget:
        """The way out, and what closing it will bring up next."""
        footer = QWidget()
        footer.setFixedHeight(56)
        footer.setStyleSheet(f"background: {BAND}; border-top: 1px solid {LINE};")
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 24, 0)
        footer.setLayout(row)

        coming = []
        if any(p.player for p in debriefing.pilot_outcomes.promotions):
            coming.append("your promotion")
        waiting = self._leave_requests(debriefing)
        if waiting:
            coming.append(
                f"{len(waiting)} leave request" f"{'' if len(waiting) == 1 else 's'}"
            )
        if coming:
            row.addWidget(_label(f"Next: {' · '.join(coming)}", 11.5, DIM))
        row.addStretch()

        okay = QPushButton("Continue")
        okay.setStyleSheet(
            "QPushButton { height: 30px; font-size: 12px; font-weight: 600;"
            f" background: {ACCENT}; border: none; border-radius: 3px;"
            " color: #0F1922; padding: 0 20px; }"
        )
        okay.clicked.connect(self.close)
        row.addWidget(okay)
        return footer

    @staticmethod
    def _leave_requests(debriefing: DebriefingReport) -> list:
        from qt_ui.windows.LeaveRequestsDialog import pending_leave_requests

        game = debriefing.game
        if not game.settings.live_pilots_enabled or not getattr(
            game.settings, "morale_enabled", True
        ):
            return []
        return pending_leave_requests(game)

    # --- what this window leads to ------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        # Queued rather than shown here: this dialog is modal and still closing, and a
        # second modal opened from inside closeEvent inherits the mess.
        QTimer.singleShot(0, self._congratulate_the_player)
        QTimer.singleShot(0, self._answer_leave_requests)
        GameUpdateSignal.get_instance().updateGame(self.debriefing.game)

    def _answer_leave_requests(self) -> None:
        """Whoever asked for a rest this turn, and your answer.

        Queued after the promotion box so the good news comes first.
        """
        from qt_ui.windows.LeaveRequestsDialog import LeaveRequestsDialog

        requests = self._leave_requests(self.debriefing)
        if not requests:
            return
        self._leave_dialog = LeaveRequestsDialog(self.debriefing.game, requests)
        self._leave_dialog.exec()

    def _congratulate_the_player(self) -> None:
        """A promotion of one of the player's own pilots is told, not just listed."""
        if self._congratulated:
            return
        mine = [p for p in self.debriefing.pilot_outcomes.promotions if p.player]
        if not mine:
            return
        self._congratulated = True
        if len(mine) == 1:
            body = (
                f"You have been promoted to <b>{mine[0].to_rank_full}</b> "
                f"in {mine[0].squadron}."
            )
        else:
            named = "<br>".join(
                f"{p.pilot_name} — <b>{p.to_rank_full}</b>, {p.squadron}" for p in mine
            )
            body = f"Your pilots have been promoted:<br><br>{named}"
        box = QMessageBox(self)
        box.setWindowTitle("Promotion")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(body)
        box.exec()
