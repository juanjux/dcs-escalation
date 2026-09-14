"""Buying aircraft: squadron rows, and what the order leaves you with pinned above.

The list used to be name-and-price rows under a one-line hangar total, so deciding
whether to order six more meant reading the parking figure at the top of the window,
the price on the row, and the budget in the footer, in three different places. The
rows now look like the Air Wing list -- silhouette, type, task, squadron -- and the
two numbers that decide the order sit above them and stay there while you scroll.
"""

from typing import Optional

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from game.purchaseadapter import AircraftPurchaseAdapter
from game.squadrons import Squadron
from game.theater import ControlPoint, ParkingType
from qt_ui.models import GameModel, SquadronModel
from qt_ui.uiconstants import AIRCRAFT_ICONS
from qt_ui.widgets.cards import CAPTION, card, make_transparent
from qt_ui.widgets.squadrondelegate import chip_colours, split_aircraft_name
from qt_ui.windows.basemenu.buylist import (
    ICON_WIDTH,
    PRESENT_WIDTH,
    PRICE_WIDTH,
    STEPPER_WIDTH,
    Column,
    ColumnHeaders,
    Figure,
    OrderSummary,
    scrolling,
)

#: The four headings, at the widths the rows lay themselves out to.
COLUMNS = [
    Column("Squadron", "squadron"),
    Column("Present", "present", PRESENT_WIDTH, descending_first=True),
    Column("Price", "price", PRICE_WIDTH, descending_first=True),
    Column("Order", "order", STEPPER_WIDTH, descending_first=True),
]
from qt_ui.windows.basemenu.UnitTransactionFrame import RowCounts, UnitTransactionFrame

#: Every kind of parking, because the list holds every kind of squadron.
EVERY_PARKING = ParkingType(fixed_wing=True, fixed_wing_stol=True, rotary_wing=True)


class QAircraftRecruitmentMenu(UnitTransactionFrame[Squadron]):
    def __init__(self, cp: ControlPoint, game_model: GameModel) -> None:
        super().__init__(game_model, AircraftPurchaseAdapter(cp))
        self.cp = cp
        self.game_model = game_model

        self.order_summary = OrderSummary(
            "After this order", self.order_figures, self.clear_order
        )

        self.headers = ColumnHeaders(
            COLUMNS, left_margin=14 + ICON_WIDTH + 10, current="squadron"
        )
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

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        main_layout.addWidget(holder, 1)

        incoming = sorted(
            (s for s in cp.coalition.air_wing.iter_squadrons() if s.destination == cp),
            key=lambda s: (s.aircraft.display_name, s.name),
        )
        if incoming:
            arriving = QLabel(
                "Arriving next turn: "
                + " · ".join(
                    f"{s} — {s.owned_aircraft} {s.aircraft.display_name} "
                    f"from {s.location.name}"
                    for s in incoming
                )
            )
            arriving.setWordWrap(True)
            arriving.setStyleSheet(
                f"font-size: 11px; color: {CAPTION}; background: transparent;"
                " border: none;"
            )
            main_layout.addWidget(arriving)

        self.setLayout(main_layout)
        self.rebuild()

    # -- the order of the list -----------------------------------------------

    def sorted_squadrons(self) -> list[Squadron]:
        key = self.headers.current
        if key == "present":
            order = lambda s: (s.owned_aircraft, s.aircraft.display_name)  # noqa: E731
        elif key == "price":
            order = lambda s: (self.price_of(s), s.aircraft.display_name)  # noqa: E731
        elif key == "order":
            order = lambda s: (
                s.pending_deliveries,
                s.aircraft.display_name,
            )  # noqa: E731
        else:
            order = lambda s: (s.aircraft.display_name, s.name)  # noqa: E731
        return sorted(self.cp.squadrons, key=order, reverse=not self.headers.ascending)

    def rebuild(self) -> None:
        while self._rows.count():
            taken = self._rows.takeAt(0)
            widget = taken.widget()
            if widget is not None:
                widget.deleteLater()
        self.styled_rows.clear()
        self.purchase_groups.clear()

        for squadron in self.sorted_squadrons():
            self._rows.addWidget(self.add_styled_row(squadron))
        self._rows.addStretch()

    # -- what the rows say ---------------------------------------------------

    def row_icon(self, item: Squadron) -> Optional[QPixmap]:
        # Slashes are not allowed in filenames, so the icons are stored without them.
        name = item.aircraft.dcs_id.replace("/", "_")
        return AIRCRAFT_ICONS.get(name)

    def row_title(self, item: Squadron) -> tuple[str, str]:
        return split_aircraft_name(item.aircraft.display_name)

    def row_chips(self, item: Squadron) -> list[tuple[str, str, str]]:
        fill, ink = chip_colours(item.primary_task)
        return [(item.primary_task.value, fill.name(), ink.name())]

    def row_subtitle(self, item: Squadron) -> str:
        text = str(item)
        if item.destination is not None:
            text += f" · transfer ordered to {item.destination.name}"
        return text

    def row_warning(self, item: Squadron) -> str:
        """Why no more can be based here -- but never that you are short of money.

        The budget is in the summary above, and repeating "costs 20M, you have 5M"
        on every row of a list you cannot afford says nothing the summary has not.
        """
        if self.enable_purchase(item):
            return ""
        if self.cp.unclaimed_parking(ParkingType().from_squadron(item)) <= 0:
            # A helicopter can take a ramp slot, so what is full is "parking"; a jet
            # cannot take a helipad, so for it the shortage is specifically fixed-wing.
            kind = "" if item.aircraft.helicopter else "fixed-wing "
            return f"no {kind}parking free here"
        if not item.has_aircraft_capacity_for(1):
            return f"at its cap of {item.max_size}"
        return ""

    def row_counts(self, item: Squadron) -> RowCounts:
        return RowCounts(
            present=item.owned_aircraft,
            capacity=item.max_size,
            pending=item.pending_deliveries,
            idle=item.untasked_aircraft,
        )

    # -- what the summary says -----------------------------------------------

    def order_figures(self) -> list[Figure]:
        allocation = self.cp.allocated_aircraft(EVERY_PARKING)
        parking = self.cp.total_aircraft_parking(EVERY_PARKING)
        free = max(parking - allocation.total, 0)

        figures = [
            Figure("parking", f"{allocation.total}/{parking}", f"· {free} free"),
            Figure("cost", f"${self.order_cost()}M"),
        ]

        budget = self.game_model.game.coalition_for(self.cp.captured).budget
        # A purchase is paid for the moment it is made, so the budget can never go
        # negative here; what it can do is fall below the cheapest thing on the list,
        # which is the point at which the list stops being of any use.
        cheapest = min(
            (self.price_of(squadron) for squadron in self.cp.squadrons), default=0
        )
        figures.append(
            Figure(
                "budget left",
                f"${budget:.0f}M",
                "· nothing here is affordable" if budget < cheapest else "",
                warn=bool(cheapest) and budget < cheapest,
            )
        )
        return figures

    def order_cost(self) -> int:
        return sum(
            squadron.pending_deliveries * self.price_of(squadron)
            for squadron in self.cp.squadrons
        )

    def clear_order(self) -> None:
        """Undo everything ordered or sold at this base, in one click."""
        for squadron in list(self.cp.squadrons):
            pending = squadron.pending_deliveries
            if pending > 0:
                self.sell(squadron, pending)
            elif pending < 0:
                self.buy(squadron, -pending)

    # -- the rest is unchanged -----------------------------------------------

    def sell_tooltip(self, is_enabled: bool) -> str:
        if is_enabled:
            return "Sell unit. Use Shift or Ctrl key to sell multiple units at once."
        else:
            return (
                "Can not be sold because either no aircraft are available or are "
                "already assigned to a mission."
            )

    def supports_item_dialog(self) -> bool:
        return True

    def on_item_clicked(self, item: Squadron) -> None:
        from qt_ui.dialogs import open_once
        from qt_ui.windows.SquadronDialog import SquadronDialog

        self.squadron_dialog = open_once(
            f"squadron:{item.id}",
            lambda: SquadronDialog(
                self.game_model.ato_model,
                SquadronModel(item),
                self.game_model.game.theater,
                self.game_model.sim_controller,
                self,
            ),
        )
