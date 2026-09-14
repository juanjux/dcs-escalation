"""A pilot drawn as a row: stars, rank, name, whether he is you, and how he is holding up.

The flight dialog picked its crew from combo boxes that drew one line of plain text,
so the five things you choose a pilot on arrived as one colour and one weight, and
morale had to be squeezed in as an emoji -- which renders differently on every machine
and says nothing to anyone who has not learnt the faces.

Painting the row means the combo can say the same thing the squadron roster says, in
the same vocabulary: rank as five slots you can scan down, the name as the only bold
thing, and morale as a coloured dot with its word. The popup uses the same painter, so
you can pick by morale rather than opening the Air Wing to find out.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QStylePainter,
    QWidget,
)

from game.squadrons import friendship
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot
from qt_ui.rankstars import (
    STAR_EMPTY,
    STAR_EMPTY_SELECTED,
    STAR_FILLED,
    STAR_FILLED_SELECTED,
    paint_rank_stars,
    star_font,
    stars_width,
)

#: The morale ramp, cold to hot, matching the states in :mod:`game.squadrons.morale`.
#: Normal is deliberately grey: a squadron that is holding up should read as quiet, and
#: colour should mean something is unusual.
MORALE_COLOURS = {
    "Triumphant": "#8FC3F0",
    "Confident": "#86C39A",
    "Normal": "#8E9DAA",
    "Shaken": "#E0A86B",
    "Shattered": "#D97B4F",
    "Broken": "#D9645E",
}
#: The label recedes further than the dot for a pilot nobody needs to think about.
MORALE_LABEL_OVERRIDE = {"Normal": "#B7C6D2"}
MORALE_LABEL_OVERRIDE_SELECTED = {"Normal": "#E4EDF4"}

#: How far the friendship wash behind a row can go, out of 255. A wash rather than a
#: colour: the name and the morale dot are what the row is read for, and a fill that
#: competes with them makes the list harder to use rather than easier. Halved on the
#: selected row, which already has a fill of its own under it.
TINT_ALPHA = 64
TINT_ALPHA_SELECTED = 32

#: What the faintest band is still worth, as a share of the ceiling. A pair only just
#: into Friendly is news -- it is the first band that is -- and at a strictly linear
#: ramp it arrived so close to nothing that the row read as Neutral.
TINT_FLOOR = 0.35

ROW_HEIGHT = 28

TEXT_PRIMARY = QColor("#F2F7FA")
TEXT_SELECTED = QColor("#FFFFFF")
RANK_TEXT = QColor("#7C8B99")
RANK_TEXT_SELECTED = QColor("#B7C6D2")
UNASSIGNED = QColor("#E0A86B")
MUTED = QColor("#4F6070")
SELECTED_FILL = QColor("#1E3A52")
HOVER_FILL = QColor("#1A2A38")

PLAYER_CHIP_BG = QColor("#2B4A66")
PLAYER_CHIP_TEXT = QColor("#BEDCF6")

LEFT = 8
GAP = 7
DOT = 8
CHIP_HEIGHT = 15
CHIP_RADIUS = 3
CHIP_PADDING = 5


def _font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def morale_word(pilot: Pilot, squadron: Any) -> Optional[str]:
    """The state's name, or None when this pilot has no morale to show.

    The player has none on purpose: he knows how his own week went. Neither has anyone
    when the campaign has morale switched off.
    """
    if squadron is None or not getattr(squadron, "morale_in_play", False):
        return None
    if not getattr(pilot, "has_morale", False):
        return None
    state = morale_rules.morale_state(pilot.morale, squadron.settings)
    return str(state.name)


def affinity_tint(
    affinity: Optional[float], selected: bool = False, settings: Any = None
) -> Optional[QColor]:
    """The wash behind a man whose company would change the flight.

    None for a pair nobody needs to think about, which is what Neutral is: only what is
    news gets painted. Blended by alpha rather than by hue so the band's own colour
    still means what it means in every other list.
    """
    if affinity is None:
        return None
    band = friendship.band(affinity, settings)
    if band.colour is None:
        return None
    strength = min(abs(friendship.points(affinity)), 5.0) / 5.0
    strength = TINT_FLOOR + (1.0 - TINT_FLOOR) * strength
    colour = QColor(band.colour)
    colour.setAlpha(
        int(round(strength * (TINT_ALPHA_SELECTED if selected else TINT_ALPHA)))
    )
    return colour


def paint_pilot(
    painter: QPainter,
    rect: QRect,
    pilot: Optional[Pilot],
    squadron: Any,
    selected: bool = False,
    unassigned_text: str = "Unassigned — choose a pilot",
    affinity: Optional[float] = None,
) -> None:
    """Draw one pilot into ``rect``. Used by the popup and by the closed combo."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if pilot is None:
        painter.setFont(_font(12))
        painter.setPen(UNASSIGNED)
        painter.drawText(
            rect.adjusted(LEFT, 0, -LEFT, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            unassigned_text,
        )
        painter.restore()
        return

    tint = affinity_tint(affinity, selected, getattr(squadron, "settings", None))
    if tint is not None:
        painter.fillRect(rect, tint)

    baseline = rect.center().y() + 5
    x = float(rect.left() + LEFT)

    # Rank, as five slots. Always five, so the names below start at the same x.
    level = morale_rules.rank_level(squadron.pilot_skill(pilot)) if squadron else 0
    painter.setFont(star_font())
    x += paint_rank_stars(
        painter,
        x,
        baseline,
        level,
        filled=STAR_FILLED_SELECTED if selected else STAR_FILLED,
        empty=STAR_EMPTY_SELECTED if selected else STAR_EMPTY,
    )
    x += GAP

    rank = squadron.pilot_rank(pilot) if squadron else None
    if rank is not None:
        font = _font(12)
        painter.setFont(font)
        painter.setPen(RANK_TEXT_SELECTED if selected else RANK_TEXT)
        painter.drawText(int(x), baseline, rank.abbreviation)
        x += QFontMetrics(font).horizontalAdvance(rank.abbreviation) + GAP

    # Reserve the right-hand end for the things that must never be elided: whether he
    # is you, and how he is holding up.
    right = float(rect.right() - LEFT)
    word = morale_word(pilot, squadron)
    if word is not None:
        label_font = _font(12, QFont.Weight.Medium)
        label_width = QFontMetrics(label_font).horizontalAdvance(word)
        right -= label_width
        colour = QColor(MORALE_COLOURS.get(word, "#8E9DAA"))
        overrides = (
            MORALE_LABEL_OVERRIDE_SELECTED if selected else MORALE_LABEL_OVERRIDE
        )
        painter.setFont(label_font)
        painter.setPen(QColor(overrides.get(word, colour.name())))
        painter.drawText(int(right), baseline, word)
        right -= GAP
        dot = QRect(int(right - DOT), rect.center().y() - DOT // 2, DOT, DOT)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawEllipse(dot)
        right -= DOT + GAP * 2

    if pilot.player:
        chip_font = _font(10, QFont.Weight.Bold)
        chip_width = (
            QFontMetrics(chip_font).horizontalAdvance("PLAYER") + CHIP_PADDING * 2
        )
        right -= chip_width
        chip = QRect(
            int(right),
            rect.center().y() - CHIP_HEIGHT // 2,
            chip_width,
            CHIP_HEIGHT,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PLAYER_CHIP_BG)
        painter.drawRoundedRect(chip, CHIP_RADIUS, CHIP_RADIUS)
        painter.setFont(chip_font)
        painter.setPen(PLAYER_CHIP_TEXT)
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, "PLAYER")
        right -= GAP

    # The name takes whatever is left, elided in the middle: a long Russian name keeps
    # its beginning and its end, which is what tells two of them apart.
    name_font = _font(13, QFont.Weight.DemiBold)
    painter.setFont(name_font)
    painter.setPen(TEXT_SELECTED if selected else TEXT_PRIMARY)
    available = max(0, int(right - x))
    name = QFontMetrics(name_font).elidedText(
        pilot.name, Qt.TextElideMode.ElideMiddle, available
    )
    painter.drawText(int(x), baseline, name)

    painter.restore()


def row_width_hint(squadron: Any) -> int:
    """Wide enough for the longest name in the squadron plus everything beside it."""
    metrics = QFontMetrics(_font(13, QFont.Weight.DemiBold))
    longest = 0
    for pilot in getattr(squadron, "available_pilots", []) or []:
        longest = max(longest, metrics.horizontalAdvance(pilot.name))
    # stars + rank + name + PLAYER + morale, with the gaps between them.
    return int(longest) + 260


class PilotItemDelegate(QStyledItemDelegate):
    """Paints the rows of the pilot drop-down."""

    def __init__(
        self,
        squadron: Any,
        parent: Optional[QWidget] = None,
        affinity_of: Optional[Callable[[Pilot], Optional[float]]] = None,
    ) -> None:
        super().__init__(parent)
        self.squadron = squadron
        #: How well this man would get on with the rest of the crew, when whoever owns
        #: the list knows. The delegate never learns what a flight is.
        self.affinity_of = affinity_of

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        pilot = index.data(Qt.ItemDataRole.UserRole)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.fillRect(option.rect, SELECTED_FILL)
        elif hovered:
            painter.fillRect(option.rect, HOVER_FILL)

        if pilot is None and index.data(Qt.ItemDataRole.DisplayRole) == "No aircraft":
            painter.save()
            painter.setFont(_font(12))
            painter.setPen(MUTED)
            painter.drawText(
                option.rect.adjusted(LEFT, 0, -LEFT, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "No aircraft",
            )
            painter.restore()
            return

        paint_pilot(
            painter,
            option.rect,
            pilot,
            self.squadron,
            selected,
            affinity=self.affinity_of(pilot) if self.affinity_of else None,
        )


class PaintedPilotCombo(QComboBox):
    """A combo that draws its closed state with the same painter as its popup.

    Qt draws a combo's current item as plain text, which is why the roster and the
    selector could never look alike. Overriding the paint puts the frame and the arrow
    through the style as usual and then draws the row into the space that is left.
    """

    def __init__(
        self,
        squadron: Any,
        parent: Optional[QWidget] = None,
        affinity_of: Optional[Callable[[Pilot], Optional[float]]] = None,
    ) -> None:
        super().__init__(parent)
        self.squadron = squadron
        self.affinity_of = affinity_of

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        area = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        pilot = self.currentData()
        if pilot is None and self.currentText() == "No aircraft":
            painter.setFont(_font(12))
            painter.setPen(MUTED)
            painter.drawText(
                area.adjusted(LEFT, 0, -LEFT, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "No aircraft",
            )
            return
        paint_pilot(
            painter,
            area,
            pilot,
            self.squadron,
            affinity=self.affinity_of(pilot) if self.affinity_of else None,
        )
