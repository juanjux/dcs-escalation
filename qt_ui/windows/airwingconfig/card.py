"""One squadron, as a card you can read closed and edit open.

The group box this replaces was always open and always the full form, so a type with
four squadrons was four forms stacked down a scrolling page and no way to see what you
had. Closed, the header answers what you go looking for -- name, what it is for, where
it is, how big, how much it is allowed to do. Open, it is the same fields as before.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.coalition import Coalition
from game.squadrons import Pilot, Squadron
from game.theater import ControlPoint, ParkingType
from qt_ui.uiconstants import ICONS
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.combos.QSquadronLiverySelector import SquadronLiverySelector
from qt_ui.widgets.combos.primarytaskselector import PrimaryTaskSelector
from qt_ui.widgets.controls import styled_input
from qt_ui.widgets.squadrondelegate import chip_colours
from .common import (
    ACCENT,
    AMBER,
    BAR_OTHERS,
    BAR_TRACK,
    CHEAT_BG,
    CHEAT_BORDER,
    CHEAT_CHIP_BG,
    GREEN,
    HEADER,
    LINE,
    PANEL,
    PilotLimitSpinner,
    RED,
    SquadronBaseSelector,
    SquadronSizeSpinner,
    TEXT_LABEL,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    AirWingConfigParkingTracker,
)
from .taskchips import TaskChips

CARD_WIDTH_LEFT = 300


def _caption(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"font-size: 10.5px; font-weight: 700; letter-spacing: 1px; color: {TEXT_MUTED};"
    )
    return label


class ParkingBar(QWidget):
    """This squadron's share of its base, against everyone else's.

    Three sentences of arithmetic became one bar and one line: the numbers are still
    there, the bar only says where to read them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(6)
        self.mine = 0
        self.others = 0
        self.total = 1
        make_transparent(self)

    def set_values(self, mine: int, others: int, total: int) -> None:
        self.mine, self.others, self.total = mine, others, max(1, total)
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 (Qt naming)
        from PySide6.QtGui import QColor, QPainter

        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        width = self.width()
        painter.setBrush(QColor(BAR_TRACK))
        painter.drawRect(0, 0, width, self.height())
        used = self.mine + self.others
        over = used > self.total
        others_w = int(width * min(1.0, self.others / self.total))
        mine_w = int(width * min(1.0, self.mine / self.total))
        painter.setBrush(QColor(RED if over else BAR_OTHERS))
        painter.drawRect(0, 0, others_w, self.height())
        painter.setBrush(QColor(RED if over else ACCENT))
        painter.drawRect(others_w, 0, min(mine_w, width - others_w), self.height())
        painter.end()


class PlayerSlots(QWidget):
    """The player pilots in this squadron, as the painted row used everywhere else.

    Or one quiet dashed row saying why there are none, instead of a label above an
    empty box.
    """

    def __init__(self, squadron: Squadron) -> None:
        super().__init__()
        self.squadron = squadron
        make_transparent(self)
        self.column = QVBoxLayout()
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(2)
        self.setLayout(self.column)
        self.editor: Optional[QLineEdit] = None
        self.rebuild()

    def reason_not_available(self) -> Optional[str]:
        if not self.squadron.aircraft.flyable:
            return (
                f"{self.squadron.aircraft.display_name} is not flyable in DCS — AI only"
            )
        if not self.squadron.player.is_blue:
            return "Player slots are not available for the opfor"
        return None

    def rebuild(self) -> None:
        while self.column.count():
            item = self.column.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        reason = self.reason_not_available()
        if reason is not None:
            self.editor = None
            row = QLabel(reason)
            row.setWordWrap(True)
            row.setStyleSheet(
                f"background: #182430; border: 1px dashed #2F3D4B; border-radius: 3px;"
                f" padding: 6px 8px; font-size: 11.5px; color: {TEXT_MUTED};"
            )
            self.column.addWidget(row)
            return
        # One name per line, as before: this is the only place a player can name the
        # pilots he will fly as, and a list of line edits would be worse.
        self.editor = QLineEdit(", ".join(p.name for p in self.claim_players()))
        self.editor.setPlaceholderText("Player names, comma separated")
        self.column.addWidget(styled_input(self.editor))

    def claim_players(self) -> list[Pilot]:
        if not self.squadron.player.is_blue:
            return []
        players = [p for p in self.squadron.pilot_pool if p.player]
        for player in players:
            self.squadron.pilot_pool.remove(player)
        return players

    def return_players(self) -> None:
        if self.editor is None or not self.squadron.player.is_blue:
            return
        names = [n.strip() for n in self.editor.text().split(",") if n.strip()]
        # Prepend player pilots so they get set active first.
        self.squadron.pilot_pool = [
            Pilot(name, player=True) for name in names
        ] + self.squadron.pilot_pool

    def replace_squadron(self, squadron: Squadron) -> None:
        self.squadron = squadron
        self.rebuild()


class SquadronCard(QWidget):
    remove_squadron_signal = Signal(Squadron)
    changed = Signal()
    expanded = Signal(object)

    def __init__(
        self,
        game: Game,
        coalition: Coalition,
        squadron: Squadron,
        parking_tracker: AirWingConfigParkingTracker,
        aircraft_present: bool,
        cheat: bool = False,
    ) -> None:
        super().__init__()
        self.game = game
        self.coalition = coalition
        self.squadron = squadron
        self.parking_tracker = parking_tracker
        self.aircraft_present = aircraft_present
        self.cheat = cheat
        self._open = False

        self.setObjectName(f"squadronCard{id(self)}")
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.setLayout(column)

        column.addWidget(self._build_header())
        self.body = self._build_body()
        column.addWidget(self.body)
        self.body.setVisible(False)

        self.parking_tracker.allocation_changed.connect(self.refresh)
        self.refresh()

    # --- header -------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName(f"cardHeader{id(self)}")
        header.setFixedHeight(52)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.mousePressEvent = self._header_clicked  # type: ignore[method-assign]
        self.header = header

        row = QHBoxLayout()
        row.setContentsMargins(14, 8, 12, 8)
        row.setSpacing(10)
        header.setLayout(row)

        self.arrow = QLabel("▸")
        self.arrow.setFixedWidth(16)
        self.arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.arrow)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        line1 = QHBoxLayout()
        line1.setContentsMargins(0, 0, 0, 0)
        line1.setSpacing(8)
        self.title = QLabel()
        self.title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};"
        )
        line1.addWidget(self.title)
        self.nickname_label = QLabel()
        self.nickname_label.setStyleSheet(f"font-size: 12.5px; color: {TEXT_LABEL};")
        line1.addWidget(self.nickname_label)
        self.task_chip = QLabel()
        line1.addWidget(self.task_chip)
        line1.addStretch()
        text.addLayout(line1)
        self.summary = QLabel()
        self.summary.setStyleSheet(f"font-size: 11.5px; color: {TEXT_TERTIARY};")
        text.addWidget(self.summary)
        row.addLayout(text, stretch=1)

        self.warning_pill = QLabel()
        self.warning_pill.setVisible(False)
        row.addWidget(self.warning_pill)

        self.replace_button = QPushButton("Replace with preset…")
        self.replace_button.setFixedHeight(26)
        self.replace_button.setStyleSheet(
            f"QPushButton {{ background: {PANEL}; color: {TEXT_SECONDARY};"
            f" border: 1px solid #3A4B5C; border-radius: 3px; padding: 0 10px;"
            f" font-size: 11.5px; }}"
            f"QPushButton:hover {{ background: #31424F; }}"
        )
        self.replace_button.clicked.connect(self.replace_with_preset)
        row.addWidget(self.replace_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setFixedHeight(26)
        self.remove_button.setStyleSheet(
            "QPushButton { background: #3B2523; color: #E8B7B3;"
            " border: 1px solid #A8443F; border-radius: 3px; padding: 0 10px;"
            " font-size: 11.5px; }"
            "QPushButton:hover { background: #4A2B29; }"
        )
        self.remove_button.clicked.connect(
            lambda: self.remove_squadron_signal.emit(self.squadron)
        )
        row.addWidget(self.remove_button)
        return header

    def _header_clicked(self, _event: QMouseEvent) -> None:
        self.set_open(not self._open)
        if self._open:
            self.expanded.emit(self)

    def set_open(self, is_open: bool) -> None:
        self._open = is_open
        self.body.setVisible(is_open)
        self.arrow.setText("▾" if is_open else "▸")
        # Big enough to be the thing you aim at: it is the only control on a closed
        # card, and at 12 px it was a smudge.
        self.arrow.setStyleSheet(
            f"font-size: 17px; color: {ACCENT if is_open else TEXT_SECONDARY};"
        )
        self.replace_button.setVisible(is_open)
        self.remove_button.setVisible(is_open)
        self.refresh()

    # --- body ---------------------------------------------------------------

    def _build_body(self) -> QWidget:
        body = QWidget()
        make_transparent(body)
        row = QHBoxLayout()
        row.setContentsMargins(14, 14, 16, 14)
        row.setSpacing(20)
        body.setLayout(row)

        left = QVBoxLayout()
        left.setSpacing(8)
        holder = QWidget()
        make_transparent(holder)
        holder.setLayout(left)
        holder.setFixedWidth(CARD_WIDTH_LEFT)
        row.addWidget(holder)

        if self.cheat:
            left.addWidget(self._build_cheat_block())

        left.addWidget(_caption("Name"))
        self.name_edit = QLineEdit(self.squadron.name)
        self.name_edit.textChanged.connect(self.refresh)
        left.addWidget(styled_input(self.name_edit))

        left.addWidget(_caption("Nickname"))
        nickname_row = QHBoxLayout()
        nickname_row.setSpacing(6)
        self.nickname_edit = QLineEdit(self.squadron.nickname)
        self.nickname_edit.textChanged.connect(self.refresh)
        nickname_row.addWidget(styled_input(self.nickname_edit))
        reroll = QToolButton()
        reroll.setIcon(QIcon(ICONS["Reload"]))
        reroll.setFixedSize(28, 28)
        reroll.setToolTip("Re-roll nickname")
        reroll.clicked.connect(self.reroll_nickname)
        nickname_row.addWidget(reroll)
        left.addLayout(nickname_row)

        left.addWidget(_caption("Livery"))
        self.livery_selector = SquadronLiverySelector(self.squadron)
        left.addWidget(styled_input(self.livery_selector))

        sizes = QHBoxLayout()
        sizes.setSpacing(10)
        size_column = QVBoxLayout()
        size_column.setSpacing(4)
        size_column.addWidget(_caption("Max size"))
        self.max_size_selector = SquadronSizeSpinner(self.squadron.max_size, self)
        self.max_size_selector.valueChanged.connect(self.update_max_size)
        size_column.addWidget(styled_input(self.max_size_selector, width=96))
        sizes.addLayout(size_column)
        pilots_column = QVBoxLayout()
        pilots_column.setSpacing(4)
        pilots_column.addWidget(_caption("Max pilots"))
        self.pilot_limit_selector = PilotLimitSpinner(self.squadron, self)
        self.pilot_limit_selector.valueChanged.connect(self.update_max_size)
        pilots_column.addWidget(styled_input(self.pilot_limit_selector))
        sizes.addLayout(pilots_column)
        left.addLayout(sizes)

        left.addWidget(_caption("Primary task"))
        self.primary_task_selector = PrimaryTaskSelector.for_squadron(self.squadron)
        self.primary_task_selector.currentIndexChanged.connect(self.on_primary_changed)
        left.addWidget(styled_input(self.primary_task_selector))

        left.addWidget(_caption("Base"))
        self.base_selector = SquadronBaseSelector(
            self.game.theater.control_points_for(self.squadron.player),
            self.squadron.location,
            self.squadron.aircraft,
        )
        self.base_selector.currentIndexChanged.connect(self.relocate_squadron)
        left.addWidget(styled_input(self.base_selector))

        self.parking_bar = ParkingBar()
        left.addWidget(self.parking_bar)
        self.parking_label = QLabel()
        self.parking_label.setWordWrap(True)
        self.parking_label.setStyleSheet("font-size: 11.5px;")
        left.addWidget(self.parking_label)

        if self.cheat:
            note = QLabel("Changing base relocates the squadron immediately.")
            note.setWordWrap(True)
            note.setStyleSheet(f"font-size: 11px; color: {AMBER};")
            left.addWidget(note)

        left.addWidget(_caption("Player slots"))
        self.player_slots = PlayerSlots(self.squadron)
        left.addWidget(self.player_slots)
        left.addStretch()

        self.task_chips = TaskChips(self.squadron)
        self.task_chips.changed.connect(self.refresh)
        row.addWidget(self.task_chips, stretch=1)
        return body

    def _build_cheat_block(self) -> QWidget:
        block = QWidget()
        block.setObjectName(f"cheatBlock{id(self)}")
        block.setStyleSheet(
            f"#cheatBlock{id(self)} {{ background: {CHEAT_BG};"
            f" border: 1px solid {CHEAT_BORDER}; border-radius: 4px; }}"
        )
        column = QVBoxLayout()
        column.setContentsMargins(10, 8, 10, 10)
        column.setSpacing(6)
        block.setLayout(column)

        chip = QLabel("CHEAT")
        chip.setStyleSheet(
            f"background: {CHEAT_CHIP_BG}; color: {AMBER}; border-radius: 3px;"
            f" padding: 2px 6px; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.8px;"
        )
        chip.setFixedWidth(52)
        column.addWidget(chip)
        column.addWidget(_caption("Aircraft on hand"))

        stepper = QHBoxLayout()
        stepper.setSpacing(6)
        style = (
            f"QPushButton {{ background: #3B2D21; color: {AMBER};"
            f" border: 1px solid #5A4630; border-radius: 3px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #4A3A28; }}"
        )
        minus = QPushButton("−")
        minus.setFixedSize(28, 28)
        minus.setStyleSheet(style)
        minus.clicked.connect(self.cheat_remove_aircraft)
        stepper.addWidget(minus)
        self.aircraft_count_label = QLabel()
        self.aircraft_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.aircraft_count_label.setFixedWidth(44)
        self.aircraft_count_label.setStyleSheet(
            f"font-family: Consolas, monospace; font-size: 15px; font-weight: 600;"
            f" color: {TEXT_PRIMARY};"
        )
        stepper.addWidget(self.aircraft_count_label)
        plus = QPushButton("+")
        plus.setFixedSize(28, 28)
        plus.setStyleSheet(style)
        plus.clicked.connect(self.cheat_add_aircraft)
        stepper.addWidget(plus)
        self.cheat_delta_label = QLabel()
        self.cheat_delta_label.setStyleSheet(f"font-size: 11px; color: {AMBER};")
        stepper.addWidget(self.cheat_delta_label)
        stepper.addStretch()
        column.addLayout(stepper)

        self.cheat_note = QLabel()
        self.cheat_note.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        column.addWidget(self.cheat_note)

        self._aircraft_at_open = self.squadron.owned_aircraft
        self.update_aircraft_count_label()
        return block

    # --- state --------------------------------------------------------------

    def over_capacity(self) -> int:
        location = self.squadron.location
        used = self.parking_tracker.used_parking_at(location)
        return used - self.total_parking_at(location)

    def total_parking_at(self, location: ControlPoint) -> int:
        """Slots at this base that this squadron's aircraft can use."""
        parking_type = ParkingType().from_aircraft(
            self.squadron.aircraft, self.game.settings.ground_start_ai_planes
        )
        return location.total_aircraft_parking(parking_type)

    def refresh(self) -> None:
        name = (
            self.name_edit.text() if hasattr(self, "name_edit") else self.squadron.name
        )
        self.title.setText(name or self.squadron.name)
        nickname = (
            self.nickname_edit.text()
            if hasattr(self, "nickname_edit")
            else self.squadron.nickname
        )
        self.nickname_label.setText(f"“{nickname}”" if nickname else "")

        task = self.squadron.primary_task
        if hasattr(self, "primary_task_selector"):
            task = self.primary_task_selector.selected_task or task
        fill, ink = chip_colours(task)
        self.task_chip.setText(task.value.upper())
        self.task_chip.setStyleSheet(
            f"background: {fill.name()}; color: {ink.name()}; border-radius: 3px;"
            f" padding: 2px 7px; font-size: 10px; font-weight: 700;"
            f" letter-spacing: 0.6px;"
        )

        allowed = (
            len(list(self.task_chips.auto_assignable_mission_types))
            if hasattr(self, "task_chips")
            else len(self.squadron.auto_assignable_mission_types)
        )
        if self.cheat:
            parts = [
                self.squadron.location.name,
                f"{self.squadron.owned_aircraft} of {self.squadron.max_size} aircraft",
                f"{len(self.squadron.living_pilots)} pilots",
                f"{allowed} tasks",
            ]
        else:
            parts = [
                self.squadron.location.name,
                f"{self.squadron.max_size} aircraft max",
                f"{allowed} tasks allowed",
            ]
        self.summary.setText(" · ".join(parts))

        over = self.over_capacity()
        bar = ACCENT if self._open else "transparent"
        if over > 0:
            bar = RED
        # Scoped to the header's own name: an unscoped border rule cascades, and
        # this one drew a left border down every label in the row.
        self.header.setStyleSheet(
            f"#{self.header.objectName()} {{ background: {HEADER};"
            f" border-left: 3px solid {bar}; border-bottom: 1px solid {LINE}; }}"
        )
        self.warning_pill.setVisible(not self._open and over > 0)
        if over > 0:
            self.warning_pill.setText(f"▲ {self.squadron.location.name} is {over} over")
            self.warning_pill.setStyleSheet(
                f"color: {AMBER}; font-size: 11px; padding-right: 6px;"
            )

        if self._open:
            self.update_parking()
        if self.cheat and hasattr(self, "aircraft_count_label"):
            self.update_aircraft_count_label()

    def update_parking(self) -> None:
        location = self.squadron.location
        mine = self.squadron.max_size
        others = self.parking_tracker.used_parking_at(location) - mine
        total = self.total_parking_at(location)
        self.parking_bar.set_values(mine, others, total)
        fit = "N/A"
        if airport := location.dcs_airport:
            fit = str(
                len(airport.free_parking_slots(self.squadron.aircraft.dcs_unit_type))
            )
        free = total - mine - others
        colour = GREEN if free >= 0 else RED
        self.parking_label.setText(
            f"<span style='color:{TEXT_TERTIARY}'>{mine} this squadron · "
            f"{others} others · </span>"
            f"<span style='color:{colour}'>{free} free</span>"
            f"<span style='color:{TEXT_TERTIARY}'> of {total} · {fit} slots fit a "
            f"{self.squadron.aircraft.display_name}</span>"
        )

    def update_max_size(self) -> None:
        self.squadron.max_size = self.max_size_selector.value()
        self.squadron.pilot_limit_override = self.pilot_limit_selector.chosen_limit
        self.parking_tracker.signal_change()
        self.changed.emit()

    def on_primary_changed(self) -> None:
        task = self.primary_task_selector.selected_task
        if task is not None:
            self.task_chips.set_primary(task)
        self.refresh()

    def update_aircraft_count_label(self) -> None:
        self.aircraft_count_label.setText(str(self.squadron.owned_aircraft))
        delta = self.squadron.owned_aircraft - self._aircraft_at_open
        self.cheat_delta_label.setText(
            f"was {self._aircraft_at_open} · {delta:+d}" if delta else ""
        )
        pending = self.squadron.pending_deliveries
        arriving = f" · {pending} on order" if pending else ""
        self.cheat_note.setText(f"max {self.squadron.max_size}{arriving}")

    def cheat_add_aircraft(self) -> None:
        # Free aircraft: bump owned and the taskable pool directly, no budget change.
        # Recruit a pilot with it -- with squadron pilot limits on, a cheated airframe
        # would otherwise sit uncrewable (claim_new_pilot_if_allowed refuses).
        self.squadron.owned_aircraft += 1
        self.squadron.untasked_aircraft += 1
        self.squadron._recruit_pilots(1)
        self.update_aircraft_count_label()
        self.changed.emit()

    def cheat_remove_aircraft(self) -> None:
        if self.squadron.owned_aircraft <= 0:
            return
        self.squadron.owned_aircraft -= 1
        self.squadron.untasked_aircraft = max(0, self.squadron.untasked_aircraft - 1)
        self.update_aircraft_count_label()
        self.changed.emit()

    def relocate_squadron(self) -> None:
        location = self.base_selector.currentData()
        if location is None:
            return
        self.parking_tracker.relocate_squadron(
            self.squadron, self.squadron.location, location
        )
        self.changed.emit()

    def reroll_nickname(self) -> None:
        self.nickname_edit.setText(
            self.squadron.coalition.air_wing.squadron_def_generator.random_nickname()
        )

    # --- preset replacement --------------------------------------------------

    def pick_replacement_squadron(self) -> Optional[Squadron]:
        from .popups import PresetSquadronSelector

        popup = PresetSquadronSelector(
            self.squadron.aircraft,
            self.coalition.air_wing.squadron_defs,
        )
        if popup.exec_() != QDialog.DialogCode.Accepted:
            return None

        selected_def = popup.squadron_def_selector.currentData()
        self.squadron.coalition.air_wing.unclaim_squadron_def(self.squadron)
        return Squadron.create_from(
            selected_def,
            self.squadron.primary_task,
            self.squadron.max_size,
            self.squadron.location,
            self.coalition,
            self.game,
        )

    def replace_with_preset(self) -> None:
        new_squadron = self.pick_replacement_squadron()
        if new_squadron is None:
            return
        self.player_slots.return_players()
        self.parking_tracker.remove_squadron(self.squadron)
        self.squadron = new_squadron
        self.parking_tracker.add_squadron(self.squadron)
        self.bind_data()
        self.task_chips.replace_squadron(self.squadron)
        self.player_slots.replace_squadron(self.squadron)
        self.parking_tracker.signal_change()
        self.changed.emit()

    def bind_data(self) -> None:
        old_state = self.blockSignals(True)
        try:
            self.name_edit.setText(self.squadron.name)
            self.nickname_edit.setText(self.squadron.nickname)
            self.primary_task_selector.setCurrentText(self.squadron.primary_task.value)
            index = self.livery_selector.findText(self.squadron.livery)
            self.livery_selector.setCurrentIndex(index)
            self.max_size_selector.setValue(self.squadron.max_size)
            self.base_selector.setCurrentText(self.squadron.location.name)
        finally:
            self.blockSignals(old_state)
        self.refresh()

    # --- saving --------------------------------------------------------------

    def apply(self) -> Squadron:
        self.squadron.name = self.name_edit.text()
        self.squadron.nickname = self.nickname_edit.text()
        self.squadron.max_size = self.max_size_selector.value()
        self.squadron.pilot_limit_override = self.pilot_limit_selector.chosen_limit
        if (primary_task := self.primary_task_selector.selected_task) is not None:
            self.squadron.primary_task = primary_task
        else:
            raise RuntimeError("Primary task cannot be none")
        base = self.base_selector.currentData()
        if base is None:
            raise RuntimeError("Base cannot be none")
        self.squadron.assign_to_base(base)
        self.player_slots.return_players()
        self.squadron.set_auto_assignable_mission_types(
            set(self.task_chips.auto_assignable_mission_types)
        )
        return self.squadron
