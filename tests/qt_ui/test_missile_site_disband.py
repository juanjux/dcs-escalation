"""Missile sites can be sold without enabling mid-campaign purchases."""

from copy import copy
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QPushButton

from game.missiletargets import MissileTarget, stored
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    CoastalSiteGroundObject,
)
from qt_ui.windows.groundobject import QGroundObjectMenu as menu
from qt_ui.windows.groundobject.header import LocationHeader
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_missile_targets import missiles  # noqa: F401


@pytest.fixture
def location(missiles: Any, controls: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w = missiles
    for cp in w.game.theater.controlpoints:
        cp.coalition.game = w.game
        cp.coalition.budget = 100
    w.game.blue = w.a.coalition
    w.game.red = w.enemy.coalition
    w.game.theater.iads_network = SimpleNamespace(update_tgo=Mock())
    w.game.ato_for = lambda **kwargs: SimpleNamespace(packages=[])
    support = copy(next(unit for unit in w.source.units if unit.id == 5))
    support.id += 1000
    support.ground_object = w.site
    w.site.groups[0].units.append(support)
    controls.model.is_ownfor = True
    monkeypatch.setitem(menu.EVENT_ICONS, "capture", QIcon())
    monkeypatch.setattr(menu.QGroundObjectMenu, "_build", lambda window: None)
    window = menu.QGroundObjectMenu(None, w.site, w.a, controls.model)
    window._update_total_value()
    window.column.addWidget(window._footer())
    yield SimpleNamespace(world=w, controls=controls, window=window)
    window.close()


@pytest.mark.parametrize("turn", [0, 1, 15])
def test_missile_sites_are_sellable_without_changing_purchase_or_repair_rules(
    location: Any, turn: int
) -> None:
    p = location
    p.world.game.turn = turn
    assert p.world.site.sellable and p.window._can_sell
    assert p.world.site.purchasable == (turn == 0)
    assert p.world.site.repairable == (turn == 0)
    assert p.window._can_trade == (turn == 0)


def test_mid_campaign_footer_offers_disband_but_not_buy(location: Any) -> None:
    p = location
    assert p.world.game.turn > 0
    assert p.window.total_value == p.world.site.value > 0
    assert any(label.text() == "Disband" for label in p.window.findChildren(QLabel))
    assert not any(
        button.text() == "Buy / replace…"
        for button in p.window.findChildren(QPushButton)
    )
    price = p.world.site.value
    assert price > 0 and p.window.total_value == price
    assert f"value ${price}M" in LocationHeader._figures(p.world.site, p.world.a)


def test_disband_refunds_survivors_and_pending_repairs_then_clears_order(
    location: Any,
) -> None:
    p = location
    w = p.world
    alive = next(unit for unit in w.site.units if unit.unit_type.price > 0)
    dead = copy(alive)
    dead.id += 1000
    dead.alive = False
    dead.repair_turns_remaining = None
    repairing = copy(dead)
    repairing.id += 1000
    repairing.repair_turns_remaining = 2
    w.site.groups[0].units.extend([dead, repairing])
    w.site.missile_target = MissileTarget(Player.BLUE, 10000, 20000, "GPS")
    w.site._threat_poly = object()
    price = alive.unit_type.price
    p.window._sell_all()
    assert w.game.blue.budget == 100 + 2 * price
    assert w.game.red.budget == 100
    assert list(w.site.units) == [] and w.site.is_dead
    assert stored(w.site) is None
    assert vars(w.site)["_threat_poly"] is None
    assert len(p.controls.sent) == 1
    assert w.site in p.controls.sent[0].updated_tgos
    w.game.theater.iads_network.update_tgo.assert_called_once_with(
        w.site, p.controls.sent[0]
    )
    p.window._sell_all()
    assert w.game.blue.budget == 100 + 2 * price


@pytest.mark.parametrize(
    "owner,cheat,allowed",
    [
        (Player.BLUE, False, True),
        (Player.RED, False, False),
        (Player.RED, True, True),
        (Player.NEUTRAL, False, False),
        (Player.NEUTRAL, True, False),
    ],
)
def test_disband_respects_ownership_and_enemy_trade_cheat(
    location: Any, owner: Player, cheat: bool, allowed: bool
) -> None:
    p = location
    w = p.world
    w.a.coalition.player = owner
    w.game.settings.enable_enemy_buy_sell = cheat
    assert p.window._can_sell is allowed
    units = list(w.site.units)
    p.window._sell_all()
    assert (list(w.site.units) == []) is allowed
    if not allowed:
        assert list(w.site.units) == units
        assert w.a.coalition.budget == 100 and not p.controls.sent


def test_stale_campaign_cannot_sell_the_previous_campaign_site(location: Any) -> None:
    p = location
    p.controls.model.game = None
    p.window._sell_all()
    assert list(p.world.site.units) and p.world.game.blue.budget == 100
    assert not p.controls.sent


def test_zero_price_missile_launcher_can_still_be_disbanded(location: Any) -> None:
    p = location
    w = p.world
    w.site.groups[0].units = [
        unit for unit in w.site.units if unit.unit_type.price == 0
    ]
    assert w.site.unit_count > 0
    p.window._update_total_value()
    assert p.window.total_value == 0
    footer = p.window._footer()
    disband_label = next(
        label for label in footer.findChildren(QLabel) if label.text() == "Disband"
    )
    disband_label.parentWidget().click()
    assert not list(w.site.units) and w.game.blue.budget == 100


def test_other_group_types_keep_existing_trade_rules(location: Any) -> None:
    w = location.world
    coastal = CoastalSiteGroundObject(
        "COAST", PresetLocation("COAST", w.a.position), w.a
    )
    building = BuildingGroundObject(
        "FACTORY", "factory", PresetLocation("FACTORY", w.a.position), w.a, None
    )
    for turn in (0, 5):
        w.game.turn = turn
        for site in (w.source, w.ship, coastal, building):
            assert site.sellable == site.purchasable
