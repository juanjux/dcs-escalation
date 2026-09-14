"""Buying aircraft: what the row says you have, and what the order leaves you with.

The list used to be name-and-price rows under a one-line total, with the parking
figure at the top of the window and the budget in the footer, so the two numbers that
decide an order were never on screen with the row you were ordering from.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def _squadron(
    owned: int = 2,
    pending: int = 0,
    idle: int = 2,
    max_size: int = 12,
    price: int = 20,
    room: bool = True,
    helicopter: bool = False,
) -> Any:
    settings = SimpleNamespace(ground_start_ai_planes=False)
    return SimpleNamespace(
        owned_aircraft=owned,
        pending_deliveries=pending,
        untasked_aircraft=idle,
        max_size=max_size,
        price=price,
        has_aircraft_capacity_for=lambda _count: room,
        destination=None,
        aircraft=SimpleNamespace(
            helicopter=helicopter, lha_capable=False, flyable=True
        ),
        coalition=SimpleNamespace(game=SimpleNamespace(settings=settings)),
    )


def _menu(
    squadrons: list[Any],
    budget: float = 500.0,
    parking: int = 50,
    present: int = 10,
    free_parking: int = 1,
    can_buy: bool = True,
) -> Any:
    """The menu without its widgets: every decision below is arithmetic, not Qt."""
    from qt_ui.windows.basemenu.airfield.QAircraftRecruitmentMenu import (
        QAircraftRecruitmentMenu,
    )

    menu = cast(Any, QAircraftRecruitmentMenu.__new__(QAircraftRecruitmentMenu))
    allocation = SimpleNamespace(
        total=present, total_present=present, total_transferring=0, total_ordered=0
    )
    coalition = SimpleNamespace(budget=budget)
    menu.cp = SimpleNamespace(
        squadrons=squadrons,
        captured=SimpleNamespace(is_blue=True),
        allocated_aircraft=lambda _parking_type: allocation,
        total_aircraft_parking=lambda _parking_type: parking,
        unclaimed_parking=lambda _parking_type: free_parking,
    )
    menu.game_model = SimpleNamespace(
        game=SimpleNamespace(coalition_for=lambda _player: coalition)
    )
    menu.purchase_adapter = SimpleNamespace(
        price_of=lambda squadron: squadron.price,
        can_buy=lambda _squadron: can_buy,
    )
    return menu


def test_a_row_says_what_is_here_the_cap_the_order_and_what_can_fly(
    qt_app: Any,
) -> None:
    """ "6 / 12 max, +3, 6 idle" -- four figures the old "6 (6 idle)" ran together."""
    squadron = _squadron(owned=6, pending=3, idle=6, max_size=12)
    counts = _menu([squadron]).row_counts(squadron)
    assert (counts.present, counts.capacity, counts.pending, counts.idle) == (
        6,
        12,
        3,
        6,
    )


def test_a_row_that_can_take_more_says_nothing(qt_app: Any) -> None:
    squadron = _squadron()
    assert _menu([squadron]).row_warning(squadron) == ""


def test_a_squadron_at_its_cap_says_so_on_the_row(qt_app: Any) -> None:
    """Before the order, not after it is refused."""
    squadron = _squadron(max_size=4, room=False)
    menu = _menu([squadron], can_buy=False)
    assert menu.row_warning(squadron) == "at its cap of 4"


def test_a_base_with_no_parking_free_says_which_kind(qt_app: Any) -> None:
    """A jet cannot take a helipad, so for it the shortage is specifically fixed-wing.

    A helicopter can take either, so for it there is simply no parking free.
    """
    squadron = _squadron()
    menu = _menu([squadron], can_buy=False, free_parking=0)
    assert menu.row_warning(squadron) == "no fixed-wing parking free here"

    helicopter = _squadron(helicopter=True)
    menu = _menu([helicopter], can_buy=False, free_parking=0)
    assert menu.row_warning(helicopter) == "no parking free here"


def test_being_short_of_money_is_never_a_row_warning(qt_app: Any) -> None:
    """It is in the summary above, once, rather than on all twelve rows."""
    squadron = _squadron()
    menu = _menu([squadron], budget=0.0, can_buy=False)
    assert menu.row_warning(squadron) == ""


def test_the_summary_is_parking_cost_and_what_is_left(qt_app: Any) -> None:
    menu = _menu([_squadron(pending=3, price=20)], parking=51, present=11)
    assert [(f.caption, f.value) for f in menu.order_figures()] == [
        ("parking", "11/51"),
        ("cost", "$60M"),
        ("budget left", "$500M"),
    ]
    assert menu.order_figures()[0].note == "· 40 free"


def test_the_summary_warns_when_nothing_on_the_list_is_affordable(qt_app: Any) -> None:
    """A purchase is paid for as it is made, so the budget cannot go negative here.

    What it can do is fall below the cheapest thing in the list, which is the point
    at which the list stops being of any use -- and that is worth saying out loud
    rather than leaving the player to work out from twelve greyed-out steppers.
    """
    menu = _menu([_squadron(price=15), _squadron(price=45)], budget=4.0)
    budget_left = menu.order_figures()[-1]
    assert budget_left.warn
    assert budget_left.note == "· nothing here is affordable"


def test_a_budget_that_covers_the_cheapest_does_not_warn(qt_app: Any) -> None:
    menu = _menu([_squadron(price=15), _squadron(price=45)], budget=15.0)
    assert not menu.order_figures()[-1].warn


def test_an_empty_base_does_not_warn_that_nothing_is_affordable(qt_app: Any) -> None:
    """With nothing to buy there is no cheapest thing, and no complaint to make."""
    menu = _menu([], budget=0.0)
    assert not menu.order_figures()[-1].warn


def test_clearing_the_order_undoes_orders_and_sales_alike(qt_app: Any) -> None:
    """Both directions: a cancelled sale is as much a pending change as a purchase."""
    ordered = _squadron(pending=3)
    sold = _squadron(pending=-2)
    untouched = _squadron(pending=0)
    menu = _menu([ordered, sold, untouched])

    undone: list[tuple[str, int]] = []
    menu.sell = lambda item, count: undone.append(("sell", count))
    menu.buy = lambda item, count: undone.append(("buy", count))
    menu.clear_order()

    assert undone == [("sell", 3), ("buy", 2)]


def test_the_order_cost_is_this_base_s_own_orders(qt_app: Any) -> None:
    menu = _menu([_squadron(pending=2, price=20), _squadron(pending=-1, price=45)])
    assert menu.order_cost() == 2 * 20 - 45
