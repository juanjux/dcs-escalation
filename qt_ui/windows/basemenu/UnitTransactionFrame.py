from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Optional, TypeVar

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from game.purchaseadapter import PurchaseAdapter, TransactionError
from qt_ui.models import GameModel
from qt_ui.widgets.controls import BORDER as BORDER_INK, mono
from qt_ui.windows.basemenu.buylist import (
    AMBER as ORDERED_INK,
    OrderSummary,
    PurchaseRow,
    QUIET as QUIET_INK,
)
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.QUnitInfoWindow import QUnitInfoWindow


class RecruitType(Enum):
    BUY = 0
    SELL = 1


class ClickableLabel(QLabel):
    """A QLabel that invokes a callback when left-clicked."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._on_click: Optional[Callable[[], None]] = None

    def set_on_click(self, callback: Callable[[], None]) -> None:
        self._on_click = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


TransactionItemType = TypeVar("TransactionItemType")


@dataclass(frozen=True)
class RowCounts:
    """What a buy row says you have: here now, the cap, on order, and free to fly."""

    present: int
    capacity: Optional[int]
    pending: int
    idle: Optional[int]


class PurchaseGroup(QGroupBox, Generic[TransactionItemType]):
    def __init__(
        self,
        item: TransactionItemType,
        recruiter: UnitTransactionFrame[TransactionItemType],
        stepper: bool = False,
    ) -> None:
        super().__init__()
        self.item = item
        self.recruiter = recruiter
        self.stepper = stepper

        if not stepper:
            self.setProperty("style", "buy-box")
            self.setMaximumHeight(72)
            self.setMinimumHeight(36)
        else:
            # Flat inside a buy row: the row already carries the frame, and a box
            # around three buttons inside a boxed row is two frames deep.
            self.setFlat(True)
            self.setStyleSheet("QGroupBox { border: none; margin: 0; padding: 0; }")
        layout = QHBoxLayout()
        if stepper:
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        self.setLayout(layout)

        self.sell_button = QPushButton("-" if not stepper else "\u2212")
        self.sell_button.setProperty("style", "btn-sell")
        self.sell_button.setDisabled(not recruiter.enable_sale(item))
        self.sell_button.setVisible(recruiter.enable_sale(item))
        self._size(self.sell_button, 28 if stepper else 16)
        if stepper:
            # Hidden but still taking up its space: a row that cannot sell used to be
            # 28 px narrower than the ones around it, which pulled its price and its
            # count out of line with the whole column.
            policy = self.sell_button.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            self.sell_button.setSizePolicy(policy)

        self.sell_button.clicked.connect(
            lambda: self.recruiter.recruit_handler(RecruitType.SELL, self.item)
        )

        self.amount_bought = QLabel()
        self.amount_bought.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )
        if stepper:
            self.amount_bought.setFixedSize(40, 28)
            self.amount_bought.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.amount_bought.setFont(mono(13))

        self.buy_button = QPushButton("+")
        self.buy_button.setProperty("style", "btn-buy")
        self.buy_button.setDisabled(not recruiter.enable_purchase(item))
        self._size(self.buy_button, 28 if stepper else 16)

        self.buy_button.clicked.connect(
            lambda: self.recruiter.recruit_handler(RecruitType.BUY, self.item)
        )

        layout.addWidget(self.sell_button)
        layout.addWidget(self.amount_bought)
        layout.addWidget(self.buy_button)

        self.update_state()

    @staticmethod
    def _size(button: QPushButton, side: int) -> None:
        button.setMinimumSize(side, side)
        button.setMaximumSize(side, side)
        button.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

    @property
    def pending_units(self) -> int:
        return self.recruiter.pending_delivery_quantity(self.item)

    def update_state(self) -> None:
        self.buy_button.setEnabled(self.recruiter.enable_purchase(self.item))
        self.buy_button.setToolTip(
            self.recruiter.purchase_tooltip(self.buy_button.isEnabled())
        )
        self.sell_button.setEnabled(self.recruiter.enable_sale(self.item))
        self.sell_button.setVisible(self.recruiter.enable_sale(self.item))
        self.sell_button.setToolTip(
            self.recruiter.sell_tooltip(self.sell_button.isEnabled())
        )
        self.amount_bought.setText(f"<b>{self.pending_units}</b>")
        if self.stepper:
            colour = ORDERED_INK if self.pending_units else QUIET_INK
            edge = colour if self.pending_units else BORDER_INK
            PurchaseRow.restyle(
                self.amount_bought,
                f"color: {colour}; background: #14202B;"
                f" border-top: 1px solid {edge};"
                f" border-bottom: 1px solid {edge};",
            )


class UnitTransactionFrame(QFrame, Generic[TransactionItemType]):
    BUDGET_FORMAT = "Available Budget: <b>${:.2f}M</b>"

    def __init__(
        self,
        game_model: GameModel,
        purchase_adapter: PurchaseAdapter[TransactionItemType],
    ) -> None:
        super().__init__()
        self.game_model = game_model
        self.purchase_adapter = purchase_adapter
        self.existing_units_labels = {}
        self.purchase_groups: dict[
            TransactionItemType, PurchaseGroup[TransactionItemType]
        ] = {}
        self.styled_rows: dict[TransactionItemType, PurchaseRow] = {}
        self.order_summary: Optional[OrderSummary] = None
        self._repaint_pending = False
        self.game_model.transfer_model.inventory_changed.connect(
            self.post_transaction_update
        )
        self.update_available_budget()

    def current_quantity_of(self, item: TransactionItemType) -> int:
        return self.purchase_adapter.current_quantity_of(item)

    def pending_delivery_quantity(self, item: TransactionItemType) -> int:
        return self.purchase_adapter.pending_delivery_quantity(item)

    def expected_quantity_next_turn(self, item: TransactionItemType) -> int:
        return self.purchase_adapter.expected_quantity_next_turn(item)

    def display_name_of(
        self, item: TransactionItemType, multiline: bool = False
    ) -> str:
        return self.purchase_adapter.name_of(item, multiline)

    def price_of(self, item: TransactionItemType) -> int:
        return self.purchase_adapter.price_of(item)

    def existing_units_text(self, item: TransactionItemType, count: int) -> str:
        """Text for the current-quantity label. Subclasses may add detail."""
        return str(count)

    def supports_item_dialog(self) -> bool:
        """Whether clicking an item's name opens a detail dialog."""
        return False

    def stacked_existing_units(self) -> bool:
        """Whether the existing-units label sits below the name (vs. beside).

        Useful when that label can hold long text that would otherwise widen
        the row and force a horizontal scrollbar.
        """
        return False

    def on_item_clicked(self, item: TransactionItemType) -> None:
        """Handle a click on an item's name. No-op unless overridden."""
        return None

    @property
    def budget(self) -> float:
        return self.game_model.game.blue.budget

    @budget.setter
    def budget(self, value: int) -> None:
        self.game_model.game.blue.budget = value

    # -- what a styled buy row reads -----------------------------------------
    #
    # Defaults that describe anything: a subclass overrides only what it can say
    # better. Nothing here reaches into the item, so the row widget never learns
    # what a squadron or a unit type is.

    def row_icon(self, item: TransactionItemType) -> Optional[QPixmap]:
        """The thing's own silhouette, as the Air Wing list paints it."""
        return None

    def row_title(self, item: TransactionItemType) -> tuple[str, str]:
        """Its name, and the variant that distinguishes it from its siblings."""
        return self.display_name_of(item), ""

    def row_chips(self, item: TransactionItemType) -> list[tuple[str, str, str]]:
        """(text, fill, ink) for each chip beside the name."""
        return []

    def row_subtitle(self, item: TransactionItemType) -> str:
        return ""

    def row_warning(self, item: TransactionItemType) -> str:
        """Why this row cannot take another one, in a few words, or nothing."""
        if self.enable_purchase(item):
            return ""
        return self.purchase_adapter.why_cannot_buy(item)

    def row_counts(self, item: TransactionItemType) -> RowCounts:
        return RowCounts(
            present=self.current_quantity_of(item),
            capacity=None,
            pending=self.pending_delivery_quantity(item),
            idle=None,
        )

    def order_control(self, item: TransactionItemType) -> QWidget:
        """The stepper, remembered so a transaction anywhere updates every row."""
        group: PurchaseGroup[TransactionItemType] = PurchaseGroup(
            item, self, stepper=True
        )
        self.purchase_groups[item] = group
        return group

    def add_styled_row(
        self, item: TransactionItemType, compact: bool = False
    ) -> QWidget:
        row = PurchaseRow(item, self, compact=compact)
        self.styled_rows[item] = row
        return row

    def add_purchase_row(
        self,
        item: TransactionItemType,
        layout: QGridLayout,
        row: int,
    ) -> None:
        stacked = self.stacked_existing_units()
        exist = QGroupBox()
        exist.setProperty("style", "buy-box")
        exist.setMaximumHeight(96 if stacked else 72)
        exist.setMinimumHeight(36)
        existLayout = QHBoxLayout()
        existLayout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        exist.setLayout(existLayout)

        existing_count = self.current_quantity_of(item)

        display = self.display_name_of(item, multiline=True)
        clickable = self.supports_item_dialog()
        if clickable:
            unitName = ClickableLabel(f"<b><u>{display}</u></b>")
        else:
            unitName = ClickableLabel(f"<b>{display}</b>")
        unitName.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        if clickable:
            unitName.set_on_click(lambda: self.on_item_clicked(item))

        existing_units = QLabel(self.existing_units_text(item, existing_count))
        if stacked:
            existing_units.setWordWrap(True)
            existing_units.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            )
        else:
            existing_units.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            )

        self.existing_units_labels[item] = existing_units

        price = QLabel(f"<b>$ {self.price_of(item)}</b> M")
        price.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

        purchase_group = PurchaseGroup(item, self)
        self.purchase_groups[item] = purchase_group

        info = QGroupBox()
        info.setProperty("style", "buy-box")
        info.setMaximumHeight(72)
        info.setMinimumHeight(36)
        infolayout = QHBoxLayout()
        info.setLayout(infolayout)

        unitInfo = QPushButton("i")
        unitInfo.setProperty("style", "btn-info")
        unitInfo.setMinimumSize(16, 16)
        unitInfo.setMaximumSize(16, 16)
        unitInfo.clicked.connect(lambda: self.info(item))
        unitInfo.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        )

        if stacked:
            name_box = QVBoxLayout()
            name_box.addWidget(unitName)
            name_box.addWidget(existing_units)
            existLayout.addLayout(name_box)
            existLayout.addItem(
                QSpacerItem(
                    20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
            )
            existLayout.addWidget(price)
        else:
            existLayout.addWidget(unitName)
            existLayout.addItem(
                QSpacerItem(
                    20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
            )
            existLayout.addWidget(existing_units)
            existLayout.addItem(
                QSpacerItem(
                    20, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
            )
            existLayout.addWidget(price)

        infolayout.addWidget(unitInfo)

        layout.addWidget(exist, row, 1)
        layout.addWidget(purchase_group, row, 2)
        layout.addWidget(info, row, 3)

    def update_available_budget(self) -> None:
        GameUpdateSignal.get_instance().updateBudget(self.game_model.game)

    def recruit_handler(
        self, recruit_type: RecruitType, item: TransactionItemType
    ) -> None:
        # Lookup if Keyboard Modifiers were pressed
        # Shift = 10 times
        # CTRL = 5 Times
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            amount = 10
        elif modifiers == Qt.KeyboardModifier.ControlModifier:
            amount = 5
        else:
            amount = 1

        if recruit_type == RecruitType.SELL:
            self.sell(item, amount)
        elif recruit_type == RecruitType.BUY:
            self.buy(item, amount)

    def post_transaction_update(self) -> None:
        self.update_purchase_controls()
        self.update_existing_units()
        self.update_available_budget()

    def update_existing_units(self) -> None:
        for item, label in self.existing_units_labels.items():
            label.setText(str(self.current_quantity_of(item)))
        # Once for a burst of signals: a ground purchase emits three, and each of
        # them used to restyle every row in the list.
        if self._repaint_pending:
            return
        self._repaint_pending = True
        QTimer.singleShot(0, self.repaint_rows)

    def repaint_rows(self) -> None:
        self._repaint_pending = False
        for row in self.styled_rows.values():
            row.refresh()
        if self.order_summary is not None:
            self.order_summary.refresh()

    def buy(self, item: TransactionItemType, quantity: int) -> None:
        try:
            self.purchase_adapter.buy(item, quantity)
        except TransactionError as ex:
            logging.exception(f"Purchase of {self.display_name_of(item)} failed")
            QMessageBox.warning(
                self, "Purchase failed", str(ex), QMessageBox.StandardButton.Ok
            )
        finally:
            self.post_transaction_update()

    def sell(self, item: TransactionItemType, quantity: int) -> None:
        try:
            self.purchase_adapter.sell(item, quantity)
        except TransactionError as ex:
            logging.exception(f"Sale of {self.display_name_of(item)} failed")
            QMessageBox.warning(
                self, "Sale failed", str(ex), QMessageBox.StandardButton.Ok
            )
        finally:
            self.post_transaction_update()

    def update_purchase_controls(self) -> None:
        for group in self.purchase_groups.values():
            group.update_state()

    def enable_purchase(self, item: TransactionItemType) -> bool:
        return self.purchase_adapter.can_buy(item)

    def enable_sale(self, item: TransactionItemType) -> bool:
        return self.purchase_adapter.can_sell_or_cancel(item)

    @staticmethod
    def purchase_tooltip(is_enabled: bool) -> str:
        if is_enabled:
            return "Buy unit. Use Shift or Ctrl key to buy multiple units at once."
        else:
            return "Unit can not be bought."

    @staticmethod
    def sell_tooltip(is_enabled: bool) -> str:
        if is_enabled:
            return "Sell unit. Use Shift or Ctrl key to buy multiple units at once."
        else:
            return "Unit can not be sold."

    def info(self, item: TransactionItemType) -> None:
        self.info_window = QUnitInfoWindow(
            self.game_model.game, self.purchase_adapter.unit_type_of(item)
        )
        self.info_window.show()
