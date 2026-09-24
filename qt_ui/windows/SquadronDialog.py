import logging
from copy import deepcopy
from functools import partial
from typing import Callable, Iterator, Optional, Type

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QRectF,
    QSettings,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QHelpEvent,
    QPainter,
    QPalette,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from dcs.unittype import FlyingType

from game.ato.flightplans.custom import CustomFlightPlan
from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType
from game.dcs.aircrafttype import AircraftType
from game.settings import Settings
from game.squadrons import friendship
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.experience import turns_phrase
from game.purchaseadapter import AircraftPurchaseAdapter, TransactionError
from game.server import EventStream
from game.sim import GameUpdateEvents
from game.squadrons import Pilot, Squadron
from game.theater import ConflictTheater, ControlPoint, ParkingType
from game.squadrons.pilot import PilotStatus
from qt_ui.delegates import painter_context
from game.squadrons.morale import RANK_LEVELS
from qt_ui.widgets.pilotrow import (
    MORALE_COLOURS,
    affinity_tint,
    MORALE_LABEL_OVERRIDE,
    MORALE_LABEL_OVERRIDE_SELECTED,
)
from qt_ui.rankstars import (
    STAR_EMPTY,
    STAR_EMPTY_DIMMED,
    STAR_EMPTY_SELECTED,
    STAR_FILLED,
    STAR_FILLED_DIMMED,
    STAR_FILLED_SELECTED,
    paint_rank_stars,
)
from qt_ui.errorreporter import report_errors
from qt_ui.models import AtoModel, SquadronModel
from qt_ui.simcontroller import SimController
from qt_ui.uiconstants import app_settings, AIRCRAFT_ICONS
from qt_ui.dialogs import open_once
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.pilot import PilotDialog
from qt_ui.widgets.combos.QSquadronLiverySelector import SquadronLiverySelector
from qt_ui.widgets.combos.primarytaskselector import PrimaryTaskSelector

#: Everything the redesign paints. The rest of the palette comes from the Air Wing
#: list, which these rows have to sit beside without looking like a different program.
ROW_SELECTED = "#1E3A52"
ROW_HOVERED = "#1A2A38"
ROW_SEPARATOR = "#1D2731"
BAR_HOVERED = "#3F5D73"
BAR_SELECTED = "#8FC3F0"
#: The selected row also gets its own outline, because with friendship on every other
#: row carries an affinity wash of its own and a thin bar was lost among them.
BAR_WIDTH_HOVERED = 3
BAR_WIDTH_SELECTED = 5

NAME = "#F2F7FA"
NAME_SELECTED = "#FFFFFF"
RANK_NAME = "#B7C6D2"
RANK_NAME_SELECTED = "#D3DFE8"
MUTED = "#8E9DAA"
MUTED_SELECTED = "#9FB3C2"
DIM = "#7C8B99"
DOT_SEPARATOR = "#4F6070"
DOT_SEPARATOR_SELECTED = "#6E93B0"

PLAYER_CHIP_FILL = "#22384A"
PLAYER_CHIP_TEXT = "#8FC3F0"

WARNING_ADVISORY = "#E0A86B"
WARNING_BLOCKING = "#D9645E"

AVAILABLE = "#5F8A6C"
AVAILABLE_SELECTED = "#9BD1AD"
WOUNDED = "#C08A72"
WOUNDED_SELECTED = "#E0A86B"
WOUNDED_DETAIL = "#8A6C5C"
ON_LEAVE = "#8FC3F0"
ON_LEAVE_SELECTED = "#BEDCF6"
ON_LEAVE_DETAIL = "#6E93B0"

#: The morale ramp lives with the row painter now, so the roster here and the pilot
#: selector in the flight dialog cannot drift apart -- they draw the same row.

FATE_CHIPS = {
    PilotStatus.Dead: ("KIA", "#3B2523", "#D9645E"),
    PilotStatus.Deserted: ("DESERTED", "#3B2D21", "#E0A86B"),
    PilotStatus.Discharged: ("DISCHARGED", "#26343F", "#9FADB9"),
}

#: The form ends here and the roster takes the rest of the window.
LEFT_PANEL_WIDTH = 574

PILOT_ROW_HEIGHT = 52
FALLEN_ROW_HEIGHT = 36

#: The left column ends here, and the notes column starts here. Where it *ends* is not
#: fixed: it runs to wherever the morale and status block begins, so widening the window
#: gives the warnings the room rather than leaving them clipped at a hard stop.
COLUMN_A_RIGHT = 290
NOTES_LEFT = 300
#: What the right-hand block needs at its widest ("Wounded · 4 turns to recover").
STATE_BLOCK_WIDTH = 200
#: Below this the notes are unreadable anyway, so let them clip rather than collide.
NOTES_MIN_WIDTH = 60
MARGIN = 14

#: Wide enough that the longest note fits without being shortened.
#:
#: A 1200-wide window leaves the notes 35 px of the roster's 564 -- the identity column
#: takes NOTES_LEFT and the morale block STATE_BLOCK_WIDTH -- so "Requests leave · 2
#: turns" (113 px) was cut to "Requests l...". The longest note, "Will refuse to fly next
#: mission", wants about 142 px, and the roster loses roughly 636 px of the window to the
#: form beside it and its own margins: 315 + 142 + 200 + 14 + 636, rounded up.
MIN_DIALOG_WIDTH = 1320
MIN_DIALOG_HEIGHT = 760


def _font(
    size: float, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False
) -> QFont:
    font = QFont("Consolas") if mono else QFont()
    font.setPixelSize(int(size))
    font.setWeight(weight)
    return font


class PilotRowPainter:
    """What both delegates share: the squadron and the palette.

    Deliberately without an ``__init__``: Qt's constructor walks the MRO, so a second
    one here would be called with no arguments. Each delegate sets the model itself.

    """

    squadron_model: SquadronModel

    @property
    def squadron(self) -> Squadron:
        return self.squadron_model.squadron

    @property
    def morale_in_play(self) -> bool:
        return bool(self.squadron.morale_in_play)

    def morale_shown_for(self, pilot: Pilot) -> bool:
        """The player has no morale to show: he knows how his own week went."""
        return self.morale_in_play and pilot.has_morale

    @property
    def settings(self) -> Settings:
        """The campaign's own morale bands, which it is free to have moved."""
        return self.squadron.settings

    def rank_of(self, pilot: Pilot) -> tuple[int, str]:
        """His rung, and what his own air force calls it."""
        rank = self.squadron.pilot_rank(pilot)
        level = morale_rules.rank_level(self.squadron.pilot_skill(pilot))
        return level, "" if rank is None else rank.name

    @staticmethod
    def missions_of(pilot: Pilot) -> tuple[str, str]:
        flown = pilot.record.missions_flown
        return str(flown), "mission" if flown == 1 else "missions"


class PilotDelegate(QStyledItemDelegate, PilotRowPainter):
    """One living pilot in three zones: identity, pending actions, and state.

    The state is always on the right edge so the column can be scanned.

    """

    def __init__(self, squadron_model: SquadronModel) -> None:
        super().__init__()
        self.squadron_model = squadron_model
        #: The pilot the list is being read from the point of view of, when there is
        #: one. The rows below him are washed with what *he* thinks of them -- his own
        #: direction, because the question a roster answers is who he would fly with.
        self.anchor: Optional[Pilot] = None

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, PILOT_ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        pilot = self.squadron_model.pilot_at_index(index)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        with painter_context(painter):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(rect.topLeft())
            width = rect.width()

            tint = self._affinity_tint(pilot)
            if tint is not None:
                painter.fillRect(0, 0, width, PILOT_ROW_HEIGHT, tint)
            if selected:
                painter.fillRect(0, 0, width, PILOT_ROW_HEIGHT, QColor(ROW_SELECTED))
                painter.fillRect(
                    0, 0, BAR_WIDTH_SELECTED, PILOT_ROW_HEIGHT, QColor(BAR_SELECTED)
                )
            elif hovered:
                painter.fillRect(0, 0, width, PILOT_ROW_HEIGHT, QColor(ROW_HOVERED))
                painter.fillRect(
                    0, 0, BAR_WIDTH_HOVERED, PILOT_ROW_HEIGHT, QColor(BAR_HOVERED)
                )
            painter.fillRect(0, 51, width, 1, QColor(ROW_SEPARATOR))
            if selected:
                # After the separator, which runs along the row's bottom edge and would
                # otherwise paint over it.
                self._outline(painter, width)

            self._paint_identity(painter, pilot, selected)
            self._paint_notes(painter, pilot, width)
            self._paint_state(painter, pilot, width, selected)

    @staticmethod
    def _outline(painter: QPainter, width: int) -> None:
        """A one-pixel box around the row, drawn square so it sits on the separator."""
        edge = QColor(BAR_SELECTED)
        painter.fillRect(0, 0, width, 1, edge)
        painter.fillRect(0, PILOT_ROW_HEIGHT - 1, width, 1, edge)
        painter.fillRect(width - 1, 0, 1, PILOT_ROW_HEIGHT, edge)

    def _affinity_tint(self, pilot: Pilot) -> Optional[QColor]:
        """Background wash showing what the selected pilot thinks of this one.

        Nothing for the selected pilot himself, nothing when none is selected, and
        nothing for a pair at Neutral.

        """
        anchor = self.anchor
        if anchor is None or anchor is pilot:
            return None
        squadron = self.squadron_model.squadron
        if not getattr(squadron, "friendship_in_play", False):
            return None
        return affinity_tint(
            friendship.feeling(anchor, pilot), settings=squadron.settings
        )

    # --- who he is ----------------------------------------------------------

    def _paint_identity(self, painter: QPainter, pilot: Pilot, selected: bool) -> None:
        painter.setFont(_font(14, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        chip_room = 62 if pilot.player else 0
        name = metrics.elidedText(
            pilot.name,
            Qt.TextElideMode.ElideRight,
            COLUMN_A_RIGHT - MARGIN - chip_room,
        )
        painter.setPen(QColor(NAME_SELECTED if selected else NAME))
        painter.drawText(MARGIN, 22, name)

        if pilot.player:
            self._paint_player_chip(
                painter, MARGIN + metrics.horizontalAdvance(name) + 8
            )

        # Line two: five slots of rank, the name his air force gives it, then what he
        # has flown. The stars are a bar you scan; the name is what he is called.
        level, rank_name = self.rank_of(pilot)
        x = float(MARGIN)
        x += paint_rank_stars(
            painter,
            x,
            42,
            level,
            filled=STAR_FILLED_SELECTED if selected else STAR_FILLED,
            empty=STAR_EMPTY_SELECTED if selected else STAR_EMPTY,
        )
        x += 6

        painter.setFont(_font(12))
        metrics = painter.fontMetrics()
        count, word = self.missions_of(pilot)
        tail = metrics.horizontalAdvance(f" · {count} {word}")
        if rank_name:
            rank_name = metrics.elidedText(
                rank_name,
                Qt.TextElideMode.ElideRight,
                max(0, int(COLUMN_A_RIGHT - x - tail)),
            )
            painter.setPen(QColor(RANK_NAME_SELECTED if selected else RANK_NAME))
            painter.drawText(int(x), 42, rank_name)
            x += metrics.horizontalAdvance(rank_name) + 6

        painter.setPen(QColor(DOT_SEPARATOR_SELECTED if selected else DOT_SEPARATOR))
        painter.drawText(int(x), 42, "·")
        x += metrics.horizontalAdvance("·") + 6

        painter.setFont(_font(12, mono=True))
        painter.setPen(QColor(MUTED_SELECTED if selected else MUTED))
        painter.drawText(int(x), 42, count)
        x += painter.fontMetrics().horizontalAdvance(count) + 4
        painter.setFont(_font(12))
        painter.setPen(QColor(MUTED_SELECTED if selected else DIM))
        painter.drawText(int(x), 42, word)

    def _paint_player_chip(self, painter: QPainter, x: float) -> None:
        """Almost every pilot is AI. Painting "AI" forty times is noise; this is not."""
        painter.setFont(_font(9.5, QFont.Weight.Bold))
        label = "PLAYER"
        width = painter.fontMetrics().horizontalAdvance(label) + 12
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PLAYER_CHIP_FILL))
        painter.drawRoundedRect(QRectF(x, 9, width, 16), 3, 3)
        painter.setPen(QColor(PLAYER_CHIP_TEXT))
        painter.drawText(QRectF(x, 9, width, 16), Qt.AlignmentFlag.AlignCenter, label)

    # --- what wants a decision ----------------------------------------------

    def _paint_notes(self, painter: QPainter, pilot: Pilot, width: int) -> None:
        note = self.note_for(pilot)
        if note is None:
            return
        text, colour = note
        painter.setPen(QColor(colour))
        painter.setFont(_font(11))
        painter.drawText(NOTES_LEFT, 30, "▲")
        x = NOTES_LEFT + painter.fontMetrics().horizontalAdvance("▲") + 6
        painter.setFont(_font(11.5))
        room = max(NOTES_MIN_WIDTH, width - MARGIN - STATE_BLOCK_WIDTH - x)
        text = painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, int(room)
        )
        painter.drawText(int(x), 30, text)

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> bool:
        """The whole row as text, for the tooltip.

        A painted row has no text for Qt to offer, so it is built here, which also keeps
        the rank name and the warning readable when the row elides them.

        """
        if event.type() != QEvent.Type.ToolTip or not index.isValid():
            return super().helpEvent(event, view, option, index)
        pilot = self.squadron_model.pilot_at_index(index)
        level, rank_name = self.rank_of(pilot)
        count, word = self.missions_of(pilot)
        lines = [f"<b>{pilot.name}</b>{' — player' if pilot.player else ''}"]
        if rank_name:
            lines.append(f"{rank_name} ({level} of {RANK_LEVELS})")
        lines.append(f"{count} {word} flown")
        if self.morale_shown_for(pilot):
            state = morale_rules.morale_state(pilot.morale, self.settings)
            lines.append(f"Morale: {state.name}")
        if pilot.hardened and hardening.in_play(self.settings):
            # It never comes off, so a high figure on a man whose morale is fine is a
            # man who has already been through it and come out the other side.
            relief = round(hardening.morale_relief(pilot.hardened, self.settings) * 100)
            lines.append(
                f"Hardened: {pilot.hardened} of {hardening.ceiling(self.settings)}"
                f" — knocks land {relief}% lighter"
            )
        status, _, detail, _ = self._status_of(pilot, False)
        lines.append(f"{status} {detail}".strip())
        note = self.note_for(pilot)
        if note is not None:
            lines.append(note[0])
        QToolTip.showText(event.globalPos(), "<br>".join(lines), view)
        return True

    def note_for(self, pilot: Pilot) -> Optional[tuple[str, str]]:
        """Anything the player can act on, as opposed to state he cannot change.

        A wound is state and belongs under morale; a leave request is a question for the
        player and belongs here.

        """
        if not self.morale_shown_for(pilot):
            return None
        if pilot.refuses_to_fly:
            return "Will refuse to fly next mission", WARNING_BLOCKING
        # A man in a hospital bed is not asking for a rest, whatever flag a save made
        # before that rule still carries.
        if pilot.wants_leave and not pilot.wounded:
            asked = pilot.leave_turns_requested
            return (
                (
                    f"Requests leave · {turns_phrase(asked)}"
                    if asked
                    else "Requests leave"
                ),
                WARNING_ADVISORY,
            )
        if (
            pilot.morale < pilot.morale_last_turn
            and morale_rules.morale_state(pilot.morale, self.settings).severity
        ):
            return "Morale dropping — consider leave", WARNING_ADVISORY
        return None

    # --- how he is ----------------------------------------------------------

    def _paint_state(
        self, painter: QPainter, pilot: Pilot, width: int, selected: bool
    ) -> None:
        right = width - MARGIN
        if self.morale_shown_for(pilot):
            state = morale_rules.morale_state(pilot.morale, self.settings)
            dot = MORALE_COLOURS.get(state.name, MUTED)
            override = (
                MORALE_LABEL_OVERRIDE_SELECTED if selected else MORALE_LABEL_OVERRIDE
            )
            painter.setFont(_font(12, QFont.Weight.Medium))
            label_width = painter.fontMetrics().horizontalAdvance(state.name)
            painter.setPen(QColor(override.get(state.name, dot)))
            painter.drawText(int(right - label_width), 22, state.name)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(dot))
            painter.drawEllipse(QRectF(right - label_width - 14, 13, 8, 8))

        text, colour, detail, detail_colour = self._status_of(pilot, selected)
        painter.setFont(_font(11.5))
        metrics = painter.fontMetrics()
        full = f"{text} {detail}" if detail else text
        x = right - metrics.horizontalAdvance(full)
        painter.setPen(QColor(colour))
        painter.drawText(int(x), 42, text)
        if detail:
            painter.setPen(QColor(detail_colour))
            painter.drawText(int(x + metrics.horizontalAdvance(f"{text} ")), 42, detail)

    def _status_of(self, pilot: Pilot, selected: bool) -> tuple[str, str, str, str]:
        """What the game has decided about him. A wound outranks leave outranks fit."""
        if pilot.wounded:
            return (
                "Wounded",
                WOUNDED_SELECTED if selected else WOUNDED,
                f"· {turns_phrase(pilot.wounded_turns)} to recover",
                WOUNDED_DETAIL,
            )
        if pilot.on_leave:
            detail = (
                f"· {turns_phrase(pilot.leave_turns)} left" if pilot.leave_turns else ""
            )
            return (
                "On leave",
                ON_LEAVE_SELECTED if selected else ON_LEAVE,
                detail,
                ON_LEAVE_DETAIL,
            )
        return "Available", AVAILABLE_SELECTED if selected else AVAILABLE, "", ""


class FallenPilotDelegate(QStyledItemDelegate, PilotRowPainter):
    """The list of dead pilots: one line each, dimmed, and without morale.

    Dimmed so it does not compete with the roster above it.

    """

    def __init__(self, squadron_model: SquadronModel) -> None:
        super().__init__()
        self.squadron_model = squadron_model

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, FALLEN_ROW_HEIGHT)

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        pilot = self.squadron_model.pilot_at_index(index)
        rect = option.rect

        with painter_context(painter):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(rect.topLeft())
            width = rect.width()
            painter.fillRect(0, FALLEN_ROW_HEIGHT - 1, width, 1, QColor(ROW_SEPARATOR))

            painter.setFont(_font(13, QFont.Weight.DemiBold))
            painter.setPen(QColor(RANK_NAME))
            painter.drawText(MARGIN, 23, pilot.name)
            x = float(MARGIN + painter.fontMetrics().horizontalAdvance(pilot.name) + 8)

            level, rank_name = self.rank_of(pilot)
            x += paint_rank_stars(
                painter,
                x,
                23,
                level,
                filled=STAR_FILLED_DIMMED,
                empty=STAR_EMPTY_DIMMED,
            )
            if rank_name:
                x += 6
                painter.setFont(_font(12))
                painter.setPen(QColor(DIM))
                painter.drawText(int(x), 23, rank_name)

            count, word = self.missions_of(pilot)
            painter.setFont(_font(12, mono=True))
            painter.setPen(QColor(MUTED))
            painter.drawText(340, 23, count)
            after = 340 + painter.fontMetrics().horizontalAdvance(count) + 4
            painter.setFont(_font(12))
            painter.setPen(QColor(DIM))
            painter.drawText(after, 23, word)

            self._paint_fate(painter, pilot, width)

    @staticmethod
    def _paint_fate(painter: QPainter, pilot: Pilot, width: int) -> None:
        chip = FATE_CHIPS.get(pilot.status)
        if chip is None:
            return
        label, fill, text = chip
        painter.setFont(_font(10, QFont.Weight.Bold))
        chip_width = painter.fontMetrics().horizontalAdvance(label) + 16
        x = width - MARGIN - chip_width
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(x, 9, chip_width, 18), 4, 4)
        painter.setPen(QColor(text))
        painter.drawText(
            QRectF(x, 9, chip_width, 18), Qt.AlignmentFlag.AlignCenter, label
        )


class PilotList(QListView):
    """List view for displaying a squadron's pilots."""

    def __init__(self, squadron_model: SquadronModel, fallen: bool = False) -> None:
        super().__init__()
        self.squadron_model = squadron_model

        delegate: QStyledItemDelegate = (
            FallenPilotDelegate(squadron_model)
            if fallen
            else PilotDelegate(squadron_model)
        )
        self.setItemDelegate(delegate)
        self.setModel(self.squadron_model)
        self.selectionModel().setCurrentIndex(
            self.squadron_model.index(0, 0, QModelIndex()),
            QItemSelectionModel.SelectionFlag.Select,
        )

        if not fallen:
            # Picking a man out washes the rest of the list with what he thinks of
            # them, so a squadron's friendships can be read one pilot at a time.
            self.selectionModel().currentChanged.connect(self._follow_selection)
            self.selectionModel().selectionChanged.connect(
                lambda *_: self._follow_selection(
                    self.selectionModel().currentIndex(), QModelIndex()
                )
            )

            # The list opens with the first man current, and that happened before
            # the connections above, so nothing would have told the delegate.
            self._follow_selection(self.selectionModel().currentIndex(), QModelIndex())

        # The rows light up under the cursor, which needs the view to follow it.
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        if fallen:
            self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        else:
            # Sending nine men on leave one at a time, each with its own dialog asking
            # how long, is the kind of thing a squadron has every turn.
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def _follow_selection(self, current: QModelIndex, _previous: QModelIndex) -> None:
        delegate = self.itemDelegate()
        if not isinstance(delegate, PilotDelegate):
            return
        anchor = None
        if current.isValid() and self.selectionModel().hasSelection():
            anchor = self.squadron_model.pilot_at_index(current)
        if anchor is not delegate.anchor:
            delegate.anchor = anchor
            self.viewport().update()


class AutoAssignedTaskControls(QVBoxLayout):
    """The mission types this squadron is given automatically.

    Laid out in three columns: seventeen rows one per line ran the panel to about 560
    px, which left no room for the form beside the roster. All and None are provided
    because setting sixteen of seventeen by hand is tedious.

    """

    COLUMNS = 3

    def __init__(self, squadron_model: SquadronModel) -> None:
        super().__init__()
        self.squadron_model = squadron_model
        self.checkboxes: dict[FlightType, QCheckBox] = {}

        shortcuts = QHBoxLayout()
        shortcuts.setSpacing(6)
        for text, checked in (("All", True), ("None", False)):
            button = QPushButton(text)
            button.setStyleSheet(BUTTON_SECONDARY)
            button.setFixedHeight(22)
            button.clicked.connect(partial(self.set_every_task, checked))
            shortcuts.addWidget(button)
        shortcuts.addStretch()
        self.addLayout(shortcuts)

        def make_callback(toggled_task: FlightType) -> Callable[[bool], None]:
            def callback(checked: bool) -> None:
                self.on_toggled(toggled_task, checked)

            return callback

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self.addLayout(grid)

        row = column = 0
        for task in FlightType:
            if not self.squadron_model.squadron.capable_of(task):
                continue
            checkbox = QCheckBox(text=task.value)
            checkbox.setChecked(squadron_model.is_auto_assignable(task))
            checkbox.toggled.connect(make_callback(task))
            grid.addWidget(checkbox, row, column)
            self.checkboxes[task] = checkbox
            column += 1
            if column == self.COLUMNS:
                column = 0
                row += 1

    def set_every_task(self, checked: bool) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(checked)

    def on_toggled(self, task: FlightType, checked: bool) -> None:
        self.squadron_model.set_auto_assignable(task, checked)


class SquadronDestinationComboBox(QComboBox):
    def __init__(self, squadron: Squadron, theater: ConflictTheater) -> None:
        super().__init__()
        self.squadron = squadron
        self.theater = theater
        #: Bases with squadrons that don't fit, collected while building the
        #: combo so the dialog can show a single consolidated warning.
        self.parking_overflow: dict[str, list[tuple[Squadron, str]]] = {}

        parking_type = ParkingType().from_squadron(squadron)
        room = squadron.location.unclaimed_parking(parking_type)
        self.addItem(
            f"Remain at {squadron.location} (room for {room} more aircraft)",
            squadron.location,
        )
        selected_index: Optional[int] = None
        for idx, destination in enumerate(sorted(self.iter_destinations(), key=str), 1):
            if destination == squadron.destination:
                selected_index = idx
            room = self.calculate_parking_slots(
                destination, squadron.aircraft.dcs_unit_type
            )
            self.addItem(
                f"Transfer to {destination} (room for {room} more aircraft)",
                destination,
            )
            if room < squadron.owned_aircraft or room == 0:
                diff = squadron.owned_aircraft - room
                text = (
                    f"Transfer to {destination} not possible "
                    f"({diff} additional slots required)"
                )
                if squadron.owned_aircraft == 0 and room == 0:
                    text = (
                        f"Transfer to {destination} not possible "
                        f"(no fitting slots found)"
                    )
                self.setItemText(idx, text)
                self.model().item(idx).setEnabled(False)

        if squadron.owned_aircraft and not squadron.location.runway_is_operational():
            # Nothing takes off from a damaged runway, ferries included. An empty
            # squadron has nothing to fly out, so it can still move.
            why = (
                f"{squadron.location} has sunk"
                if squadron.location.sunk
                else f"the runway at {squadron.location} is damaged"
            )
            for idx in range(1, self.count()):
                self.setItemText(
                    idx, f"Transfer to {self.itemData(idx)} not possible ({why})"
                )
                self.model().item(idx).setEnabled(False)

        if squadron.destination is None:
            selected_index = 0

        if selected_index is not None:
            self.setCurrentIndex(selected_index)

    def iter_destinations(self) -> Iterator[ControlPoint]:
        size = self.squadron.expected_size_next_turn
        parking_type = ParkingType().from_squadron(self.squadron)
        for control_point in self.theater.control_points_for(self.squadron.player):
            if control_point == self.squadron.location:
                continue
            if not control_point.can_operate(self.squadron.aircraft):
                continue
            ac_type = self.squadron.aircraft.dcs_unit_type
            if (
                self.squadron.destination is not control_point
                and control_point.unclaimed_parking(parking_type) < size
                and self.calculate_parking_slots(control_point, ac_type) < size
            ):
                continue
            yield control_point

    def calculate_parking_slots(
        self, cp: ControlPoint, dcs_unit_type: Type[FlyingType]
    ) -> int:
        if cp.dcs_airport:
            ap = deepcopy(cp.dcs_airport)
            overflow = []

            parking_type = ParkingType(
                fixed_wing=False, fixed_wing_stol=False, rotary_wing=True
            )
            free_helicopter_slots = cp.total_aircraft_parking(parking_type)

            parking_type = ParkingType(
                fixed_wing=False, fixed_wing_stol=True, rotary_wing=False
            )
            free_ground_spawns = cp.total_aircraft_parking(parking_type)

            # Squadrons whose parking must be reserved at this base next turn:
            # every squadron currently based here (outgoing transfers included —
            # they may need to return if the destination is captured this turn)
            # plus any squadrons relocating in.
            occupants = list(cp.squadrons)
            occupants += [
                s for s in cp.coalition.air_wing.iter_squadrons() if s.destination == cp
            ]
            for s in occupants:
                for count in range(s.owned_aircraft):
                    is_heli = s.aircraft.helicopter
                    is_vtol = not is_heli and s.aircraft.lha_capable
                    count_ground_spawns = (
                        s.aircraft.flyable
                        or cp.coalition.game.settings.ground_start_ai_planes
                    )

                    if free_helicopter_slots > 0 and is_heli:
                        free_helicopter_slots -= 1
                    elif free_ground_spawns > 0 and (
                        is_heli or is_vtol or count_ground_spawns
                    ):
                        free_ground_spawns -= 1
                    else:
                        slot = ap.free_parking_slot(s.aircraft.dcs_unit_type)
                        if slot:
                            slot.unit_id = id(s) + count
                        else:
                            if s.aircraft.helicopter:
                                pk_label = "rotary-wing"
                            elif s.aircraft.lha_capable:
                                pk_label = "STOL/ground-spawn"
                            else:
                                pk_label = "fixed-wing"
                            overflow.append((s, pk_label))
                            break
            if overflow:
                self.parking_overflow[cp.name] = list(overflow)
            else:
                self.parking_overflow.pop(cp.name, None)
            return (
                len(ap.free_parking_slots(dcs_unit_type))
                + free_helicopter_slots
                + free_ground_spawns
            )
        else:
            parking_type = ParkingType().from_aircraft(
                next(AircraftType.for_dcs_type(dcs_unit_type)),
                cp.coalition.game.settings.ground_start_ai_planes,
            )
            return cp.unclaimed_parking(parking_type)


#: The left panel is a form, and a form reads better when its labels get out of the
#: way. Small, spaced, upper case, and the colour of a caption rather than a heading.
SECTION_LABEL_STYLE = (
    "font-size: 11px; font-weight: bold; letter-spacing: 1px; color: #6B7A87;"
)
TILE_STYLE = "background: #26343F; border: 1px solid #1D2731; border-radius: 3px;"
BUTTON_SECONDARY = (
    "QPushButton { height: 30px; font-size: 12px; font-weight: 600;"
    " background: #26343F; border: 1px solid #3A4B5C; border-radius: 3px;"
    " color: #D3DFE8; padding: 0 12px; }"
    "QPushButton:disabled { background: #202B36; border-color: #2F3D4B; color: #5F6F7D; }"
)
BUTTON_PRIMARY = (
    "QPushButton { height: 30px; font-size: 12px; font-weight: 600;"
    " background: #8FC3F0; border: none; border-radius: 3px; color: #0F1922;"
    " padding: 0 12px; }"
    "QPushButton:disabled { background: #202B36; color: #5F6F7D; }"
)
BUTTON_DESTRUCTIVE = (
    "QPushButton { height: 30px; font-size: 12px; font-weight: 600;"
    " background: #A8443F; border: none; border-radius: 3px; color: #FFFFFF;"
    " padding: 0 12px; }"
    "QPushButton:hover { background: #BF4F49; }"
    "QPushButton:disabled { background: #202B36; color: #5F6F7D; }"
)

#: The five figures of the inventory, in the order they are read: what you have, what
#: is coming, what you lost, what you paid for, what you started with.
INVENTORY_TILES = (
    ("CURRENT", "owned_aircraft", "#F2F7FA"),
    ("ON ORDER", "pending_deliveries", "#E0A86B"),
    ("DESTROYED", "destroyed_aircraft", "#C08A72"),
    ("PURCHASED", "purchased_aircraft", "#B7C6D2"),
    ("INITIAL", "initial_aircraft", "#8E9DAA"),
)

#: The same treatment for the men: the ceiling, who is on the books, then the three
#: reasons a pilot is not flying, and what is left. Available is the only one you act
#: on, so it is the only one in green.
ROSTER_TILES = (
    ("MAX", "max", "#8E9DAA"),
    ("CURRENT", "current", "#F2F7FA"),
    ("ON LEAVE", "on_leave", "#B7C6D2"),
    ("WOUNDED", "wounded", "#E0A86B"),
    ("BROKEN", "broken", "#C08A72"),
    ("AVAILABLE", "available", "#7FCF7F"),
)


def _section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(SECTION_LABEL_STYLE)
    return label


class SquadronDialog(QDialog):
    """Dialog window showing a squadron."""

    def __init__(
        self,
        ato_model: AtoModel,
        squadron_model: SquadronModel,
        theater: ConflictTheater,
        sim_controller: SimController,
        parent,
    ) -> None:
        super().__init__(parent)
        self.ato_model = ato_model
        self.squadron_model = squadron_model
        # The main list (and the action buttons) operate on living pilots only;
        # dead pilots get their own read-only list below.
        self.squadron_model.pilot_filter = "living"
        self.dead_squadron_model = SquadronModel(
            squadron_model.squadron, pilot_filter="dead"
        )
        self.sim_controller = sim_controller
        self.theater = theater
        self._child_dialogs: list[QDialog] = []

        self.setMinimumSize(MIN_DIALOG_WIDTH, MIN_DIALOG_HEIGHT)
        self.setWindowTitle(f"Squadron — {squadron_model.squadron}")
        # TODO: self.setWindowIcon()

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)
        self.setLayout(layout)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        layout.addLayout(columns, stretch=1)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        left_column.setContentsMargins(0, 0, 0, 0)
        # Boxed and pinned: a livery name can run to sixty characters, and left to
        # itself the form would take half the window from the roster.
        left_panel = QWidget()
        left_panel.setLayout(left_column)
        left_panel.setFixedWidth(LEFT_PANEL_WIDTH)
        columns.addWidget(left_panel, stretch=0)

        left_column.addLayout(self._build_header())

        left_column.addWidget(_section_label("Primary task"))
        self.primary_task_selector = PrimaryTaskSelector.for_squadron(
            self.squadron_model.squadron
        )
        self.primary_task_selector.currentIndexChanged.connect(
            self.on_task_index_changed
        )
        left_column.addWidget(self.primary_task_selector)

        left_column.addWidget(_section_label("Livery"))
        self.livery_selector = SquadronLiverySelector(self.squadron_model.squadron)
        left_column.addWidget(self.livery_selector)

        left_column.addWidget(_section_label("Aircraft inventory"))
        self.inventory_tiles: dict[str, QLabel] = {}
        left_column.addLayout(self._build_inventory_tiles())

        left_column.addWidget(_section_label("Pilots roster"))
        self.roster_tiles: dict[str, QLabel] = {}
        left_column.addLayout(self._build_roster_tiles())

        # Buying aircraft is only meaningful for the player's own squadrons.
        if self.squadron.player.is_blue:
            self.purchase_adapter: AircraftPurchaseAdapter = AircraftPurchaseAdapter(
                self.squadron.location
            )

            purchase_row = QHBoxLayout()
            purchase_row.setSpacing(6)
            self.sell_aircraft_button = QPushButton("−")
            self.sell_aircraft_button.setProperty("style", "btn-sell")
            self.sell_aircraft_button.setFixedSize(28, 28)
            self.sell_aircraft_button.clicked.connect(self.sell_aircraft)
            purchase_row.addWidget(self.sell_aircraft_button)

            self.on_order_label = QLabel()
            self.on_order_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.on_order_label.setFixedWidth(44)
            self.on_order_label.setStyleSheet(
                "background: #14202B; border: 1px solid #3A4B5C; border-radius: 3px;"
                " padding: 4px 0; font-size: 13px;"
            )
            purchase_row.addWidget(self.on_order_label)

            self.buy_aircraft_button = QPushButton("+")
            self.buy_aircraft_button.setProperty("style", "btn-buy")
            self.buy_aircraft_button.setFixedSize(28, 28)
            self.buy_aircraft_button.clicked.connect(self.buy_aircraft)
            purchase_row.addWidget(self.buy_aircraft_button)

            self.price_label = QLabel()
            self.price_label.setStyleSheet("font-size: 12px; color: #8E9DAA;")
            purchase_row.addWidget(self.price_label)
            purchase_row.addStretch()
            left_column.addLayout(purchase_row)

            self.parking_slots_label = QLabel()
            self.parking_slots_label.setStyleSheet("font-size: 12px; color: #7C8B99;")
            left_column.addWidget(self.parking_slots_label)

            self._refresh_aircraft_controls()

        left_column.addWidget(_section_label("Auto-assignable mission types"))
        self.auto_assigned_tasks = AutoAssignedTaskControls(squadron_model)
        left_column.addLayout(self.auto_assigned_tasks)

        # Pinned to the bottom of the panel so it does not float mid-form.
        left_column.addStretch()
        left_column.addWidget(_section_label("Base"))
        self.transfer_destination = SquadronDestinationComboBox(
            squadron_model.squadron, theater
        )
        self.transfer_destination.currentIndexChanged.connect(
            self.on_destination_changed
        )
        left_column.addWidget(self.transfer_destination)

        right_column = QVBoxLayout()
        right_column.setSpacing(6)
        columns.addLayout(right_column, stretch=1)

        right_column.addLayout(self._build_roster_header())
        right_column.addWidget(self._build_column_headers())

        self.pilot_list = PilotList(squadron_model)
        self.pilot_list.selectionModel().selectionChanged.connect(
            self.on_selection_changed
        )
        self.pilot_list.doubleClicked.connect(
            partial(self.open_pilot, self.squadron_model)
        )
        right_column.addWidget(self.pilot_list, stretch=3)

        right_column.addWidget(_section_label("KIA & discharged"))
        self.dead_pilot_list = PilotList(self.dead_squadron_model, fallen=True)
        self.dead_pilot_list.doubleClicked.connect(
            partial(self.open_pilot, self.dead_squadron_model)
        )
        right_column.addWidget(self.dead_pilot_list, stretch=1)

        # Under the roster, not under the aircraft: these all act on a pilot.
        right_column.addLayout(self._build_buttons())

        self._warn_parking_overflow()
        self._restore_geometry()

    # --- the size you chose -------------------------------------------------

    #: Shared by every squadron: the size you want is a property of the dialog, not of
    #: one squadron, and the same key the main window uses for its own geometry.
    GEOMETRY_KEY = "squadronDialogGeometry"

    @staticmethod
    def _qsettings() -> QSettings:
        return app_settings()

    def _restore_geometry(self) -> None:
        saved = self._qsettings().value(self.GEOMETRY_KEY)
        if saved is not None:
            self.restoreGeometry(saved)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._qsettings().setValue(self.GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)

    # --- the panels ---------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        """Identity on the left, context on the right, two lines each.

        The aircraft is the title, with the name and nickname under it and the base on
        the right.

        """
        squadron = self.squadron
        row = QHBoxLayout()
        row.setSpacing(12)

        icon_name = squadron.aircraft.dcs_id.replace("/", "_")
        pixmap = AIRCRAFT_ICONS.get(icon_name)
        if pixmap is not None:
            silhouette = QLabel()
            silhouette.setPixmap(pixmap)
            silhouette.setFixedSize(91, 24)
            silhouette.setScaledContents(True)
            row.addWidget(silhouette, alignment=Qt.AlignmentFlag.AlignTop)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        row.addLayout(identity)

        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        name = QLabel(squadron.aircraft.display_name)
        name.setStyleSheet("font-size: 20px; font-weight: 600; color: #F2F7FA;")
        type_row.addWidget(name)
        variant = squadron.aircraft.variant_id
        if variant and variant != squadron.aircraft.display_name:
            variant_label = QLabel(variant)
            variant_label.setStyleSheet("font-size: 13px; color: #8E9DAA;")
            type_row.addWidget(variant_label, alignment=Qt.AlignmentFlag.AlignBottom)
        type_row.addStretch()
        identity.addLayout(type_row)

        second = QHBoxLayout()
        second.setSpacing(6)
        squadron_name = QLabel(squadron.name)
        squadron_name.setStyleSheet("font-size: 13px; color: #B7C6D2;")
        second.addWidget(squadron_name)
        if squadron.nickname:
            nickname = QLabel(f"“{squadron.nickname}”")
            nickname.setStyleSheet("font-size: 13px; color: #7C8B99;")
            second.addWidget(nickname)
        second.addStretch()
        identity.addLayout(second)

        context = QVBoxLayout()
        context.setSpacing(2)
        row.addLayout(context)
        task = QLabel(squadron.primary_task.value.upper())
        task.setStyleSheet(
            "font-size: 10px; font-weight: bold; letter-spacing: 0.8px;"
            " color: #8FC3F0; background: #22384A; border-radius: 3px;"
            " padding: 3px 8px;"
        )
        context.addWidget(task, alignment=Qt.AlignmentFlag.AlignRight)
        base = QLabel(str(squadron.location))
        base.setStyleSheet("font-size: 13px; color: #8E9DAA;")
        context.addWidget(base, alignment=Qt.AlignmentFlag.AlignRight)
        return row

    def _build_inventory_tiles(self) -> QHBoxLayout:
        """Five figures instead of four lines of prose: they are read, not parsed."""
        return self._build_tiles(
            INVENTORY_TILES,
            {a: str(getattr(self.squadron, a)) for _, a, _ in INVENTORY_TILES},
            self.inventory_tiles,
        )

    def _build_roster_tiles(self) -> QHBoxLayout:
        """The roster in the same shape as the aircraft, and read the same way."""
        return self._build_tiles(
            ROSTER_TILES, self._roster_figures(), self.roster_tiles
        )

    def _roster_figures(self) -> dict[str, str]:
        """Who is on the books, and why each of them is not flying.

        MAX reads as a dash when the campaign runs no pilot limit: the setting exists
        but nothing enforces it.

        """
        squadron = self.squadron
        pilots = squadron.living_pilots
        return {
            "max": str(squadron.pilot_limit) if squadron.pilot_limits_enabled else "—",
            "current": str(len(pilots)),
            "on_leave": str(sum(1 for pilot in pilots if pilot.on_leave)),
            "wounded": str(sum(1 for pilot in pilots if pilot.wounded)),
            "broken": str(len(squadron.refusing_pilots)),
            "available": str(len(squadron.fit_for_duty)),
        }

    def _build_tiles(
        self,
        specs: tuple[tuple[str, str, str], ...],
        figures: dict[str, str],
        store: dict[str, QLabel],
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        for label, attribute, colour in specs:
            tile = QVBoxLayout()
            tile.setSpacing(0)
            value = QLabel(figures[attribute])
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet(
                f"font-family: Consolas, monospace; font-size: 20px;"
                f" font-weight: 600; color: {colour};"
            )
            caption = QLabel(label)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setStyleSheet("font-size: 10px; color: #7C8B99;")
            tile.addWidget(value)
            tile.addWidget(caption)

            holder = QWidget()
            holder.setLayout(tile)
            holder.setFixedHeight(64)
            holder.setStyleSheet(TILE_STYLE)
            row.addWidget(holder)
            store[attribute] = value
        return row

    def _build_roster_header(self) -> QHBoxLayout:
        """How many pilots, and the shape of them, before you scroll anything."""
        row = QHBoxLayout()
        row.addWidget(_section_label("Pilots"))
        self.roster_summary = QLabel()
        self.roster_summary.setStyleSheet("font-size: 12px; color: #8E9DAA;")
        row.addWidget(self.roster_summary)
        row.addStretch()
        # A double click is the only way into a man's record, and nothing else on the
        # window would tell anybody that.
        opens = QLabel("double-click a pilot for his record")
        opens.setStyleSheet("font-size: 11px; color: #4F6070;")
        row.addWidget(opens)

        self._refresh_roster_summary()
        return row

    def _refresh_roster_summary(self) -> None:
        """How full the squadron is, as one pair of figures.

        What each pilot is doing is shown by the roster tiles on the left, so this is
        left with the one thing they do not answer: how much room there is.

        """
        figures = self._roster_figures()
        self.roster_summary.setText(
            f"<b>{figures['current']}/{figures['max']}</b>"
            if self.squadron.pilot_limits_enabled
            else f"<b>{figures['current']}</b>"
        )
        for attribute, tile in getattr(self, "roster_tiles", {}).items():
            tile.setText(figures[attribute])

    @staticmethod
    def _build_column_headers() -> QWidget:
        header = QWidget()
        header.setFixedHeight(22)
        header.setStyleSheet("background: #1B2732;")
        row = QHBoxLayout()
        row.setContentsMargins(MARGIN, 0, MARGIN, 0)
        header.setLayout(row)
        for text, stretch, align in (
            ("PILOT", 0, Qt.AlignmentFlag.AlignLeft),
            ("NOTES", 1, Qt.AlignmentFlag.AlignLeft),
            ("MORALE / STATUS", 0, Qt.AlignmentFlag.AlignRight),
        ):
            label = _section_label(text)
            row.addWidget(label, stretch, align)
        return header

    def _build_buttons(self) -> QHBoxLayout:
        """Discharge is set apart: a fast click on Rename must never land on it."""
        panel = QHBoxLayout()
        panel.setSpacing(8)
        panel.setContentsMargins(0, 6, 0, 0)

        self.discharge_button = QPushButton("Discharge")
        self.discharge_button.setStyleSheet(BUTTON_DESTRUCTIVE)
        self.discharge_button.clicked.connect(self.discharge_pilot)
        panel.addWidget(self.discharge_button)
        panel.addSpacing(24)
        panel.addStretch()

        self.rename_button = QPushButton("Rename")
        self.rename_button.setStyleSheet(BUTTON_SECONDARY)
        self.rename_button.clicked.connect(self.rename_pilot)
        panel.addWidget(self.rename_button)

        self.toggle_ai_button = QPushButton()
        self.toggle_ai_button.setStyleSheet(BUTTON_SECONDARY)
        self.toggle_ai_button.clicked.connect(self.toggle_ai)
        panel.addWidget(self.toggle_ai_button)

        self.toggle_leave_button = QPushButton()
        self.toggle_leave_button.setStyleSheet(BUTTON_PRIMARY)
        self.toggle_leave_button.clicked.connect(self.toggle_leave)
        panel.addWidget(self.toggle_leave_button)

        self.reset_button_states(self.pilot_list.currentIndex())
        return panel

    def _warn_parking_overflow(self) -> None:
        overflow = self.transfer_destination.parking_overflow
        if not overflow:
            return
        self._overflow_squadrons: dict[str, Squadron] = {}
        lines = [
            "Insufficient parking space was detected at the following "
            "bases:<br/><br/>"
        ]
        for cp_name, entries in overflow.items():
            lines.append(f"<b>{cp_name}</b>:<br/>")
            for s, pk_label in entries:
                href = str(s.id)
                self._overflow_squadrons[href] = s
                lines.append(
                    f'&nbsp;&nbsp;<a href="{href}"><b><u>{s.name}</u></b></a>'
                    f" - {s.aircraft.variant_id} "
                    f"(no free {pk_label} parking space)<br/>"
                )
            lines.append("<br/>")
        lines.append(
            "Consider moving these squadrons to a different airfield to "
            "avoid possible air-starts."
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Insufficient parking space detected!")
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        layout = QVBoxLayout()

        label = QLabel("".join(lines))
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        # Default Qt link blue is nearly unreadable on the dark theme.
        link_palette = label.palette()
        link_palette.setColor(QPalette.ColorRole.Link, QColor("#E0E0E0"))
        label.setPalette(link_palette)
        label.linkActivated.connect(self._open_overflow_squadron)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(label)
        layout.addWidget(scroll)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.close)
        layout.addWidget(ok_button, alignment=Qt.AlignmentFlag.AlignRight)

        dialog.setLayout(layout)
        dialog.resize(520, 360)
        self._parking_warning = dialog
        dialog.show()

    def open_pilot(self, model: SquadronModel, index: QModelIndex) -> None:
        """His own dialog, on a double click. The roll of the fallen opens too: a
        dead man's record is most of what there is to read about him."""
        if not index.isValid():
            return
        pilot = model.pilot_at_index(index)
        dialog = open_once(
            f"pilot:{pilot.id}",
            lambda: PilotDialog(pilot, self.squadron.coalition.game, self),
        )
        if isinstance(dialog, PilotDialog):
            dialog.pilot_changed.connect(self._pilot_changed)

    def _pilot_changed(self) -> None:
        """A cheat moved a man between the two lists, or renamed him in both."""
        for model in (self.squadron_model, self.dead_squadron_model):
            model.beginResetModel()
            model.endResetModel()
        self._refresh_roster_summary()
        self.reset_button_states(self.pilot_list.currentIndex())

    def _open_overflow_squadron(self, href: str) -> None:
        squadron = self._overflow_squadrons.get(href)
        if squadron is None:
            return
        open_once(
            f"squadron:{squadron.id}",
            lambda: SquadronDialog(
                self.ato_model,
                SquadronModel(squadron),
                self.theater,
                self.sim_controller,
                self,
            ),
        )

    @property
    def squadron(self) -> Squadron:
        return self.squadron_model.squadron

    @staticmethod
    def _purchase_amount() -> int:
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            return 10
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            return 5
        return 1

    def _refresh_aircraft_controls(self) -> None:
        for attribute, tile in self.inventory_tiles.items():
            tile.setText(str(getattr(self.squadron, attribute)))
        self.on_order_label.setText(str(self.squadron.pending_deliveries))
        self.price_label.setText(
            f"order aircraft · ${self.purchase_adapter.price_of(self.squadron)}M"
        )
        parking_type = ParkingType().from_squadron(self.squadron)
        free_slots = self.squadron.location.unclaimed_parking(parking_type)
        self.parking_slots_label.setText(
            f"{free_slots} parking "
            f"{'slot' if free_slots == 1 else 'slots'} free at "
            f"{self.squadron.location}"
        )
        can_buy = self.purchase_adapter.can_buy(self.squadron)
        self.buy_aircraft_button.setEnabled(can_buy)
        self.buy_aircraft_button.setToolTip(
            "Buy aircraft. Use Shift or Ctrl to buy 10 or 5 at once."
            if can_buy
            else "Cannot buy: insufficient budget, parking or squadron capacity."
        )
        can_sell = self.purchase_adapter.can_sell_or_cancel(self.squadron)
        self.sell_aircraft_button.setEnabled(can_sell)
        self.sell_aircraft_button.setToolTip(
            "Sell aircraft. Use Shift or Ctrl to sell 10 or 5 at once."
            if can_sell
            else "Cannot sell: no idle aircraft or pending orders."
        )

    def buy_aircraft(self) -> None:
        try:
            self.purchase_adapter.buy(self.squadron, self._purchase_amount())
        except TransactionError as ex:
            logging.exception("Aircraft purchase failed")
            QMessageBox.warning(
                self, "Purchase failed", str(ex), QMessageBox.StandardButton.Ok
            )
        finally:
            self._refresh_aircraft_controls()
            GameUpdateSignal.get_instance().updateBudget(self.ato_model.game)

    def sell_aircraft(self) -> None:
        try:
            self.purchase_adapter.sell(self.squadron, self._purchase_amount())
        except TransactionError as ex:
            logging.exception("Aircraft sale failed")
            QMessageBox.warning(
                self, "Sale failed", str(ex), QMessageBox.StandardButton.Ok
            )
        finally:
            self._refresh_aircraft_controls()
            GameUpdateSignal.get_instance().updateBudget(self.ato_model.game)

    def _instant_relocate(self, destination: ControlPoint) -> None:
        self.squadron.relocate_to(destination)
        for _, f in self.squadron.flight_db.objects.items():
            if f.squadron == self.squadron:
                if isinstance(f.flight_plan, CustomFlightPlan):
                    for wpt in f.flight_plan.waypoints:
                        if wpt.waypoint_type == FlightWaypointType.LANDING_POINT:
                            wpt.control_point = destination
                            wpt.position = wpt.control_point.position
                            break
                f.recreate_flight_plan()
                EventStream.put_nowait(GameUpdateEvents().update_flight(f))

    def on_destination_changed(self, index: int) -> None:
        with report_errors("Could not change squadron destination", self):
            destination = self.transfer_destination.itemData(index)
            if destination is self.squadron.location:
                self.squadron.cancel_relocation()
            elif self.ato_model.game.settings.enable_transfer_cheat:
                self._instant_relocate(destination)
            else:
                self.squadron.plan_relocation(
                    destination, self.sim_controller.current_time_in_sim
                )
            self.ato_model.replace_from_game(player=True)

    def reset_button_states(self, index: QModelIndex) -> None:
        """Every button follows the selection, and says why when it cannot act."""
        pilot = self.squadron_model.pilot_at_index(index) if index.isValid() else None
        self.rename_button.setEnabled(pilot is not None)
        self.discharge_button.setEnabled(pilot is not None and pilot.alive)
        self.reset_ai_toggle_state(index)
        self.reset_leave_toggle_state(index)

    def check_disabled_button_states(
        self, button: QPushButton, index: QModelIndex
    ) -> bool:
        if not index.isValid():
            button.setText("No pilot selected")
            button.setDisabled(True)
            return True
        pilot = self.squadron_model.pilot_at_index(index)
        if not pilot.alive:
            button.setText("Pilot is gone")
            button.setDisabled(True)
            return True
        if pilot.wounded:
            # He is already off the roster and comes back on his own schedule.
            button.setText(f"Wounded for {turns_phrase(pilot.wounded_turns)}")
            button.setDisabled(True)
            return True
        return False

    def rename_pilot(self) -> None:
        index = self.pilot_list.currentIndex()
        if not index.isValid():
            logging.error("Cannot toggle player/AI: no pilot is selected")
            return
        p = self.squadron_model.pilot_at_index(index)
        text, ok = QInputDialog.getText(
            self, "Rename pilot", "New name: ", QLineEdit.EchoMode.Normal
        )
        if ok:
            p.name = text

    def toggle_ai(self) -> None:
        index = self.pilot_list.currentIndex()
        if not index.isValid():
            logging.error("Cannot toggle player/AI: no pilot is selected")
            return
        self.squadron_model.toggle_ai_state(index)

    def reset_ai_toggle_state(self, index: QModelIndex) -> None:
        if self.check_disabled_button_states(self.toggle_ai_button, index):
            return
        if not self.squadron_model.squadron.aircraft.flyable:
            self.toggle_ai_button.setText("Not flyable")
            self.toggle_ai_button.setDisabled(True)
            return
        self.toggle_ai_button.setEnabled(True)
        pilot = self.squadron_model.pilot_at_index(index)
        self.toggle_ai_button.setText(
            "Convert to AI" if pilot.player else "Convert to player"
        )

    def selected_pilots(self) -> list[Pilot]:
        """Every pilot under the selection, resolved before anything is changed.

        The model resets after each pilot it touches, so the rows have to be resolved to
        pilots first or the second one acted on is the wrong pilot.

        """
        rows = {
            index.row() for index in self.pilot_list.selectionModel().selectedIndexes()
        }
        current = self.pilot_list.currentIndex()
        if not rows and current.isValid():
            rows = {current.row()}
        pilots = []
        for row in sorted(rows):
            index = self.squadron_model.index(row, 0, QModelIndex())
            if index.isValid():
                pilots.append(self.squadron_model.pilot_at_index(index))
        return pilots

    def toggle_leave(self) -> None:
        """Grant leave for a length, or recall pilots and pay the morale cost.

        The button follows the pilot under the cursor and acts on everyone selected who
        is in the same state as him, so a mixed selection is never sent both ways at
        once.

        """
        index = self.pilot_list.currentIndex()
        if not index.isValid():
            logging.error("Cannot toggle on leave state: no pilot is selected")
            return
        current = self.squadron_model.pilot_at_index(index)
        pilots = [
            pilot
            for pilot in self.selected_pilots()
            if pilot.on_leave == current.on_leave
        ] or [current]
        turns = 0
        if not current.on_leave:
            # For how long, rather than until you remember him: leave granted here now
            # runs down on its own like a wound.
            who = pilots[0].name if len(pilots) == 1 else f"{len(pilots)} pilots"
            turns, ok = QInputDialog.getInt(
                self,
                "Send on leave",
                f"How many turns of leave for {who}?",
                morale_rules.DEFAULT_LEAVE_TURNS,
                1,
                morale_rules.MAX_LEAVE_TURNS,
            )
            if not ok:
                return
        with report_errors("Could not change leave", self):
            for pilot in pilots:
                # Room runs out as they go: a squadron at its ceiling cannot have
                # everyone back at once, and the rest stay where they are.
                self.squadron_model.toggle_leave_state_of(pilot, turns)
        self._refresh_roster_summary()
        self.reset_button_states(self.pilot_list.currentIndex())

    def reset_leave_toggle_state(self, index: QModelIndex) -> None:
        if self.check_disabled_button_states(self.toggle_leave_button, index):
            return
        pilot = self.squadron_model.pilot_at_index(index)
        self.toggle_leave_button.setEnabled(
            not pilot.on_leave or self.squadron_model.squadron.has_unfilled_pilot_slots
        )
        self.toggle_leave_button.setText(
            "Cancel leave" if pilot.on_leave else "Send on leave"
        )
        cost = abs(morale_rules.LEAVE_CANCELLED.amount(self.squadron.settings))
        self.toggle_leave_button.setToolTip(
            f"He loses {cost} morale for being called back early."
            if pilot.on_leave
            else ""
        )

    def discharge_pilot(self) -> None:
        """Throw pilots out. Asked about first: there is no getting them back."""
        pilots = self.selected_pilots()
        if not pilots:
            logging.error("Cannot discharge: no pilot is selected")
            return
        if len(pilots) == 1:
            rank = self.squadron.pilot_rank(pilots[0])
            addressed = (
                pilots[0].name
                if rank is None
                else f"{rank.abbreviation} {pilots[0].name}"
            )
            question = (
                f"Discharge {addressed} from {self.squadron}? "
                "He leaves the squadron for good."
            )
        else:
            # Named, not counted: discharging the wrong man is not undoable, and a
            # number is not something you can check.
            named = "\n".join(f"  {pilot.name}" for pilot in pilots)
            question = (
                f"Discharge {len(pilots)} pilots from {self.squadron}?\n\n{named}"
                "\n\nThey leave the squadron for good."
            )
        answer = QMessageBox.question(
            self,
            "Discharge pilot" if len(pilots) == 1 else "Discharge pilots",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for pilot in pilots:
            self.squadron_model.discharge(pilot)
        self.dead_squadron_model.beginResetModel()
        self.dead_squadron_model.endResetModel()
        self._refresh_roster_summary()
        self.reset_button_states(self.pilot_list.currentIndex())

    def on_selection_changed(
        self, selected: QItemSelection, _deselected: QItemSelection
    ) -> None:
        indexes = selected.indexes()
        if not indexes:
            return
        self.reset_button_states(indexes[0])

    def on_task_index_changed(self, index: int) -> None:
        task = self.primary_task_selector.itemData(index)
        if task is None:
            raise RuntimeError("Selected task cannot be None")
        self.squadron.primary_task = task
