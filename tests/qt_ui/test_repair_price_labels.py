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
