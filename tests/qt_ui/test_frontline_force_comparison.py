"""Base strategy rows distinguish deployable pools from reserve inventories."""

import os
import random
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import GroundPlanner
from game.theater.base import Base
from game.theater.player import Player
from qt_ui.windows.basemenu.ground_forces.QGroundForcesStrategy import (
    QGroundForcesStrategy,
)


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


def _unit(unit_class: UnitClass = UnitClass.TANK) -> Any:
    unit = MagicMock(spec=GroundUnitType)
    unit.unit_class = unit_class
    return unit


def _base(name: str, owner: Player, count: int, limit: int) -> Any:
    base = Base()
    base.commission_units({_unit(): count})
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        captured=owner,
        base=base,
        frontline_unit_count_limit=limit,
        connected_points=[],
        stances={},
    )


def _row(own: Any, enemy: Any) -> QGroundForcesStrategy:
    own.connected_points = [enemy]
    enemy.connected_points = [own]
    game: Any = SimpleNamespace(settings=SimpleNamespace(enable_frontline_cheats=False))
    return QGroundForcesStrategy(own, game)


def _labels(widget: QGroundForcesStrategy) -> dict[str, QLabel]:
    return {label.text(): label for label in widget.findChildren(QLabel)}


@pytest.mark.parametrize(
    "own_count,enemy_count,own_limit,enemy_limit,odds,reserve",
    [
        (21, 49, 15, 15, "15 vs 15", "Reserve: 6 vs 34"),
        (21, 49, 10, 20, "10 vs 20", "Reserve: 11 vs 29"),
        (7, 3, 15, 15, "7 vs 3", "Reserve: 0 vs 0"),
        (0, 49, 15, 15, "0 vs 15", "Reserve: 0 vs 34"),
        (21, 49, 0, 0, "0 vs 0", "Reserve: 21 vs 49"),
    ],
)
def test_compares_deployable_pools_and_separate_reserves(
    app: Any,
    own_count: int,
    enemy_count: int,
    own_limit: int,
    enemy_limit: int,
    odds: str,
    reserve: str,
) -> None:
    own = _base("Own Base", Player.BLUE, own_count, own_limit)
    enemy = _base("Enemy Base", Player.RED, enemy_count, enemy_limit)
    widget = _row(own, enemy)
    labels = _labels(widget)

    assert odds in labels
    assert reserve in labels
    assert "deployable" in labels
    assert "units" not in labels
    tooltip = labels[odds].toolTip()
    assert f"{own_count} total (limit {own_limit})" in tooltip
    assert f"{enemy_count} total (limit {enemy_limit})" in tooltip
    assert "Own Base:" in tooltip and "Enemy Base:" in tooltip
    assert "shared across" in tooltip.replace("<br>", " ")
    widget.close()


def test_counts_match_planner_rounding_and_unsupported_types(app: Any) -> None:
    own = _base("Own Base", Player.BLUE, 21, 15)
    enemy = _base("Enemy Base", Player.RED, 49, 15)
    # Proportional rounding can leave a place unused despite enough inventory.
    enemy.base.armor = {_unit(): 14, _unit(): 14, _unit(): 21}
    own.base.armor = {_unit(): 14, _unit(UnitClass.INFANTRY): 7}
    widget = _row(own, enemy)
    rng = random.getstate()
    try:
        planned = []
        for point in (own, enemy):
            planner = GroundPlanner(point, widget.game)
            planner.plan_groundwar()
            planned.append(
                sum(g.size for groups in planner.units_per_cp.values() for g in groups)
            )
    finally:
        random.setstate(rng)

    assert planned == [10, 14]
    labels = _labels(widget)
    assert f"{planned[0]} vs {planned[1]}" in labels
    assert "Reserve: 11 vs 35" in labels
    widget.close()


def test_shared_fronts_are_explicit_and_rendering_does_not_replan(app: Any) -> None:
    own = _base("Own Base", Player.BLUE, 21, 15)
    enemy = _base("Enemy Base", Player.RED, 49, 15)
    widget = _row(own, enemy)
    enemy.connected_points.append(_base("Other Base", Player.BLUE, 10, 15))
    state = random.getstate()
    layout = widget._row(enemy)
    labels = [
        item.widget()
        for i in range(layout.count())
        if (item := layout.itemAt(i)) is not None
    ]
    assert any(
        isinstance(label, QLabel)
        and label.text() == "Deployable pools shared across fronts"
        for label in labels
    )
    assert random.getstate() == state
    assert own.base.total_armor == 21 and enemy.base.total_armor == 49
    widget.close()


def test_comparison_uses_current_inventory_not_a_cached_plan(app: Any) -> None:
    own = _base("Own Base", Player.BLUE, 21, 15)
    enemy = _base("Enemy Base", Player.RED, 49, 15)
    widget = _row(own, enemy)
    own.base.armor = {_unit(): 4}
    updated = QGroundForcesStrategy(own, widget.game)
    labels = _labels(updated)
    assert "4 vs 15" in labels
    assert "Reserve: 0 vs 34" in labels
    widget.close()
    updated.close()
