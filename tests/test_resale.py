"""Resale policy and exact cancellation of pending aircraft transactions."""

import pickle
from types import SimpleNamespace
from typing import Any

import pytest

from game.aircraftmaintenance import sale_value
from game.purchaseadapter import AircraftPurchaseAdapter
from game.resale import ground_object_sale_value, resale_value
from game.settings import Settings
from game.settings.optiondescription import SETTING_DESCRIPTION_KEY
from game.squadrons.squadron import Squadron
from game.theater import Player
from game.theater.controlpoint import ControlPoint


@pytest.fixture(params=[Player.BLUE, Player.RED])
def trade(request: pytest.FixtureRequest) -> Any:
    settings = Settings()
    coalition: Any = SimpleNamespace(budget=100.0)
    coalition.adjust_budget = lambda value: setattr(
        coalition, "budget", coalition.budget + value
    )
    game = SimpleNamespace(
        settings=settings, high_command_for=lambda side: SimpleNamespace(loans=[])
    )
    coalition.game = game
    cp: Any = SimpleNamespace(coalition=coalition)
    squadron = SimpleNamespace(
        aircraft=SimpleNamespace(price=3),
        pending_deliveries=0,
        untasked_aircraft=4,
        coalition=coalition,
        player=request.param,
    )
    return SimpleNamespace(
        settings=settings,
        game=game,
        coalition=coalition,
        squadron=squadron,
        adapter=AircraftPurchaseAdapter(cp),
    )


def test_defaults_and_settings_dependencies() -> None:
    settings = Settings()
    assert settings.resale_depreciation_enabled
    assert settings.resale_value_percent == 85
    description = Settings.__dataclass_fields__["resale_value_percent"].metadata[
        SETTING_DESCRIPTION_KEY
    ]
    assert description.enabled_when(settings)
    settings.resale_depreciation_enabled = False
    assert not description.enabled_when(settings)
    assert resale_value(settings, 3) == 3
    restored = pickle.loads(pickle.dumps(settings))
    assert not restored.resale_depreciation_enabled
    assert restored.resale_value_percent == 85


@pytest.mark.parametrize("percent", [0, 40, 85, 100])
def test_configurable_sale_and_exact_undo(trade: Any, percent: int) -> None:
    trade.settings.resale_value_percent = percent
    trade.adapter.sell(trade.squadron, 2)
    assert trade.coalition.budget == pytest.approx(100 + 6 * percent / 100)
    assert trade.squadron.untasked_aircraft == 2
    trade.settings.resale_value_percent = 17
    trade.settings.resale_depreciation_enabled = False
    trade.adapter.buy(trade.squadron, 2)
    assert trade.coalition.budget == pytest.approx(100)
    assert trade.squadron.untasked_aircraft == 4
    assert trade.squadron.pending_deliveries == 0
    assert trade.squadron.pending_sale_values == []


def test_cancel_purchase_refunds_full_price(trade: Any) -> None:
    trade.squadron.pending_deliveries = 2
    trade.coalition.budget = 94
    trade.adapter.sell(trade.squadron, 3)
    assert trade.coalition.budget == pytest.approx(102.55)
    assert trade.squadron.pending_deliveries == -1
    assert trade.squadron.untasked_aircraft == 3


def test_automatic_order_refund_uses_receipts(trade: Any) -> None:
    trade.adapter.sell(trade.squadron, 1)
    trade.settings.resale_value_percent = 50
    trade.adapter.sell(trade.squadron, 1)
    Squadron.refund_orders(trade.squadron, -1)
    assert trade.coalition.budget == pytest.approx(102.55)
    Squadron.refund_orders(trade.squadron)
    assert trade.coalition.budget == pytest.approx(100)
    assert trade.squadron.pending_sale_values == []


def test_legacy_pending_sale_cancels_at_original_full_price(trade: Any) -> None:
    trade.squadron.pending_deliveries = -1
    trade.coalition.budget = 103
    trade.adapter.buy(trade.squadron, 1)
    assert trade.coalition.budget == 100


def test_receipts_survive_save_and_delivery_clears_them(trade: Any) -> None:
    trade.adapter.sell(trade.squadron, 2)
    saved = Squadron.__new__(Squadron)
    saved.__setstate__(
        {
            "pending_sale_values": trade.squadron.pending_sale_values,
            "pending_deliveries": -2,
        }
    )
    restored = pickle.loads(pickle.dumps(saved))
    assert restored.pending_sale_values == [2.55, 2.55]
    trade.squadron.owned_aircraft = 4
    trade.squadron.purchased_aircraft = 0
    trade.squadron.cancel_overflow_orders = lambda: None
    Squadron.deliver_orders(trade.squadron)
    assert trade.squadron.owned_aircraft == 2
    assert trade.squadron.pending_deliveries == 0
    assert trade.squadron.pending_sale_values == []


def test_legacy_settings_use_default_policy() -> None:
    assert resale_value(SimpleNamespace(), 3) == pytest.approx(2.55)  # type: ignore[arg-type]


def test_group_sales_refund_pending_repairs_in_full(trade: Any) -> None:
    site: Any = SimpleNamespace(
        sellable=True,
        value=3,
        units=[
            SimpleNamespace(alive=True, repair_turns_remaining=None),
            SimpleNamespace(alive=False, repair_turns_remaining=None),
            SimpleNamespace(
                alive=False,
                repair_turns_remaining=2,
                unit_type=SimpleNamespace(price=7),
            ),
        ],
    )
    assert ground_object_sale_value(trade.game, site) == pytest.approx(9.55)
    trade.settings.resale_depreciation_enabled = False
    assert ground_object_sale_value(trade.game, site) == 10
    site.sellable = False
    assert ground_object_sale_value(trade.game, site) == 0


def test_damaged_aircraft_apply_both_valuations(trade: Any) -> None:
    assert sale_value(trade.game, trade.squadron) == pytest.approx(1.275)
    trade.settings.resale_depreciation_enabled = False
    assert sale_value(trade.game, trade.squadron) == 1.5


def test_captured_equipment_sales_follow_the_same_policy(trade: Any) -> None:
    messages: list[Any] = []
    credits: list[tuple[float, Player]] = []
    trade.game.message = lambda *args: messages.append(args)
    trade.game.adjust_budget = lambda value, player: credits.append((value, player))
    base: Any = SimpleNamespace(
        name="Captured base",
        captured=Player.RED,
        base=SimpleNamespace(total_armor_value=3, armor={"vehicle": 1}),
    )
    ControlPoint.capture_equipment(base, trade.game)
    ControlPoint.capture_aircraft(base, trade.game, trade.squadron.aircraft, 2)
    assert credits == [(2.55, Player.BLUE), (5.1, Player.BLUE)]
    assert not base.base.armor
    assert len(messages) == 2
