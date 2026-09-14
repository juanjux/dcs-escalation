"""What a squadron is allowed to be given, as chips instead of a wall of checkboxes.

Twenty rows of "Mission Type / Auto-Assign" for an aircraft that can fly eleven of them
was the worst part of this form: no structure, no sense of which tasks were the
airframe's business, and the ten it cannot do sat there greyed out taking up the same
room as the ones it can.

The chips show only what the aircraft can fly, grouped into the three families the rest
of the app already colours tasks by, so a glance says "this squadron is air-to-ground
only" without reading a label. What is hidden is named in one line, because a task
missing with no explanation reads as a bug.
"""

from __future__ import annotations

from typing import Iterator, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QPoint, QRect, QSize

from game.ato.flighttype import FlightType
from game.squadrons import Squadron
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import wrapped_tooltip
from qt_ui.widgets.squadrondelegate import (
    AIR_TO_AIR,
    AIR_TO_GROUND,
    SUPPORT,
    chip_colours,
)
from .common import ACCENT, TEXT_MUTED

#: Caption, colour and membership of each family, in reading order.
FAMILIES: list[tuple[str, str, set[FlightType]]] = [
    ("AIR-TO-AIR", "#6E93B0", AIR_TO_AIR),
    ("AIR-TO-GROUND", "#9A7A55", AIR_TO_GROUND),
    ("SUPPORT", "#5F8A6C", SUPPORT),
]


class FlowLayout(QLayout):
    """Chips wrap like words. Qt has no such layout, so this is the standard one."""

    def __init__(self, spacing: int = 6) -> None:
        super().__init__()
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (Qt naming)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._lay_out(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._lay_out(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _lay_out(self, rect: QRect, test_only: bool) -> int:
        x, y, line_height = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() and line_height > 0:
                x = rect.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class TaskChip(QToolButton):
    """One task, on or off, coloured by its family when on."""

    def __init__(self, task: FlightType, on: bool) -> None:
        super().__init__()
        self.task = task
        self.is_primary = False
        self.setCheckable(True)
        self.setChecked(on)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.toggled.connect(lambda _: self._restyle())
        self._restyle()

    def mark_primary(self, primary: bool) -> None:
        """The primary task cannot be switched off: a squadron whose own task is not
        auto-assignable is a trap the old form let you build."""
        self.is_primary = primary
        if primary:
            self.setChecked(True)
            self.setToolTip(
                wrapped_tooltip(
                    "This is the squadron's primary task, so it is always "
                    "auto-assignable. Change the primary task to release it."
                )
            )
        else:
            self.setToolTip("")
        self._restyle()

    def nextCheckState(self) -> None:  # noqa: N802 (Qt naming)
        if self.is_primary:
            return
        super().nextCheckState()

    def _restyle(self) -> None:
        fill, ink = chip_colours(self.task)
        label = self.task.value.upper()
        if self.isChecked():
            self.setText(("✓ " + label) + ("  PRIMARY" if self.is_primary else ""))
            border = ink.name() if self.is_primary else "transparent"
            self.setStyleSheet(
                f"QToolButton {{ background: {fill.name()}; color: {ink.name()};"
                f" border: 1px solid {border}; border-radius: 4px; padding: 0 9px;"
                f" font-size: 11px; font-weight: 700; }}"
            )
        else:
            self.setText(label)
            self.setStyleSheet(
                "QToolButton { background: transparent; color: #7C8B99;"
                " border: 1px solid #3A4B5C; border-radius: 4px; padding: 0 9px;"
                " font-size: 11px; font-weight: 600; }"
                "QToolButton:hover { border-color: #6B7A87; color: #B7C6D2; }"
            )


def _shortcut(text: str) -> QLabel:
    label = QLabel(text)
    label.setCursor(Qt.CursorShape.PointingHandCursor)
    label.setStyleSheet(f"font-size: 11px; color: {ACCENT};")
    return label


class TaskChips(QWidget):
    """The auto-assignable set for one squadron."""

    changed = Signal()

    def __init__(self, squadron: Squadron) -> None:
        super().__init__()
        self.squadron = squadron
        self.chips: list[TaskChip] = []
        make_transparent(self)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        self.setLayout(column)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        title = QLabel("AUTO-ASSIGNABLE TASKS")
        title.setStyleSheet(
            f"font-size: 10.5px; font-weight: 700; letter-spacing: 1px;"
            f" color: {TEXT_MUTED};"
        )
        header.addWidget(title)
        header.addStretch()
        for text, handler in (
            ("All", self.select_all),
            ("None", self.select_none),
            ("Preset", self.select_preset),
        ):
            link = _shortcut(text)
            link.mousePressEvent = lambda _event, run=handler: run()  # type: ignore[method-assign]
            header.addWidget(link)
        column.addLayout(header)

        hidden: list[str] = []
        for caption_text, colour, family in FAMILIES:
            possible = [
                task
                for task in FlightType
                if task in family
                and task is not FlightType.FERRY
                and squadron.capable_of(task)
            ]
            impossible = [
                task.value
                for task in FlightType
                if task in family
                and task is not FlightType.FERRY
                and not squadron.capable_of(task)
            ]
            hidden.extend(impossible)
            if not possible:
                # A family the airframe can do nothing in is not drawn at all.
                continue
            family_caption = QLabel(caption_text)
            family_caption.setStyleSheet(
                f"font-size: 10px; font-weight: 700; letter-spacing: 1px;"
                f" color: {colour};"
            )
            column.addWidget(family_caption)

            row = QWidget()
            make_transparent(row)
            flow = FlowLayout()
            row.setLayout(flow)
            for task in possible:
                chip = TaskChip(task, task in squadron.auto_assignable_mission_types)
                chip.toggled.connect(lambda _: self.changed.emit())
                self.chips.append(chip)
                flow.addWidget(chip)
            column.addWidget(row)

        if hidden:
            note = QLabel(
                f"Hidden because a {squadron.aircraft.display_name} cannot fly them: "
                + " · ".join(hidden)
            )
            note.setWordWrap(True)
            note.setStyleSheet("font-size: 11px; color: #4F6070;")
            column.addWidget(note)

        column.addStretch()
        self.set_primary(squadron.primary_task)

    # --- the set ------------------------------------------------------------

    @property
    def auto_assignable_mission_types(self) -> Iterator[FlightType]:
        for chip in self.chips:
            if chip.isChecked():
                yield chip.task

    def set_primary(self, task: Optional[FlightType]) -> None:
        for chip in self.chips:
            chip.mark_primary(chip.task is task)
        self.changed.emit()

    def replace_squadron(self, squadron: Squadron) -> None:
        self.squadron = squadron
        for chip in self.chips:
            chip.setChecked(chip.task in squadron.auto_assignable_mission_types)
        self.set_primary(squadron.primary_task)

    def select_all(self) -> None:
        for chip in self.chips:
            chip.setChecked(True)

    def select_none(self) -> None:
        for chip in self.chips:
            if not chip.is_primary:
                chip.setChecked(False)

    def select_preset(self) -> None:
        """Back to what this airframe is normally given.

        The aircraft's own priority table: every task it is rated for, which is the set
        a squadron is created with before anybody edits it.
        """
        wanted = set(self.squadron.aircraft.task_priorities)
        for chip in self.chips:
            chip.setChecked(chip.is_primary or chip.task in wanted)
