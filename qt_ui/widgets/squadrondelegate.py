"""Row painting for the Air Wing squadron list.

The list used to paint four blocks of identical 12pt text — squadron and base on
the left, aircraft type and strength right-aligned on the far side of a 1200px
row — which made looking for an airframe a read rather than a scan. Here the
type is the only large, bold text and sits on a fixed rail at x=120, so the
types line up in one column the eye can run down.

Kept apart from `TwoColumnRowDelegate`, which several other lists share.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from game.ato.flighttype import FlightType
from game.squadrons import Squadron, friendship
from qt_ui.models import AirWingModel

ROW_HEIGHT = 48
SEPARATOR_Y = 47

#: A grouped row loses the column its group already names, so it can be shorter.
GROUPED_ROW_HEIGHT = 44
GROUP_HEADER_HEIGHT = 28

#: Set by the model on its group-header rows: (label, member count).
GroupHeaderRole = Qt.ItemDataRole.UserRole + 1

ICON_X = 14
ICON_Y = 12
ICON_SIZE = QSize(91, 24)

#: Baselines measured from the top of the row.
LINE_1 = 21
LINE_2 = 37

COL_TYPE_X = 120
COL_TYPE_WIDTH = 320
COL_BASE_X = 460
COL_BASE_WIDTH = 250
COL_CHIP_X = 730
CHIP_Y = 15
CHIP_HEIGHT = 18
CHIP_RADIUS = 4
RIGHT_MARGIN = 14

SELECTION_BAR = QRect(0, 0, 3, ROW_HEIGHT)

HOVER_FILL = QColor("#1A2A38")
SELECTED_FILL = QColor("#1E3A52")
SEPARATOR = QColor("#1D2731")
ACCENT = QColor("#8FC3F0")
HOVER_BAR = QColor("#3F5D73")
AMBER = QColor("#E0A86B")
GREEN = QColor("#86C39A")
RUST = QColor("#C08A72")
SHIP_MARKER = QColor("#6E93B0")

TEXT_SELECTED = QColor("#FFFFFF")
TEXT_PRIMARY = QColor("#F2F7FA")
TEXT_BASE = QColor("#D3DFE8")
TEXT_SECONDARY = QColor("#B7C6D2")
TEXT_TERTIARY = QColor("#8E9DAA")
TEXT_LABEL = QColor("#7C8B99")
TEXT_MUTED = QColor("#6B7A87")
GROUP_HEADER_FILL = QColor("#182734")
GROUP_HEADER_TEXT = QColor("#BEDCF6")

CHIP_ON_SELECTED = QColor("#2B4A66")

#: The family a task belongs to. CHIP_TASKS below gives each task its own colour
#: inside its family's band of the wheel, so the hue still answers "what is this
#: for" at a glance while two air-to-ground tasks no longer paint the same.
AIR_TO_AIR = {
    FlightType.BARCAP,
    FlightType.TARCAP,
    FlightType.ESCORT,
    FlightType.INTERCEPTION,
    FlightType.SWEEP,
}
AIR_TO_GROUND = {
    FlightType.STRIKE,
    FlightType.CAS,
    FlightType.SEAD,
    FlightType.DEAD,
    FlightType.ANTISHIP,
    FlightType.BAI,
    FlightType.SEAD_ESCORT,
    FlightType.SEAD_SWEEP,
    FlightType.OCA_RUNWAY,
    FlightType.OCA_AIRCRAFT,
    FlightType.ARMED_RECON,
}
SUPPORT = {
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.TRANSPORT,
    FlightType.FERRY,
    FlightType.AIR_ASSAULT,
    FlightType.RECOVERY,
}

CHIP_FAMILIES = {
    "air": (QColor("#22384A"), ACCENT),
    "ground": (QColor("#3B2D21"), AMBER),
    "support": (QColor("#23372D"), GREEN),
    "other": (QColor("#26343F"), QColor("#9FADB9")),
}
CHIP_DEPLETED = (QColor("#2E2723"), QColor("#9A8168"))

#: Hues spaced around the wheel with the families kept contiguous, at the saturation
#: and lightness the amber chip already used. Every cross-family pair is at least 11
#: dE76 apart; the pairs closer than that are all inside one family -- the SEAD three,
#: the two OCA -- where looking alike is the point.
CHIP_TASKS: dict[FlightType, tuple[QColor, QColor]] = {
    FlightType.STRIKE: (QColor("#38211E"), QColor("#E17970")),
    FlightType.OCA_AIRCRAFT: (QColor("#38251E"), QColor("#E18E70")),
    FlightType.OCA_RUNWAY: (QColor("#38291E"), QColor("#E19F70")),
    FlightType.CAS: (QColor("#382D1E"), QColor("#E1B070")),
    FlightType.BAI: (QColor("#38321E"), QColor("#E1C470")),
    FlightType.ARMED_RECON: (QColor("#37381E"), QColor("#DDE170")),
    FlightType.AIR_ASSAULT: (QColor("#2E381E"), QColor("#B2E170")),
    FlightType.TRANSPORT: (QColor("#25381E"), QColor("#8CE170")),
    FlightType.AEWC: (QColor("#1E3824"), QColor("#70E186")),
    FlightType.FERRY: (QColor("#1E382C"), QColor("#70E1AC")),
    FlightType.REFUELING: (QColor("#1E3832"), QColor("#70E1C6")),
    FlightType.RECOVERY: (QColor("#1E3838"), QColor("#70E1DF")),
    FlightType.ANTISHIP: (QColor("#1E3338"), QColor("#70CAE1")),
    FlightType.TARCAP: (QColor("#1E2E38"), QColor("#70B5E1")),
    FlightType.BARCAP: (QColor("#1E2A38"), QColor("#70A1E1")),
    FlightType.ESCORT: (QColor("#1E2438"), QColor("#708AE1")),
    FlightType.INTERCEPTION: (QColor("#1E1E38"), QColor("#7070E1")),
    FlightType.SWEEP: (QColor("#251E38"), QColor("#8E70E1")),
    FlightType.SEAD_ESCORT: (QColor("#301E38"), QColor("#BB70E1")),
    FlightType.SEAD_SWEEP: (QColor("#351E38"), QColor("#D270E1")),
    FlightType.SEAD: (QColor("#381E37"), QColor("#E170D9")),
    FlightType.DEAD: (QColor("#381E2E"), QColor("#E170B2")),
}


def chip_colours(task: FlightType) -> tuple[QColor, QColor]:
    """Fill and ink for a task's chip, falling back to its family's pair."""
    return CHIP_TASKS.get(task, CHIP_FAMILIES[chip_family(task)])


def chip_family(task: FlightType) -> str:
    if task in AIR_TO_AIR:
        return "air"
    if task in AIR_TO_GROUND:
        return "ground"
    if task in SUPPORT:
        return "support"
    return "other"


def split_aircraft_name(name: str) -> tuple[str, str]:
    """ "F-14A Tomcat (Block 135-GR Late)" -> ("F-14A Tomcat", "Block 135-GR Late").

    The base name is what you are hunting for; the variant is what you check once
    you have found it, so they are painted at different weights and the variant
    is the first thing to elide.
    """
    start = name.find("(")
    if start == -1 or not name.rstrip().endswith(")"):
        return name, ""
    return name[:start].strip(), name[start + 1 : name.rstrip().rfind(")")].strip()


class SquadronDelegate(QStyledItemDelegate):
    def __init__(self, air_wing_model: AirWingModel) -> None:
        super().__init__()
        self.air_wing_model = air_wing_model
        #: None, "type" or "base". A grouped column is left to the header.
        self.grouping: Optional[str] = None
        # Row geometry for the frame being painted. Rows vary in height once
        # grouping is on, and painting is synchronous, so the baselines live
        # here rather than being threaded through every paint helper.
        self._line_1 = LINE_1
        self._line_2 = LINE_2

    @staticmethod
    def squadron(index: QModelIndex) -> Optional[Squadron]:
        # A proxy can hand us a group-header row, which carries no squadron.
        squadron = index.data(AirWingModel.SquadronRole)
        return squadron if isinstance(squadron, Squadron) else None

    @staticmethod
    def _font(
        option: QStyleOptionViewItem, pixels: float, weight: QFont.Weight
    ) -> QFont:
        font = QFont(option.font)
        font.setPixelSize(int(pixels))
        font.setWeight(weight)
        return font

    def row_height(self, index: QModelIndex) -> int:
        if index.data(GroupHeaderRole) is not None:
            return GROUP_HEADER_HEIGHT
        if self.grouping is not None:
            return GROUPED_ROW_HEIGHT
        return ROW_HEIGHT

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.row_height(index))

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        header = index.data(GroupHeaderRole)
        if header is not None:
            self._paint_group_header(painter, option, header)
            return

        squadron = self.squadron(index)
        if squadron is None:
            super().paint(painter, option, index)
            return

        height = self.row_height(index)
        # Both baselines shift up together on the shorter grouped row.
        self._line_1 = LINE_1 - (ROW_HEIGHT - height) // 2
        self._line_2 = LINE_2 - (ROW_HEIGHT - height)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        depleted = squadron.owned_aircraft == 0

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(option.rect.topLeft())
        width = option.rect.width()

        if selected:
            painter.fillRect(QRect(0, 0, width, height), SELECTED_FILL)
            painter.fillRect(QRect(0, 0, 3, height), ACCENT)
        elif hovered:
            painter.fillRect(QRect(0, 0, width, height), HOVER_FILL)
            painter.fillRect(QRect(0, 0, 3, height), HOVER_BAR)
        painter.fillRect(QRect(0, height - 1, width, 1), SEPARATOR)

        self._paint_icon(painter, index, depleted)
        self._paint_type(painter, option, squadron, selected, depleted)
        self._paint_base(painter, option, squadron, selected, depleted)
        self._paint_task_chip(painter, option, squadron, selected, depleted)
        self._paint_cohesion(painter, option, squadron)
        self._paint_strength(painter, option, squadron, width, selected, depleted)

        painter.restore()

    def _paint_icon(
        self, painter: QPainter, index: QModelIndex, depleted: bool
    ) -> None:
        icon: Optional[QIcon] = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is None:
            return
        painter.save()
        if depleted:
            # A squadron with no aircraft recedes rather than shouting.
            painter.setOpacity(0.22)
        icon.paint(
            painter,
            QRect(
                ICON_X,
                self._line_1 - ICON_SIZE.height() // 2 - 3,
                ICON_SIZE.width(),
                ICON_SIZE.height(),
            ),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        painter.restore()

    def _paint_type(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
        selected: bool,
        depleted: bool,
    ) -> None:
        if self.grouping == "type":
            # The header already names the airframe, so the rail is free for the
            # identifier you actually double-click.
            font = self._font(option, 14, QFont.Weight.DemiBold)
            metrics = QFontMetrics(font)
            painter.setFont(font)
            if selected:
                painter.setPen(TEXT_SELECTED)
            else:
                painter.setPen(TEXT_TERTIARY if depleted else TEXT_PRIMARY)
            name = metrics.elidedText(
                squadron.name, Qt.TextElideMode.ElideRight, COL_TYPE_WIDTH
            )
            painter.drawText(COL_TYPE_X, self._line_1, name)
            if squadron.nickname:
                advance = metrics.horizontalAdvance(name)
                remaining = COL_TYPE_WIDTH - advance - 8
                if remaining > 24:
                    nick_font = self._font(option, 12.5, QFont.Weight.Normal)
                    nick_metrics = QFontMetrics(nick_font)
                    painter.setFont(nick_font)
                    painter.setPen(TEXT_LABEL)
                    painter.drawText(
                        COL_TYPE_X + advance + 8,
                        self._line_1,
                        nick_metrics.elidedText(
                            f'"{squadron.nickname}"',
                            Qt.TextElideMode.ElideRight,
                            remaining,
                        ),
                    )
            return

        base_name, variant = split_aircraft_name(squadron.aircraft.display_name)

        name_font = self._font(option, 15, QFont.Weight.DemiBold)
        variant_font = self._font(option, 12, QFont.Weight.Normal)
        metrics = QFontMetrics(name_font)

        colour = TEXT_SELECTED if selected else TEXT_PRIMARY
        if depleted and not selected:
            colour = TEXT_TERTIARY

        # The variant elides first: a long block designation must not push the
        # name off the rail the whole column is built on.
        name_width = min(metrics.horizontalAdvance(base_name), COL_TYPE_WIDTH)
        painter.setFont(name_font)
        painter.setPen(colour)
        painter.drawText(
            COL_TYPE_X,
            self._line_1,
            metrics.elidedText(base_name, Qt.TextElideMode.ElideRight, COL_TYPE_WIDTH),
        )

        if variant:
            remaining = COL_TYPE_WIDTH - name_width - 8
            if remaining > 24:
                variant_metrics = QFontMetrics(variant_font)
                painter.setFont(variant_font)
                painter.setPen(TEXT_LABEL)
                painter.drawText(
                    COL_TYPE_X + name_width + 8,
                    self._line_1,
                    variant_metrics.elidedText(
                        variant, Qt.TextElideMode.ElideRight, remaining
                    ),
                )

        squadron_font = self._font(option, 12.5, QFont.Weight.Normal)
        squadron_metrics = QFontMetrics(squadron_font)
        painter.setFont(squadron_font)
        if selected:
            painter.setPen(TEXT_SELECTED)
        else:
            painter.setPen(TEXT_MUTED if depleted else TEXT_SECONDARY)
        name = squadron.name
        name_advance = min(squadron_metrics.horizontalAdvance(name), COL_TYPE_WIDTH)
        painter.drawText(
            COL_TYPE_X,
            self._line_2,
            squadron_metrics.elidedText(
                name, Qt.TextElideMode.ElideRight, COL_TYPE_WIDTH
            ),
        )
        if squadron.nickname:
            remaining = COL_TYPE_WIDTH - name_advance - 6
            if remaining > 24:
                painter.setPen(TEXT_LABEL)
                painter.drawText(
                    COL_TYPE_X + name_advance + 6,
                    self._line_2,
                    squadron_metrics.elidedText(
                        f'"{squadron.nickname}"',
                        Qt.TextElideMode.ElideRight,
                        remaining,
                    ),
                )

    def _paint_base(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
        selected: bool,
        depleted: bool,
    ) -> None:
        x = COL_BASE_X
        if self.grouping == "base":
            self._paint_transfer(painter, option, squadron)
            return
        if squadron.location.is_fleet:
            # A 6px diamond beats the word "carrier": cheap to paint, groupable
            # by eye, and it survives a long ship name.
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(SHIP_MARKER)
            painter.translate(COL_BASE_X + 3, 18)
            painter.rotate(45)
            painter.drawRect(-3, -3, 6, 6)
            painter.restore()
            x = COL_BASE_X + 14

        font = self._font(option, 13, QFont.Weight.Medium)
        metrics = QFontMetrics(font)
        painter.setFont(font)
        if selected:
            painter.setPen(TEXT_SELECTED)
        else:
            painter.setPen(TEXT_MUTED if depleted else TEXT_BASE)
        width = COL_BASE_WIDTH - (x - COL_BASE_X)
        painter.drawText(
            x,
            self._line_1,
            metrics.elidedText(
                squadron.location.name, Qt.TextElideMode.ElideRight, width
            ),
        )

        self._paint_transfer(painter, option, squadron)

    def _paint_transfer(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
    ) -> None:
        if squadron.destination is not None:
            # Amber is the only warm colour in the list, so pending moves are
            # countable at a glance, and the row height never changes.
            transfer_font = self._font(option, 11.5, QFont.Weight.Normal)
            transfer_metrics = QFontMetrics(transfer_font)
            painter.setFont(transfer_font)
            painter.setPen(AMBER)
            painter.drawText(
                COL_BASE_X,
                self._line_2,
                transfer_metrics.elidedText(
                    f"→ transfer to {squadron.destination.name}",
                    Qt.TextElideMode.ElideRight,
                    COL_BASE_WIDTH,
                ),
            )

    def _paint_task_chip(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
        selected: bool,
        depleted: bool,
    ) -> None:
        label = squadron.primary_task.name.replace("_", " ").upper()
        font = self._font(option, 10, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(label) + 16
        chip_y = self._line_1 - CHIP_HEIGHT + 3

        if depleted:
            fill, text = CHIP_DEPLETED
        else:
            fill, text = chip_colours(squadron.primary_task)
        if selected:
            fill = CHIP_ON_SELECTED

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            COL_CHIP_X, chip_y, width, CHIP_HEIGHT, CHIP_RADIUS, CHIP_RADIUS
        )
        painter.restore()

        painter.setFont(font)
        painter.setPen(text)
        painter.drawText(
            QRect(COL_CHIP_X, chip_y, width, CHIP_HEIGHT),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def _paint_group_header(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        header: tuple[str, int],
    ) -> None:
        label, count = header
        painter.save()
        painter.translate(option.rect.topLeft())
        width = option.rect.width()
        painter.fillRect(QRect(0, 0, width, GROUP_HEADER_HEIGHT), GROUP_HEADER_FILL)

        # No silhouette here: the rows underneath already carry it, larger.
        # Grouped by type, the header *is* the thing being scanned for, so it
        # gets the size the type has when the list is ungrouped.
        font = self._font(option, 15, QFont.Weight.Bold)
        metrics = QFontMetrics(font)
        painter.setFont(font)
        painter.setPen(GROUP_HEADER_TEXT)
        painter.drawText(COL_TYPE_X, 19, label)

        count_font = self._font(option, 11, QFont.Weight.Normal)
        painter.setFont(count_font)
        painter.setPen(TEXT_MUTED)
        painter.drawText(
            COL_TYPE_X + metrics.horizontalAdvance(label) + 16,
            19,
            f"{count} squadron" + ("" if count == 1 else "s"),
        )
        painter.restore()

    def _paint_cohesion(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
    ) -> None:
        """How well the squadron gets on, under its task chip.

        The word rather than the number, in the same band colour the pilot picker
        washes its rows with, so the two lists speak one language. Nothing at all for a
        squadron nobody needs to think about, which is what Neutral is.
        """
        value = squadron.cohesion
        if value is None:
            return
        band = friendship.band(value, squadron.settings)
        if band.colour is None:
            return
        painter.setFont(self._font(option, 11.5, QFont.Weight.Normal))
        painter.setPen(QColor(band.colour))
        painter.drawText(COL_CHIP_X, self._line_2, band.name)

    def _paint_strength(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        squadron: Squadron,
        row_width: int,
        selected: bool,
        depleted: bool,
    ) -> None:
        right = row_width - RIGHT_MARGIN

        label_font = self._font(option, 11.5, QFont.Weight.Normal)
        label_metrics = QFontMetrics(label_font)
        painter.setFont(label_font)
        painter.setPen(TEXT_LABEL)
        label_width = label_metrics.horizontalAdvance("aircraft")
        painter.drawText(right - label_width, self._line_1, "aircraft")

        # The aircraft count is the scarce number, so it leads at 15px.
        count_font = self._font(option, 15, QFont.Weight.DemiBold)
        count_metrics = QFontMetrics(count_font)
        count = str(squadron.owned_aircraft)
        count_colour = (
            RUST if depleted else (TEXT_SELECTED if selected else TEXT_PRIMARY)
        )
        painter.setFont(count_font)
        painter.setPen(count_colour)
        painter.drawText(
            right - label_width - 5 - count_metrics.horizontalAdvance(count),
            self._line_1,
            count,
        )

        pilots_font = self._font(option, 12, QFont.Weight.Normal)
        pilots_metrics = QFontMetrics(pilots_font)
        # Both numbers: what you can send, out of what is on the books. The bare
        # headcount counted the wounded, the ones away and the ones who will not fly,
        # so a squadron with nobody to send still read "16 pilots".
        fit = len(squadron.fit_for_duty)
        living = len(squadron.living_pilots)
        pilots = f"{fit} pilots" if fit == living else f"{fit}/{living} pilots"
        painter.setFont(pilots_font)
        painter.setPen(TEXT_TERTIARY)
        pilots_width = pilots_metrics.horizontalAdvance(pilots)
        painter.drawText(right - pilots_width, self._line_2, pilots)

        ready = squadron.untasked_crewed_aircraft
        if not ready:
            # The only actionable number in the row, so it is the only green
            # thing — and it disappears rather than showing a zero.
            return
        ready_font = self._font(option, 12, QFont.Weight.DemiBold)
        ready_metrics = QFontMetrics(ready_font)
        text = f"{ready} ready"
        painter.setFont(ready_font)
        painter.setPen(GREEN)
        painter.drawText(
            right - pilots_width - 8 - ready_metrics.horizontalAdvance(text),
            self._line_2,
            text,
        )
