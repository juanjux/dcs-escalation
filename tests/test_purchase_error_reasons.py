"""A refused purchase says WHY it was refused.

"Cannot buy more X" on its own cannot be acted on: being broke, a full apron and a
squadron at its cap are three different problems with three different answers (wait a
turn, pick another base, pick another squadron). The LLM planner reads the same string
over the API, so it matters there too.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.purchaseadapter import (
    AircraftPurchaseAdapter,
    PurchaseAdapter,
    TransactionError,
)


class _Adapter(PurchaseAdapter[Any]):
    """Minimal concrete adapter: only the budget rule of the base class."""

    def __init__(self, budget: float, price: int) -> None:
        super().__init__(
            SimpleNamespace(budget=budget, adjust_budget=lambda _: None)  # type: ignore[arg-type]
        )
        self._price = price

    def price_of(self, item: Any) -> int:
        return self._price

    def current_quantity_of(self, item: Any) -> int:
        return 0

    def pending_delivery_quantity(self, item: Any) -> int:
        return 0

    def can_sell(self, item: Any) -> bool:
        return False

    def do_purchase(self, item: Any) -> None:
        raise AssertionError("should not be reached")

    def do_cancel_purchase(self, item: Any) -> None: ...

    def do_sale(self, item: Any) -> None: ...

    def do_cancel_sale(self, item: Any) -> None: ...

    def name_of(self, item: Any, multiline: bool = False) -> str:
        return str(item)

    def unit_type_of(self, item: Any) -> Any:
        return None


def test_the_error_names_the_price_and_the_budget() -> None:
    with pytest.raises(TransactionError) as excinfo:
        _Adapter(budget=16.25, price=20).buy("Squadron 035", 1)
    message = str(excinfo.value)
    assert "20" in message and "16.2" in message


def _squadron(owned: int = 0, cap: int = 24) -> Any:
    # ParkingType.from_squadron reaches through the squadron for the ground-start
    # setting, so the fake has to carry that chain too.
    settings = SimpleNamespace(ground_start_ai_planes=False)
    return SimpleNamespace(
        owned_aircraft=owned,
        pending_deliveries=0,
        max_size=cap,
        has_aircraft_capacity_for=lambda n: owned + n <= cap,
        aircraft=SimpleNamespace(price=20, helicopter=True, lha_capable=False),
        coalition=SimpleNamespace(game=SimpleNamespace(settings=settings)),
    )


def _control_point(budget: float, parking: int) -> Any:
    return SimpleNamespace(
        coalition=SimpleNamespace(budget=budget, adjust_budget=lambda _: None),
        unclaimed_parking=lambda _t: parking,
        sunk=False,
        __str__=lambda self: "Beirut-Rafic Hariri",
    )


def test_squadron_out_of_money_reports_the_shortfall() -> None:
    cp = _control_point(budget=16.25, parking=27)
    reason = AircraftPurchaseAdapter(cp).why_cannot_buy(_squadron())
    assert "20" in reason and "16.2" in reason


def test_squadron_with_money_but_no_parking_says_so() -> None:
    cp = _control_point(budget=500, parking=0)
    reason = AircraftPurchaseAdapter(cp).why_cannot_buy(_squadron())
    assert "parking" in reason


def test_squadron_at_its_cap_says_so() -> None:
    cp = _control_point(budget=500, parking=27)
    reason = AircraftPurchaseAdapter(cp).why_cannot_buy(_squadron(owned=24, cap=24))
    assert "cap" in reason and "24" in reason
