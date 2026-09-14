"""Buying ground units: grouped by what they are, filtered, and totalled at the top.

A faction's catalogue is twenty-odd rows of identical shape, so finding the tank you
wanted meant reading every name. They are now broken into the half-dozen classes a
player thinks in, with a filter above them and -- the usual question -- an "Owned"
filter that shows only what is already here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.purchaseadapter import GroundUnitPurchaseAdapter
from game.theater import ControlPoint
from qt_ui.models import GameModel
from qt_ui.widgets.cards import CAPTION, card, make_transparent
from qt_ui.widgets.controls import Segmented
from qt_ui.widgets.squadrondelegate import split_aircraft_name as split_variant
from qt_ui.windows.basemenu.buylist import (
    COMPACT_PRESENT_WIDTH,
    PRICE_WIDTH,
    STEPPER_WIDTH,
    Column,
    ColumnHeaders,
    Figure,
    OrderSummary,
    scrolling,
    group_header,
)

#: The four headings, at the widths the rows lay themselves out to.
COLUMNS = [
    Column("Unit", "unit"),
    Column("Here", "here", COMPACT_PRESENT_WIDTH, descending_first=True),
    Column("Price", "price", PRICE_WIDTH, descending_first=True),
    Column("Order", "order", STEPPER_WIDTH, descending_first=True),
]
from qt_ui.windows.basemenu.UnitTransactionFrame import RowCounts, UnitTransactionFrame

#: The classes a player thinks in, and what falls into each. Order is the order the
#: groups appear in: what fights first, then what supports it.
GROUPS: list[tuple[str, set[UnitClass]]] = [
    ("Tanks", {UnitClass.TANK}),
    # Recon rides with the other wheels: a LAV-25 is what a player looks for under
    # IFV, not under Infantry, whatever the unit table calls it.
    ("IFV / APC", {UnitClass.IFV, UnitClass.APC, UnitClass.RECON}),
    ("Artillery", {UnitClass.ARTILLERY}),
    ("Anti-tank", {UnitClass.ATGM}),
    ("Infantry", {UnitClass.INFANTRY}),
    (
        "Air defence",
        {
            UnitClass.AAA,
            UnitClass.SHORAD,
            UnitClass.MANPAD,
            UnitClass.TELAR,
            UnitClass.MISSILE,
            UnitClass.LAUNCHER,
            UnitClass.SEARCH_RADAR,
            UnitClass.TRACK_RADAR,
            UnitClass.SEARCH_TRACK_RADAR,
            UnitClass.OPTICAL_TRACKER,
            UnitClass.SEARCH_LIGHT,
            UnitClass.EARLY_WARNING_RADAR,
        },
    ),
    ("Logistics", {UnitClass.LOGISTICS}),
]

#: Anything a faction offers that the table above does not name still gets a home,
#: because a unit missing from the list cannot be bought at all.
OTHER = "Other"

ALL = "__all__"
OWNED = "__owned__"


def group_of(unit_type: GroundUnitType) -> str:
    for name, classes in GROUPS:
        if unit_type.unit_class in classes:
            return name
    return OTHER


class QArmorRecruitmentMenu(UnitTransactionFrame[GroundUnitType]):
    def __init__(self, cp: ControlPoint, game_model: GameModel):
        owner = cp.captured
        super().__init__(
            game_model,
            GroundUnitPurchaseAdapter(
                cp,
                game_model.game.coalition_for(owner),
                game_model.game,
                game_model.transfer_model.inventory_changed.emit,
            ),
        )
        self.cp = cp
        self.game_model = game_model
        self.filter: str = ALL

        unit_types = sorted(
            set(game_model.game.faction_for(player=owner).ground_units),
            key=lambda unit: (unit.display_name),
        )
        self.grouped: dict[str, list[GroundUnitType]] = {}
        for unit_type in unit_types:
            self.grouped.setdefault(group_of(unit_type), []).append(unit_type)

        self.order_summary = OrderSummary(
            "After this order", self.order_figures, self.clear_order
        )
        self.headers = ColumnHeaders(COLUMNS, current="unit")
        self.headers.sort_changed.connect(lambda _key: self.rebuild())

        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(0)

        scroll_content = QWidget()
        make_transparent(scroll_content)
        scroll_content.setLayout(self._rows)

        scroll = scrolling(scroll_content)

        inside = QVBoxLayout()
        inside.setContentsMargins(0, 0, 0, 0)
        inside.setSpacing(0)
        inside.addWidget(self.order_summary)
        inside.addWidget(self.headers)
        inside.addWidget(scroll, 1)

        holder = card()
        holder.setLayout(inside)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._filters())
        layout.addWidget(holder, 1)
        self.setLayout(layout)

        self.rebuild()

    # -- the filter bar ------------------------------------------------------

    def _filters(self) -> QWidget:
        options: list[tuple[str, str]] = [("All", ALL)]
        options += [(name, name) for name in self.grouped]
        options.append(("Owned", OWNED))

        self.filters = Segmented(options, current=ALL, fill=False)
        self.filters.selection_changed.connect(self.on_filter)
        return self.filters

    def on_filter(self, choice: str) -> None:
        self.filter = choice
        self.rebuild()

    def visible_groups(self) -> list[tuple[str, list[GroundUnitType]]]:
        """What the current filter leaves, with empty groups dropped."""
        groups = []
        for name, unit_types in self.grouped.items():
            if self.filter not in (ALL, OWNED) and name != self.filter:
                continue
            if self.filter == OWNED:
                unit_types = [u for u in unit_types if self.current_quantity_of(u)]
            if unit_types:
                groups.append((name, unit_types))
        return groups

    def in_order(self, unit_types: list[GroundUnitType]) -> list[GroundUnitType]:
        """Sorted inside its group, because the grouping is what makes it readable.

        Sorting the whole catalogue by price would throw away the classes, which is
        the half of this list worth keeping.
        """
        key = self.headers.current
        if key == "here":
            order = lambda u: (  # noqa: E731
                self.current_quantity_of(u),
                u.display_name,
            )
        elif key == "price":
            order = lambda u: (self.price_of(u), u.display_name)  # noqa: E731
        elif key == "order":
            order = lambda u: (  # noqa: E731
                self.pending_delivery_quantity(u),
                u.display_name,
            )
        else:
            order = lambda u: (u.display_name,)  # noqa: E731
        return sorted(unit_types, key=order, reverse=not self.headers.ascending)

    def rebuild(self) -> None:
        """Redraw the list. The order survives, because it lives on the game."""
        while self._rows.count():
            taken = self._rows.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.deleteLater()
        self.styled_rows.clear()
        self.purchase_groups.clear()

        groups = self.visible_groups()
        if not groups:
            self._rows.addWidget(
                _nothing(
                    "Nothing here yet."
                    if self.filter == OWNED
                    else "This faction has nothing of that kind."
                )
            )
        for name, unit_types in groups:
            # One group and nothing else on screen does not need naming twice: the
            # filter button already says which one it is.
            if len(groups) > 1:
                self._rows.addWidget(group_header(name, len(unit_types)))
            for unit_type in self.in_order(unit_types):
                self._rows.addWidget(self.add_styled_row(unit_type, compact=True))
        self._rows.addStretch()

    # -- what the rows say ---------------------------------------------------

    def row_title(self, item: GroundUnitType) -> tuple[str, str]:
        # Through the adapter rather than off the unit, so the name is a string
        # whatever the catalogue holds, and the variant in brackets drops to grey.
        return split_variant(self.display_name_of(item))

    def row_counts(self, item: GroundUnitType) -> RowCounts:
        return RowCounts(
            present=self.current_quantity_of(item),
            capacity=None,
            pending=self.pending_delivery_quantity(item),
            idle=None,
        )

    def row_warning(self, item: GroundUnitType) -> str:
        """Only the structural reasons; being short of money is in the summary."""
        return ""

    # -- what the summary says -----------------------------------------------

    def order_figures(self) -> list[Figure]:
        transfers = self.game_model.game.coalition_for(self.cp.captured).transfers
        allocation = self.cp.allocated_ground_units(transfers)
        limit = self.cp.frontline_unit_count_limit
        after = allocation.total_present + allocation.total_ordered

        figures = [
            Figure(
                "units",
                f"{after}/{limit}",
                "· deployable" if after <= limit else f"· {after - limit} in reserve",
                warn=after > limit,
            ),
            Figure("cost", f"${self.order_cost()}M"),
        ]

        budget = self.game_model.game.coalition_for(self.cp.captured).budget
        cheapest = min((self.price_of(unit) for unit in self.catalogue()), default=0)
        figures.append(
            Figure(
                "budget left",
                f"${budget:.0f}M",
                "· nothing here is affordable" if budget < cheapest else "",
                warn=bool(cheapest) and budget < cheapest,
            )
        )
        return figures

    def catalogue(self) -> list[GroundUnitType]:
        """Everything this list can show, filters aside."""
        return [unit for units in self.grouped.values() for unit in units]

    def order_cost(self) -> int:
        return sum(
            self.pending_delivery_quantity(unit) * self.price_of(unit)
            for unit in self.catalogue()
        )

    def clear_order(self) -> None:
        """Undo everything ordered or sold at this base, in one click."""
        for unit in self.catalogue():
            pending = self.pending_delivery_quantity(unit)
            if pending > 0:
                self.sell(unit, pending)
            elif pending < 0:
                self.buy(unit, -pending)

    def post_transaction_update(self) -> None:
        super().post_transaction_update()
        # "Owned" is a list of what is here, so buying the first of something has to
        # put it on the list.
        if self.filter == OWNED:
            self.rebuild()


def _nothing(text: str) -> QWidget:
    label = QLabel(text)
    label.setStyleSheet(
        f"font-size: 11.5px; color: {CAPTION}; background: transparent;"
        " border: none; padding: 14px;"
    )
    return label
