"""Buy or replace what stands at a location.

Two panes: what the faction can field here, and what the chosen one is made of. The
money is in the header and answers the only question the dialog exists for -- what the
site costs once what stands there is sold -- on every change.
"""

from __future__ import annotations

import re
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.armedforces.forcegroup import ForceGroup
from game.layout.layout import TgoLayout
from game.theater import TheaterGroundObject
from qt_ui.uiconstants import EVENT_ICONS
from qt_ui.widgets.cards import make_transparent
from qt_ui.widgets.controls import Segmented, button, styled_input
from qt_ui.windows.groundobject.buymodel import (
    Selection,
    Slot,
    buy,
    here_now,
    offers,
    reach_of,
    section_of,
)
from game.theater.theatergroundobject import (
    CoastalSiteGroundObject,
    IadsGroundObject,
    MissileSiteGroundObject,
    ShipGroundObject,
    VehicleGroupGroundObject,
)
from qt_ui.windows.pilot.common import (
    ACCENT,
    EMPTY,
    GREEN,
    HEADING_BG,
    PANEL,
    RED,
    Row,
    Stack,
    TEXT_BASE,
    TEXT_LABEL,
    TEXT_PRIMARY,
    chip,
    heading,
    label,
)

WIDTH = 980
MIN_WIDTH = 860
PRESETS_WIDTH = 300

#: The fill of the preset that is selected.
SELECTED = "#1E3A52"


class QGroundObjectBuyMenu(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        ground_object: TheaterGroundObject,
        game: Game,
        current_group_value: int,
    ) -> None:
        super().__init__(parent)
        self.ground_object = ground_object
        self.game = game
        self.refund = int(current_group_value)

        self.offers = offers(ground_object)
        self.here = here_now(ground_object, self.offers)
        self._selections: dict[tuple[int, int], Selection] = {}
        self.selection = self._first_selection()

        self.setWindowTitle(f"Buy / replace — {ground_object.obj_name}")
        self.setWindowIcon(EVENT_ICONS["capture"])
        self.setMinimumWidth(MIN_WIDTH)
        self.setStyleSheet(f"QDialog {{ background: {PANEL}; }}")

        self.figures: dict[str, QLabel] = {}
        self.composition = Stack()
        self.layout_choice: Optional[Segmented] = None
        self.shortfall = label("", 12, RED, bold=True)
        self.buy_button = button("Buy", "primary", handler=self._buy)
        self.presets = Stack()
        self.preset_rows: dict[int, Row] = {}
        #: The subtotal label of each slot, so a change can find it again.
        self.subtotals: dict[int, QLabel] = {}

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._header())
        column.addWidget(self._body(), 1)
        column.addWidget(self._footer())
        self.setLayout(column)

        self._rebuild_composition()
        self.resize(WIDTH, self.sizeHint().height())

    # ------------------------------------------------------------------ the parts

    def _first_selection(self) -> Selection:
        group = self.here or (self.offers[0] if self.offers else None)
        if group is None:
            raise ValueError(f"Nothing can be built at {self.ground_object.obj_name}")
        return self._selection_for(group, group.layouts[0])

    def _selection_for(self, group: ForceGroup, layout: TgoLayout) -> Selection:
        key = (id(group), id(layout))
        if key not in self._selections:
            self._selections[key] = Selection(group, layout)
        return self._selections[key]

    def _header(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName(f"buyHeader{id(self)}")
        holder.setStyleSheet(
            f"#{holder.objectName()} {{ background: {PANEL}; border: none; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(16)

        what = QWidget()
        make_transparent(what)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(
            label(
                f"Replace what stands at {self.ground_object.obj_name}",
                16,
                TEXT_PRIMARY,
                bold=True,
            )
        )
        column.addWidget(label(self._what_is_there(), 12, TEXT_LABEL))
        what.setLayout(column)
        row.addWidget(what, 1)

        for name in ("New site", "Refund", "Net", "Budget after"):
            row.addWidget(self._figure(name))
        holder.setLayout(row)
        return holder

    def _what_is_there(self) -> str:
        cp = self.ground_object.control_point
        parts = [cp.name, _slot_name(self.ground_object)]
        units = list(self.ground_object.units)
        if units:
            parts.append(
                f"{len(units)} units worth ${self.refund}M, disbanded and refunded"
            )
        else:
            parts.append("nothing standing")
        return "  ·  ".join(parts)

    def _figure(self, name: str) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        column.addWidget(label(name.upper(), 9.5, TEXT_LABEL, bold=True))
        value = label("", 17, TEXT_PRIMARY, bold=True, monospace=True)
        self.figures[name] = value
        column.addWidget(value)
        holder.setLayout(column)
        return holder

    def _body(self) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        row = QHBoxLayout()
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(16)
        row.addWidget(self._presets(), 0)
        row.addWidget(self._composition(), 1)
        holder.setLayout(row)
        return holder

    def _presets(self) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        holder.setFixedWidth(PRESETS_WIDTH)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(5)
        column.addWidget(
            heading("Presets", f"what {self.ground_object.coalition.faction.name} has")
        )

        section = ""
        for group in sorted(self.offers, key=lambda g: (section_of(g), g.name)):
            if section_of(group) != section:
                section = section_of(group)
                bar = Row(height=24, fill=HEADING_BG)
                bar.add(label(section.upper(), 10, TEXT_LABEL, bold=True))
                bar.stretch()
                self.presets.append(bar)
            self.presets.append(self._preset_row(group))
        self.presets.refresh()
        column.addWidget(_scrolling(self.presets), 1)
        holder.setLayout(column)
        return holder

    def _preset_row(self, group: ForceGroup) -> Row:
        preview = self._selection_for(group, group.layouts[0])
        row = Row(height=48, interactive=True, vertical=True, margins=(14, 6, 14, 6))
        row.body.setSpacing(1)

        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(label(_pretty(group.name), 12.5, TEXT_BASE, bold=True))
        if group is self.here:
            title.addWidget(chip("HERE NOW", ACCENT))
        title.addStretch()
        title.addWidget(label(f"${preview.price}M", 12, TEXT_LABEL, monospace=True))
        row.body.addLayout(title)
        row.body.addWidget(label(_describe(preview), 11, EMPTY))

        row.clicked.connect(partial(self._choose, group))
        self.preset_rows[id(group)] = row
        if group is self.selection.force_group:
            row.set_fill(SELECTED)
        return row

    def _composition(self) -> QWidget:
        holder = QWidget()
        make_transparent(holder)
        self.composition_column = QVBoxLayout()
        self.composition_column.setContentsMargins(0, 0, 0, 0)
        self.composition_column.setSpacing(5)
        self.composition_caption = heading("Composition")
        self.composition_column.addWidget(self.composition_caption)
        self.composition_column.addWidget(_scrolling(self.composition), 1)
        holder.setLayout(self.composition_column)
        return holder

    def _footer(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName(f"buyFooter{id(self)}")
        holder.setStyleSheet(
            f"#{holder.objectName()} {{ background: {PANEL}; border: none; }}"
        )
        row = QHBoxLayout()
        row.setContentsMargins(16, 10, 16, 12)
        row.setSpacing(10)
        row.addWidget(self.shortfall)
        row.addStretch()
        row.addWidget(button("Cancel", handler=self.reject))
        row.addWidget(self.buy_button)
        holder.setLayout(row)
        return holder

    # ------------------------------------------------------------------- changing

    def _choose(self, group: ForceGroup) -> None:
        if group is self.selection.force_group:
            return
        for other_id, row in self.preset_rows.items():
            row.set_fill(SELECTED if other_id == id(group) else "")
        self.selection = self._selection_for(group, group.layouts[0])
        self._rebuild_composition()

    def _choose_layout(self, layout: TgoLayout) -> None:
        self.selection = self._selection_for(self.selection.force_group, layout)
        self._rebuild_composition()

    def _rebuild_composition(self) -> None:
        self.subtotals.clear()
        while self.composition.rows:
            row = self.composition.rows.pop()
            row.setParent(None)

        layouts = self.selection.force_group.layouts
        if self.layout_choice is not None:
            self.layout_choice.setParent(None)
            self.layout_choice = None
        if len(layouts) > 1:
            self.layout_choice = Segmented(
                [(layout.name, layout) for layout in layouts], self.selection.layout
            )
            self.layout_choice.selection_changed.connect(self._choose_layout)
            self.composition_column.insertWidget(1, self.layout_choice)

        for group_name, slots in self.selection.groups:
            units = sum(slot.count for slot in slots)
            price = sum(slot.price for slot in slots)
            bar = Row(height=24, fill=HEADING_BG)
            bar.add(label(group_name.upper(), 10, TEXT_LABEL, bold=True))
            bar.stretch()
            bar.add(label(f"{units} units", 11, TEXT_LABEL))
            bar.add(label(f"${price}M", 11, TEXT_LABEL, monospace=True))
            self.composition.append(bar)
            for slot in slots:
                self.composition.append(self._slot_row(slot))
        self.composition.refresh()
        self._recount()

    def _slot_row(self, slot: Slot) -> Row:
        row = Row(height=44)
        if slot.optional:
            box = QCheckBox()
            box.setChecked(slot.enabled)
            box.stateChanged.connect(partial(self._toggle, slot))
            row.add(box)

        if len(slot.options) > 1:
            combo = QComboBox()
            for option in slot.options:
                combo.addItem(_option_text(option), userData=option)
            combo.setCurrentIndex(slot.chosen)
            combo.currentIndexChanged.connect(partial(self._pick, slot))
            row.add(styled_input(combo, 320))
        else:
            option = slot.option
            row.add(label(option.name, 12.5, TEXT_BASE, bold=True))
            if option.description:
                row.add(label(option.description, 11, TEXT_LABEL))
            row.add(label(f"${option.price}M each", 11, EMPTY, monospace=True))

        row.stretch()
        stepper = QSpinBox()
        stepper.setRange(1, max(1, slot.max_size))
        stepper.setValue(slot.amount)
        stepper.setEnabled(slot.max_size > 1 and slot.enabled)
        stepper.valueChanged.connect(partial(self._amount, slot))
        row.add(styled_input(stepper, 72))

        subtotal = label(f"${slot.price}M", 12, TEXT_BASE, bold=True, monospace=True)
        subtotal.setFixedWidth(72)
        subtotal.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.subtotals[id(slot)] = subtotal
        row.add(subtotal)
        return row

    def _toggle(self, slot: Slot, state: int) -> None:
        slot.enabled = bool(state)
        self._rebuild_composition()

    def _pick(self, slot: Slot, index: int) -> None:
        slot.chosen = index
        self._recount()

    def _amount(self, slot: Slot, value: int) -> None:
        slot.amount = value
        self._recount()

    def _recount(self) -> None:
        """Every figure in the dialog, after any change to the composition."""
        for slot in self.selection.slots:
            subtotal = self.subtotals.get(id(slot))
            if subtotal is not None:
                subtotal.setText(f"${slot.price}M")

        price = self.selection.price
        net = price - self.refund
        budget = int(self.ground_object.coalition.budget)
        after = budget - net

        self.figures["New site"].setText(f"${price}M")
        self.figures["Refund"].setText(f"+${self.refund}M")
        self.figures["Net"].setText(f"{'-' if net > 0 else '+'}${abs(net)}M")
        self.figures["Budget after"].setText(
            f"${after}M" if after >= 0 else f"short ${abs(after)}M"
        )
        _ink(self.figures["Refund"], GREEN if self.refund else TEXT_LABEL)
        _ink(self.figures["Net"], RED if net > 0 else GREEN)
        _ink(self.figures["Budget after"], RED if after < 0 else TEXT_PRIMARY)

        self.composition_caption.setToolTip("")
        affordable = net <= budget
        self.shortfall.setText(
            "" if affordable else f"Short by ${net - budget}M for this composition"
        )
        self.buy_button.setText(f"Buy {_pretty(self.selection.layout.name)}")
        self.buy_button.setEnabled(affordable and self.selection.units > 0)

    def _buy(self) -> None:
        buy(self.selection, self.ground_object, self.game, self.refund)
        self.accept()


def _slot_name(ground_object: TheaterGroundObject) -> str:
    """What kind of slot this is, in the words the presets are grouped by."""
    if isinstance(ground_object, IadsGroundObject):
        return "air-defence slot"
    if isinstance(ground_object, VehicleGroupGroundObject):
        return "armour slot"
    if isinstance(ground_object, ShipGroundObject):
        return "naval slot"
    if isinstance(ground_object, MissileSiteGroundObject):
        return "missile slot"
    if isinstance(ground_object, CoastalSiteGroundObject):
        return "coastal slot"
    return "slot"


def _pretty(name: str) -> str:
    """A campaign identifier as a name: EarlyWarningRadar is three words."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return spaced.replace("_", " ")


def _describe(selection: Selection) -> str:
    prefix, reach = reach_of(selection)
    units = selection.units
    parts = [_pretty(selection.layout.name), f"{units} unit{'s' if units != 1 else ''}"]
    # Under a mile is not a reach worth printing: a gun site or a jammer would read
    # as "1 nm", which says less than nothing.
    if reach.nautical_miles >= 2:
        parts.append(f"{prefix}{reach.nautical_miles:.0f} nm")
    return " · ".join(parts)


def _option_text(option: object) -> str:
    name = getattr(option, "name", "")
    description = getattr(option, "description", "")
    price = getattr(option, "price", 0)
    tail = f" · {description}" if description else ""
    return f"{name}{tail} · ${price}M"


def _ink(widget: QWidget, colour: str) -> None:
    sheet = widget.styleSheet()
    widget.setStyleSheet(f"{sheet} color: {colour};")


def _scrolling(inner: QWidget) -> QWidget:
    holder = QWidget()
    make_transparent(holder)
    column = QVBoxLayout()
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(0)
    column.addWidget(inner)
    column.addStretch()
    holder.setLayout(column)

    area = QScrollArea()
    area.setWidget(holder)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setMinimumHeight(240)
    make_transparent(area)
    return area
