"""Ground movement reservations, mobility and saved dependency settings."""

from __future__ import annotations

import math
import pickle
from typing import Any
from uuid import uuid4

import pytest

from game import Game
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.mobility import GroundMobility, MobilityMode
from game.groundmovement.orders import (
    DestinationKind,
    GroundMovementOrders,
    GroundMovementOrder,
    GroundPosition,
    MovementDestination,
    MovementSource,
    TransportManifest,
    plan_transport,
)
from game.groundmovement import settings as movement
from game.plugins import LuaPluginManager
from game.settings import Settings
from game.theater import Player


@pytest.fixture
def settings() -> Settings:
    result = Settings()
    movement.set_enabled(result, True)
    return result


@pytest.fixture
def units() -> dict[int, GroundUnitType]:
    gun = GroundUnitType.named("AAA ZU-23 Emplacement")
    truck = GroundUnitType.named("Truck Ural-375")
    return {
        1: gun,
        2: gun,
        3: gun,
        4: gun,
        5: truck,
        6: truck,
        7: GroundUnitType.named("M1A2 Abrams"),
    }


def _plan(
    orders: GroundMovementOrders,
    settings: Settings,
    units: dict[int, GroundUnitType],
    selected: list[int],
    **overrides: Any,
) -> GroundMovementOrder:
    args: dict[str, Any] = dict(
        source_id=uuid4(),
        source_kind=MovementSource.ARMOR,
        owner=Player.BLUE,
        origin=GroundPosition(10, 20),
        destination=MovementDestination(
            DestinationKind.POSITION, GroundPosition(1000, 2000)
        ),
        units=units,
        selected=selected,
        turn=5,
    )
    args.update(overrides)
    return orders.plan(settings, **args)


def test_old_settings_default_off_and_budget_uses_statute_miles() -> None:
    settings = Settings()
    assert not movement.enabled(settings)
    assert movement.distance_per_turn(settings, on_road=True) == pytest.approx(
        193121.28
    )
    assert movement.distance_per_turn(settings, on_road=False) == pytest.approx(
        96560.64
    )


def test_enable_requires_explicit_dependency_and_disable_preserves_options() -> None:
    settings = Settings()
    settings.motorpool_enabled = False
    with pytest.raises(ValueError, match="Motor Pool"):
        movement.set_enabled(settings, True)
    with pytest.raises(ValueError, match="Motor Pool"):
        settings.set_plugin_option("groundmovement", True)
    assert vars(settings)["motorpool_enabled"] is False
    assert not movement.enabled(settings)
    movement.set_enabled(settings, True, enable_motorpool=True)
    settings.set_plugin_option("groundmovement.roadMilesPerTurn", 80)
    assert vars(settings)["motorpool_enabled"] is True
    assert movement.enabled(settings)
    movement.disable_motorpool(settings)
    assert vars(settings)["motorpool_enabled"] is False
    assert not movement.requested(settings)
    assert movement.distance_per_turn(settings, on_road=True) == pytest.approx(
        80 * 1609.344
    )


def test_invalid_imported_dependency_disables_plugin_without_enabling_motorpool() -> (
    None
):
    settings = Settings()
    settings.motorpool_enabled = False
    settings.plugins["groundmovement"] = True
    LuaPluginManager.load_settings(settings)
    assert not settings.motorpool_enabled and not movement.requested(settings)


@pytest.mark.parametrize("value", [0, -1, 1001, True, "120", math.inf, math.nan])
def test_invalid_saved_distance_is_rejected(settings: Settings, value: Any) -> None:
    settings.set_plugin_option("groundmovement.roadMilesPerTurn", value)
    with pytest.raises(ValueError, match="distance"):
        movement.distance_per_turn(settings, on_road=True)


def test_two_tractors_cannot_move_four_towed_guns(
    units: dict[int, GroundUnitType],
) -> None:
    with pytest.raises(ValueError, match="only 2"):
        plan_transport(units, [1, 2, 3, 4])


def test_partial_selection_adds_only_its_tractors_without_changing_inventory(
    units: dict[int, GroundUnitType],
) -> None:
    before = units.copy()
    manifest = plan_transport(units, [3, 1])
    assert manifest.unit_ids == (1, 3, 5, 6)
    assert manifest.towing == ((1, 5), (3, 6))
    assert set(units) - set(manifest.unit_ids) == {2, 4, 7}
    assert units == before
    assert plan_transport(units, [1, 6]).towing == ((1, 6),)
    assert plan_transport(units, [7]).unit_ids == (7,)


def test_mounted_gun_is_not_a_tractor_and_does_not_need_one() -> None:
    mounted = GroundUnitType.named("ZU-23 on Ural-375")
    assert mounted.ground_mobility.mode is MobilityMode.SELF_PROPELLED
    assert not mounted.ground_mobility.can_tow
    assert plan_transport({1: mounted}, [1]).towing == ()
    with pytest.raises(ValueError, match="only 0"):
        plan_transport(
            {1: mounted, 2: GroundUnitType.named("AAA ZU-23 Emplacement")}, [2]
        )


@pytest.mark.parametrize("selected", [[], [1, 1], [999], [True]])
def test_invalid_selection_is_rejected(
    units: dict[int, GroundUnitType], selected: list[int]
) -> None:
    with pytest.raises(ValueError):
        plan_transport(units, selected)


def test_unreviewed_logistics_is_not_implicitly_a_tractor() -> None:
    from dataclasses import replace

    unknown = replace(
        GroundUnitType.named("Truck Ural-375"), ground_mobility=GroundMobility()
    )
    with pytest.raises(ValueError, match="Mobility"):
        plan_transport({1: unknown}, [1])
    assert not unknown.ground_mobility.can_tow


@pytest.mark.parametrize(
    "data", [[], {"can_tow": 1}, {"can_tow": True}, {"mode": "flying"}, {"typo": True}]
)
def test_invalid_mobility_data_is_rejected(data: Any) -> None:
    with pytest.raises(ValueError):
        GroundMobility.from_data(data)


def test_old_ground_unit_save_refreshes_mobility_from_current_data() -> None:
    truck = GroundUnitType.named("Truck Ural-375")
    state = dict(truck.__dict__)
    state.pop("ground_mobility")
    restored = GroundUnitType.__new__(GroundUnitType)
    restored.__setstate__(state)
    assert restored.ground_mobility.can_tow


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_reservations_survive_pickle_and_pause_without_double_booking(
    settings: Settings,
    units: dict[int, GroundUnitType],
    side: Player,
) -> None:
    orders = GroundMovementOrders()
    first = _plan(orders, settings, units, [1], owner=side)
    assert orders.reserved_unit_ids == {1, 5}
    restored = pickle.loads(pickle.dumps(orders))
    movement.set_enabled(settings, False)
    assert restored.orders[first.id].status(settings) == "paused"
    assert restored.reserved_unit_ids == {1, 5}
    with pytest.raises(ValueError, match="plugin"):
        _plan(restored, settings, units, [2])
    movement.set_enabled(settings, True)
    assert restored.orders[first.id].status(settings) == "planned"
    with pytest.raises(ValueError, match="reserved"):
        _plan(restored, settings, units, [1])
    second = _plan(restored, settings, units, [2], owner=side)
    assert second.manifest.towing == ((2, 6),)
    with pytest.raises(ValueError, match="only 0"):
        _plan(restored, settings, units, [3])
    restored.cancel(first.id)
    restored.cancel(first.id)
    assert restored.orders[first.id].status(settings) == "cancelled"
    assert restored.reserved_unit_ids == {2, 6}
    assert _plan(restored, settings, units, [3]).manifest.towing == ((3, 5),)


@pytest.mark.parametrize("kind", [DestinationKind.BASE, DestinationKind.FRONTLINE])
def test_sam_cannot_merge_into_base_or_frontline(
    settings: Settings,
    units: dict[int, GroundUnitType],
    kind: DestinationKind,
) -> None:
    destination = MovementDestination(
        kind,
        GroundPosition(10, 10),
        uuid4(),
        uuid4() if kind is DestinationKind.FRONTLINE else None,
    )
    orders = GroundMovementOrders()
    with pytest.raises(ValueError, match="cannot join"):
        _plan(
            orders,
            settings,
            units,
            [7],
            source_kind=MovementSource.SAM,
            destination=destination,
        )
    assert not orders.orders


def test_partial_sam_is_blocked_pending_operational_validation(
    settings: Settings,
    units: dict[int, GroundUnitType],
) -> None:
    orders = GroundMovementOrders()
    with pytest.raises(ValueError, match="operational-site"):
        _plan(orders, settings, units, [7], source_kind=MovementSource.SAM)
    assert not orders.reserved_unit_ids
    order = _plan(orders, settings, {7: units[7]}, [7], source_kind=MovementSource.SAM)
    assert order.source_kind is MovementSource.SAM


def test_manifest_rejects_shared_or_missing_tractors() -> None:
    with pytest.raises(ValueError):
        TransportManifest((1, 2, 3), ((1, 3), (2, 3)))
    with pytest.raises(ValueError):
        TransportManifest((1,), ((1, 3),))


def test_old_game_save_initializes_separate_empty_order_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Game, "on_load", lambda self: None)
    first, second = Game.__new__(Game), Game.__new__(Game)
    for game in (first, second):
        game.__setstate__({"laser_code_registry": object()})
        assert not game.ground_movements.orders
    assert first.ground_movements is not second.ground_movements


def test_campaign_pickle_preserves_nonempty_movement_orders(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    units: dict[int, GroundUnitType],
) -> None:
    monkeypatch.setattr(Game, "on_load", lambda self: None)
    game = Game.__new__(Game)
    game.__setstate__({"laser_code_registry": object(), "settings": settings})
    order = _plan(game.ground_movements, settings, units, [1])
    movement.set_enabled(settings, False)
    restored = pickle.loads(pickle.dumps(game))
    assert restored.ground_movements.orders[order.id] == order
    assert (
        restored.ground_movements.orders[order.id].status(restored.settings) == "paused"
    )
    assert restored.ground_movements.reserved_unit_ids == {1, 5}
