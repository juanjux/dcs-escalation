"""Vehicle repair refunds and per-unit map labels."""

from types import SimpleNamespace
from typing import Any

import pytest

from game.buildingrepair import (
    cancel_unit_repairs,
    pending_unit_repairs,
    unit_repair_refunds,
)
from game.theater.theatergroup import SceneryUnit, TheaterUnit


def _unit(uid: int, price: float, **kwargs: Any) -> Any:
    state = dict(
        id=uid,
        alive=False,
        repairable=True,
        repair_turns_remaining=2,
        unit_type=SimpleNamespace(price=price),
        repair_cost_paid=None,
    )
    state.update(kwargs)
    return SimpleNamespace(**state)


def test_legacy_jammer_and_cram_refund_their_individual_prices() -> None:
    jammer, cram = _unit(1, 8), _unit(2, 15)
    site: Any = SimpleNamespace(units=[jammer, cram])
    assert unit_repair_refunds(site) == {1: 8, 2: 15}
    assert cancel_unit_repairs(site, [jammer]) == 8
    assert not jammer.alive
    assert jammer.repair_turns_remaining is None
    assert cram.repair_turns_remaining == 2
    with pytest.raises(ValueError):
        cancel_unit_repairs(site, [jammer])
    assert cancel_unit_repairs(site, [cram]) == 15


def test_new_unit_refunds_its_receipt_not_a_changed_unit_price() -> None:
    unit = _unit(1, 100, repair_cost_paid=12.5)
    site: Any = SimpleNamespace(units=[unit])
    assert cancel_unit_repairs(site, [unit]) == 12.5
    assert unit.repair_cost_paid is None


@pytest.mark.parametrize(
    "kwargs",
    [dict(alive=True), dict(repair_turns_remaining=None), dict(repairable=False)],
)
def test_completed_live_and_nonrepairable_units_cannot_refund(kwargs: Any) -> None:
    unit = _unit(1, 8, **kwargs)
    site: Any = SimpleNamespace(units=[unit])
    assert pending_unit_repairs(site) == []
    with pytest.raises(ValueError):
        cancel_unit_repairs(site, [unit])


@pytest.mark.parametrize("selection", [[], [1, 1], [1, 3]])
def test_invalid_selection_changes_no_units(selection: list[int]) -> None:
    units = {i: _unit(i, 8) for i in range(1, 4)}
    site: Any = SimpleNamespace(units=[units[1], units[2]])
    with pytest.raises(ValueError):
        cancel_unit_repairs(site, [units[i] for i in selection])
    assert all(unit.repair_turns_remaining == 2 for unit in units.values())


@pytest.mark.parametrize("cls", [TheaterUnit, SceneryUnit])
@pytest.mark.parametrize(
    "alive, turns, suffix",
    [
        (True, None, ""),
        (True, 2, ""),
        (False, None, " [DEAD]"),
        (False, 2, " [REPAIRING]"),
    ],
)
def test_unit_names_distinguish_repairing_from_destroyed(
    cls: Any, alive: bool, turns: int | None, suffix: str, monkeypatch: Any
) -> None:
    monkeypatch.setattr(TheaterUnit, "unit_type", property(lambda unit: None))
    unit = cls.__new__(cls)
    unit.id = 112
    unit.name = "Power generator"
    unit.alive = alive
    unit.repair_turns_remaining = turns
    assert unit.display_name == f"0112 | Power generator{suffix}"
    assert unit.short_name == f"<b>Power generator</b> {suffix}"
