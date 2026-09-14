"""Buying ground units: which class a unit belongs to, and what the filters leave.

A faction's catalogue is twenty-odd rows of identical shape. Grouping them is only
worth anything if every unit lands somewhere a player would look for it, and if
nothing can fall out of the list entirely.
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


def _unit(name: str, unit_class: Any, price: int = 10) -> Any:
    return SimpleNamespace(display_name=name, variant_id=name, unit_class=unit_class)


def _menu(
    grouped: dict[str, list[Any]],
    owned: dict[str, int] | None = None,
    budget: float = 500.0,
    present: int = 12,
    ordered: int = 0,
    limit: int = 27,
) -> Any:
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import (
        ALL,
        QArmorRecruitmentMenu,
    )

    menu = cast(Any, QArmorRecruitmentMenu.__new__(QArmorRecruitmentMenu))
    menu.grouped = grouped
    menu.filter = ALL
    have = owned or {}
    coalition = SimpleNamespace(budget=budget, transfers=[])
    menu.cp = SimpleNamespace(
        captured=SimpleNamespace(is_blue=True),
        frontline_unit_count_limit=limit,
        allocated_ground_units=lambda _transfers: SimpleNamespace(
            total_present=present, total_ordered=ordered
        ),
    )
    menu.game_model = SimpleNamespace(
        game=SimpleNamespace(coalition_for=lambda _player: coalition)
    )
    menu.purchase_adapter = SimpleNamespace(
        price_of=lambda unit: unit.price if hasattr(unit, "price") else 10,
        # Keyed by name: SimpleNamespace defines __eq__ and so is unhashable.
        current_quantity_of=lambda unit: have.get(unit.display_name, 0),
        pending_delivery_quantity=lambda _unit: 0,
    )
    return menu


def test_every_unit_a_faction_offers_lands_in_a_group(qt_app: Any) -> None:
    """A unit with no group would be a unit nobody can buy, which is worse than ugly."""
    from game.data.units import UnitClass
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import group_of

    for unit_class in UnitClass:
        assert group_of(cast(Any, _unit("x", unit_class)))


def test_the_classes_a_player_thinks_in_get_their_own_group(qt_app: Any) -> None:
    from game.data.units import UnitClass
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import group_of

    assert group_of(cast(Any, _unit("Leopard 2A4", UnitClass.TANK))) == "Tanks"
    assert group_of(cast(Any, _unit("LAV-25", UnitClass.APC))) == "IFV / APC"
    assert group_of(cast(Any, _unit("FV510", UnitClass.IFV))) == "IFV / APC"
    # A LAV-25 is RECON in the unit table, but it is what a player looks for under
    # IFV rather than under Infantry.
    assert group_of(cast(Any, _unit("LAV-25", UnitClass.RECON))) == "IFV / APC"
    assert group_of(cast(Any, _unit("Soldier", UnitClass.INFANTRY))) == "Infantry"
    assert group_of(cast(Any, _unit("M109A6", UnitClass.ARTILLERY))) == "Artillery"
    assert group_of(cast(Any, _unit("Avenger", UnitClass.SHORAD))) == "Air defence"
    assert group_of(cast(Any, _unit("M978", UnitClass.LOGISTICS))) == "Logistics"


def test_anything_the_table_does_not_name_still_gets_a_home(qt_app: Any) -> None:
    from game.data.units import UnitClass
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import (
        OTHER,
        group_of,
    )

    assert group_of(cast(Any, _unit("?", UnitClass.UNKNOWN))) == OTHER


def test_a_class_filter_leaves_only_that_class(qt_app: Any) -> None:
    tank = _unit("Leopard 2A4", None)
    gun = _unit("M109A6", None)
    menu = _menu({"Tanks": [tank], "Artillery": [gun]})

    menu.on_filter = lambda choice: None  # no widgets to rebuild in this fixture
    menu.filter = "Tanks"
    assert menu.visible_groups() == [("Tanks", [tank])]


def test_owned_shows_only_what_is_already_here(qt_app: Any) -> None:
    """The usual question at a base is "what do I have", not "what exists"."""
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import OWNED

    here = _unit("Leopard 2A4", None)
    elsewhere = _unit("Challenger 2", None)
    gun = _unit("M109A6", None)
    menu = _menu(
        {"Tanks": [here, elsewhere], "Artillery": [gun]}, owned={"Leopard 2A4": 4}
    )

    menu.filter = OWNED
    assert menu.visible_groups() == [("Tanks", [here])]


def test_owned_at_a_base_holding_nothing_leaves_no_groups(qt_app: Any) -> None:
    from qt_ui.windows.basemenu.ground_forces.QArmorRecruitmentMenu import OWNED

    menu = _menu({"Tanks": [_unit("Leopard 2A4", None)]}, owned={})
    menu.filter = OWNED
    assert menu.visible_groups() == []


def test_the_summary_counts_the_order_against_the_deployable_limit(qt_app: Any) -> None:
    menu = _menu({"Tanks": [_unit("Leopard 2A4", None)]}, present=16, ordered=3)
    units = menu.order_figures()[0]
    assert (units.caption, units.value, units.note) == (
        "units",
        "19/27",
        "· deployable",
    )
    assert not units.warn


def test_ordering_past_the_limit_says_what_will_sit_in_reserve(qt_app: Any) -> None:
    """Over the limit is not refused -- the extras stay at the base -- so it is a
    warning rather than a block, and it should say how many."""
    menu = _menu({"Tanks": [_unit("Leopard 2A4", None)]}, present=25, ordered=6)
    units = menu.order_figures()[0]
    assert units.value == "31/27"
    assert units.note == "· 4 in reserve"
    assert units.warn
