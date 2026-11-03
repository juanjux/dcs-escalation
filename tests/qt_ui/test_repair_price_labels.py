"""Repair buttons replace, rather than duplicate, the row's price label."""

import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from qt_ui.windows.groundobject import buildingcard, unitcard


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("building", [True, False])
@pytest.mark.parametrize(
    "alive, turns, allowed, button_expected",
    [
        (False, None, True, True),
        (True, None, True, False),
        (False, 2, True, False),
        (False, None, False, False),
    ],
)
def test_price_is_shown_once(
    app: Any,
    monkeypatch: Any,
    building: bool,
    alive: bool,
    turns: int | None,
    allowed: bool,
    button_expected: bool,
) -> None:
    unit: Any = SimpleNamespace(
        name="Test unit",
        id=1,
        alive=alive,
        health_fraction=1.0 if alive else 0.0,
        repair_turns_remaining=turns,
        repairable=True,
        position=None,
    )
    site: Any = SimpleNamespace(category="oil", repair_cost=lambda: 40, groups=[])
    module = buildingcard if building else unitcard
    monkeypatch.setattr(
        module, "CoordinateLabel", lambda *args, **kwargs: QLabel("Coordinates")
    )
    repair: Any = (lambda *args: None) if allowed else None
    if building:
        monkeypatch.setattr(buildingcard, "buildings_of", lambda _: [])
        monkeypatch.setattr(buildingcard, "thumbnail", lambda _: None)
        card = buildingcard.BuildingCard(site, object(), repair)
        row = card._row(unit)
    else:
        monkeypatch.setattr(unitcard, "type_name", lambda _: "Test unit")
        monkeypatch.setattr(unitcard, "describe_unit", lambda _: "")
        monkeypatch.setattr(unitcard, "unit_note", lambda _: "")
        monkeypatch.setattr(unitcard, "price_of", lambda _: 40)
        units = unitcard.UnitCard(site, object(), repair)
        row = units._unit_row(unit, 0)
    prices = [
        label.text() for label in row.findChildren(QLabel) if "$40M" in label.text()
    ]
    assert len(prices) == 1
    assert bool(row.findChildren(QPushButton)) == button_expected
    row.close()


def test_pending_building_has_a_cancel_button_with_its_receipt(
    app: Any, monkeypatch: Any
) -> None:
    building: Any = SimpleNamespace(
        id=1,
        alive=False,
        repair_turns_remaining=3,
        repair_cost_paid=12.5,
    )
    site: Any = SimpleNamespace(statics=[building], repair_cost=lambda: 99)
    monkeypatch.setattr(buildingcard, "buildings_of", lambda _: [])
    cancelled: list[Any] = []
    card = buildingcard.BuildingCard(site, object(), None, cancelled.append)
    cancel_button = card._repair_button(building)
    assert cancel_button is not None
    assert any(
        "+$12.5M" in label.text() for label in cancel_button.findChildren(QLabel)
    )
    assert isinstance(cancel_button, QPushButton)
    cancel_button.click()
    assert cancelled == [building]
    card.cancel_repair = None
    assert card._repair_button(building) is None


@pytest.mark.parametrize("receipt,expected", [(None, 8), (12.5, 12.5)])
def test_unit_card_can_cancel_old_and_new_jammer_repairs(
    app: Any, receipt: float | None, expected: float
) -> None:
    unit: Any = SimpleNamespace(
        id=1610,
        alive=False,
        repairable=True,
        repair_turns_remaining=2,
        repair_cost_paid=receipt,
        unit_type=SimpleNamespace(price=8),
    )
    site: Any = SimpleNamespace(units=[unit], groups=[])
    cancelled: list[Any] = []
    card = unitcard.UnitCard(site, object(), None, cancelled.append)
    cancel_button = card._repair_button(unit)
    assert isinstance(cancel_button, QPushButton)
    assert any(
        f"+${expected:g}M" in label.text()
        for label in cancel_button.findChildren(QLabel)
    )
    cancel_button.click()
    assert cancelled == [unit]
    card.cancel_repair = None
    assert card._repair_button(unit) is None
