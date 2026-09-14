"""Clicking a column heading sorts the buy list by it.

The lists were sorted by name and by nothing else, so "what have I got most of" and
"what is cheap" were questions you answered by reading every row.
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


def _squadron(aircraft: str, name: str, owned: int, price: int, pending: int) -> Any:
    return SimpleNamespace(
        aircraft=SimpleNamespace(display_name=aircraft),
        name=name,
        owned_aircraft=owned,
        price=price,
        pending_deliveries=pending,
    )


def _aircraft_menu(squadrons: list[Any]) -> Any:
    from qt_ui.windows.basemenu.airfield.QAircraftRecruitmentMenu import (
        COLUMNS,
        QAircraftRecruitmentMenu,
    )
    from qt_ui.windows.basemenu.buylist import ColumnHeaders

    menu = cast(Any, QAircraftRecruitmentMenu.__new__(QAircraftRecruitmentMenu))
    menu.cp = SimpleNamespace(squadrons=squadrons)
    menu.purchase_adapter = SimpleNamespace(price_of=lambda s: s.price)
    menu.headers = ColumnHeaders(COLUMNS, current="squadron")
    return menu


def _names(menu: Any) -> list[str]:
    return [s.aircraft.display_name for s in menu.sorted_squadrons()]


def _fleet() -> list[Any]:
    return [
        _squadron("F-15C Eagle", "1st", owned=2, price=35, pending=0),
        _squadron("A-10C Thunderbolt II", "2nd", owned=9, price=20, pending=3),
        _squadron("KC-135 Stratotanker", "3rd", owned=0, price=60, pending=1),
    ]


def test_it_opens_sorted_by_name(qt_app: Any) -> None:
    """The list's first job is still finding the squadron you had in mind."""
    assert _names(_aircraft_menu(_fleet()))[0] == "A-10C Thunderbolt II"


def test_the_present_column_starts_with_the_most(qt_app: Any) -> None:
    """Reading "who has none" from the top answers nothing; "who has most" does."""
    menu = _aircraft_menu(_fleet())
    menu.headers.clicked("present")
    assert _names(menu) == [
        "A-10C Thunderbolt II",
        "F-15C Eagle",
        "KC-135 Stratotanker",
    ]


def test_clicking_the_same_column_again_turns_it_round(qt_app: Any) -> None:
    menu = _aircraft_menu(_fleet())
    menu.headers.clicked("present")
    menu.headers.clicked("present")
    assert _names(menu)[0] == "KC-135 Stratotanker"


def test_price_and_order_sort_by_their_own_figures(qt_app: Any) -> None:
    menu = _aircraft_menu(_fleet())
    menu.headers.clicked("price")
    assert _names(menu)[0] == "KC-135 Stratotanker"

    menu.headers.clicked("order")
    assert _names(menu)[0] == "A-10C Thunderbolt II"


def test_moving_to_a_name_column_starts_at_the_top_of_the_alphabet(
    qt_app: Any,
) -> None:
    """Each column has its own useful direction, so the arrow follows the column."""
    menu = _aircraft_menu(_fleet())
    menu.headers.clicked("present")
    menu.headers.clicked("squadron")
    assert menu.headers.ascending
    assert _names(menu)[0] == "A-10C Thunderbolt II"


def _unit(name: str, price: int) -> Any:
    return SimpleNamespace(display_name=name, price=price)


def _ground_menu(units: list[Any], owned: dict[str, int]) -> Any:
    from qt_ui.windows.basemenu.buylist import ColumnHeaders
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import (
        COLUMNS,
        QArmorRecruitmentMenu,
    )

    menu = cast(Any, QArmorRecruitmentMenu.__new__(QArmorRecruitmentMenu))
    menu.grouped = {"Tanks": units}
    menu.headers = ColumnHeaders(COLUMNS, current="unit")
    menu.purchase_adapter = SimpleNamespace(
        price_of=lambda u: u.price,
        current_quantity_of=lambda u: owned.get(u.display_name, 0),
        pending_delivery_quantity=lambda _u: 0,
    )
    return menu


def test_the_ground_list_sorts_inside_its_groups(qt_app: Any) -> None:
    """Sorting the whole catalogue by price would throw the classes away, and the
    classes are the half of that list worth keeping."""
    units = [_unit("Challenger 2", 25), _unit("Leopard 2A4", 20), _unit("M1A2", 30)]
    menu = _ground_menu(units, owned={"Leopard 2A4": 4})

    menu.headers.clicked("price")
    assert [u.display_name for u in menu.in_order(units)] == [
        "M1A2",
        "Challenger 2",
        "Leopard 2A4",
    ]

    menu.headers.clicked("here")
    assert [u.display_name for u in menu.in_order(units)][0] == "Leopard 2A4"
