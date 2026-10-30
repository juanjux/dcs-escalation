"""Missile sites remain purchasable after being disbanded during a campaign."""

from copy import copy
from itertools import count
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from dcs.mapping import Point
import pytest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QPushButton

from game.missiletargets import MissileTarget, stored
from game.armedforces.forcegroup import ForceGroup
from game.data.groups import GroupTask
from game.layout.layout import LayoutUnit, TgoLayout, TgoLayoutGroup, TgoLayoutUnitGroup
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    CoastalSiteGroundObject,
)
from game.utils import Heading
from qt_ui.windows.groundobject import QGroundObjectMenu as menu
from qt_ui.windows.groundobject.header import LocationHeader
from qt_ui.windows.groundobject.QGroundObjectBuyMenu import QGroundObjectBuyMenu
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
def test_missile_sites_are_tradeable_and_rebuildable_throughout_campaign(
    location: Any, turn: int
) -> None:
    p = location
    p.world.game.turn = turn
    assert p.world.site.sellable and p.window._can_sell
    assert p.world.site.purchasable and p.world.site.repairable
    assert p.window._can_trade


def test_mid_campaign_footer_offers_disband_and_buy(location: Any) -> None:
    p = location
    assert p.world.game.turn > 0
    assert p.window.total_value == pytest.approx(p.world.site.value * 0.85)
    assert p.window.total_value > 0
    assert any(label.text() == "Disband" for label in p.window.findChildren(QLabel))
    assert any(
        button.text() == "Buy / replace…"
        for button in p.window.findChildren(QPushButton)
    )
    price = p.world.site.value
    assert price > 0 and p.window.total_value == pytest.approx(price * 0.85)
    assert f"value ${price}M" in LocationHeader._figures(p.world.site, p.world.a)


@pytest.mark.parametrize("enabled,percent", [(True, 85), (True, 40), (False, 85)])
def test_disband_uses_configured_fractional_proceeds(
    location: Any, enabled: bool, percent: int
) -> None:
    p = location
    w = p.world
    w.game.settings.resale_depreciation_enabled = enabled
    w.game.settings.resale_value_percent = percent
    p.window._update_total_value()
    expected = w.site.value * (percent / 100 if enabled else 1)
    assert p.window.total_value == pytest.approx(expected)
    p.window._sell_all()
    assert w.game.blue.budget == pytest.approx(100 + expected)


@pytest.mark.parametrize("repair_turns", [0, 2])
@pytest.mark.parametrize("enabled,percent", [(True, 85), (True, 40), (False, 85)])
def test_disbanded_site_can_be_bought_again_with_normal_price_and_delay(
    location: Any, repair_turns: int, enabled: bool, percent: int
) -> None:
    p = location
    w = p.world
    original = list(w.site.units)
    launch_type, support_type = [unit.unit_type for unit in original]
    terrain = w.game.theater.terrain
    slots = [
        TgoLayoutUnitGroup(
            name=unit_type.variant_id,
            layout_units=[
                LayoutUnit(unit_type.variant_id, Point(i * 20, 0, terrain), 0)
            ],
            unit_types=[unit_type.dcs_unit_type],
            unit_count=[1],
        )
        for i, unit_type in enumerate((launch_type, support_type))
    ]
    layout = TgoLayout("Missile")
    layout.groups = [TgoLayoutGroup("Missile", 0, slots)]
    force = ForceGroup(
        "Missile", [launch_type, support_type], [], [GroupTask.MISSILE], [layout]
    )
    w.site.coalition.faction = SimpleNamespace(name="Test faction")
    w.site.coalition.armed_forces = SimpleNamespace(
        groups_for_tasks=lambda tasks: [force] if tasks == [GroupTask.MISSILE] else []
    )
    w.game.theater.heading_to_conflict_from = lambda position: Heading.from_degrees(90)
    group_ids, unit_ids = count(2000), count(3000)
    w.game.next_group_id = lambda: next(group_ids)
    w.game.next_unit_id = lambda: next(unit_ids)
    w.game.settings.ground_object_repair_turns = repair_turns
    w.game.settings.resale_depreciation_enabled = enabled
    w.game.settings.resale_value_percent = percent
    p.window._update_total_value()
    expected = w.site.value * (percent / 100 if enabled else 1)
    quote = QGroundObjectBuyMenu(p.window, w.site, w.game, p.window.total_value)
    assert quote.refund == pytest.approx(expected)
    assert f"${expected:g}M" in quote._what_is_there()
    assert quote.figures["Refund"].text() == f"+${expected:g}M"
    # A fractional balance must not be truncated before the affordability check.
    w.site.coalition.budget = quote.selection.price - quote.refund
    quote._recount()
    assert quote.buy_button.isEnabled()
    assert quote.figures["Budget after"].text() == "$0M"
    w.site.coalition.budget -= 0.01
    quote._recount()
    assert not quote.buy_button.isEnabled()
    w.site.coalition.budget = 100
    quote.close()
    w.site.missile_target = MissileTarget(Player.BLUE, 10000, 20000, "GPS")
    p.window._sell_all()
    assert not list(w.site.units) and stored(w.site) is None
    assert p.window._can_trade and w.site.repairable
    p.window._update_total_value()
    assert p.window.total_value == 0
    footer = p.window._footer()
    assert any(b.text() == "Buy / replace…" for b in footer.findChildren(QPushButton))

    dialog = QGroundObjectBuyMenu(p.window, w.site, w.game, p.window.total_value)
    assert dialog.here is None and dialog.offers == [force]
    assert dialog.buy_button.isEnabled()
    budget = w.site.coalition.budget
    price = dialog.selection.price
    assert price > 0
    dialog._buy()
    assert w.site.coalition.budget == budget - price
    assert len(list(w.site.units)) == len(original)
    assert {u.type for u in w.site.units} == {u.type for u in original}
    assert all(u.id >= 3000 for u in w.site.units)
    assert all(u.alive == (repair_turns == 0) for u in w.site.units)
    assert all(u.repair_turns_remaining == (repair_turns or None) for u in w.site.units)
    assert stored(w.site) is None
    p.window._update_game()
    assert w.site in p.controls.sent[-1].updated_tgos
    dialog.close()


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
    assert w.game.blue.budget == pytest.approx(100 + 1.85 * price)
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
    assert w.game.blue.budget == pytest.approx(100 + 1.85 * price)


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
    assert p.window._can_trade is allowed
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
