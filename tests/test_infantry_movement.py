"""Infantry and MANPADS do not need vehicle mobility data or tractors."""

from __future__ import annotations

from dataclasses import replace
import pickle
from typing import Any

import pytest

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.base import dispatch_base_movement
from game.groundmovement.dispatch import advance_armor, dispatch_armor
from game.groundmovement.mobility import GroundMobility, MobilityMode, movement_mobility
from game.groundmovement.orders import GroundPosition, plan_transport
from game.groundmovement.planning import armor_movement_options
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from qt_ui.windows.groundobject.movementdialog import ArmorMovementDialog
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_base_reserve_groups import stock  # noqa: F401


@pytest.mark.parametrize(
    "variant",
    [
        "Infantry M4",
        "MANPADS Stinger",
        'MANPADS SA-18 Igla "Grouse"',
        "[CH] FIM-92K Stinger Soldier",
        "[CH] M120 120 mm Mortar",
    ],
)
def test_personnel_can_move_with_any_vehicle_without_tractors(variant: str) -> None:
    infantry = GroundUnitType.named(variant)
    vehicle = GroundUnitType.named("[CH] M10 LT")
    assert not vehicle.ground_mobility.can_tow
    before = infantry.ground_mobility
    manifest = plan_transport({1: infantry, 2: infantry, 3: vehicle}, [1, 2, 3])
    assert manifest.unit_ids == (1, 2, 3) and manifest.towing == ()
    assert infantry.ground_mobility == before
    assert not movement_mobility(infantry).can_tow


@pytest.mark.parametrize("mode", list(MobilityMode))
def test_personnel_mobility_override_is_not_a_vehicle_or_tractor_override(
    mode: MobilityMode,
) -> None:
    infantry = replace(
        GroundUnitType.named("Infantry M4"),
        ground_mobility=GroundMobility(mode, mode is MobilityMode.SELF_PROPELLED),
    )
    assert plan_transport({1: infantry}, [1]).unit_ids == (1,)
    assert not movement_mobility(infantry).can_tow
    gun = GroundUnitType.named("AAA ZU-23 Emplacement")
    with pytest.raises(ValueError, match="only 0"):
        plan_transport({1: infantry, 2: gun}, [1, 2])


def add_infantry(world: Any) -> None:
    unit = next(unit for unit in world.source.units if unit.id == 1)
    infantry = GroundUnitType.named("MANPADS Stinger")
    unit.type = infantry.dcs_unit_type
    unit.ground_unit_variant = infantry.variant_id
    world.units[1] = infantry


def test_options_dialog_api_and_dispatch_allow_manpads(
    world: Any, controls: Any
) -> None:
    add_infantry(world)
    options = armor_movement_options(world.game, world.source.id, Player.BLUE)
    unit = next(unit for unit in options.units if unit.id == 1)
    assert unit.selectable and not unit.can_tow
    assert all("MANPADS Stinger" not in warning for warning in options.warnings)
    assert options.towed_pieces == 3 and options.available_tractors == 2
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    try:
        assert dialog.units[1].isEnabled()
        response = controls.request("GET", controls.url + "/options")
        assert response.status_code == 200
        assert next(u for u in response.json()["units"] if u["id"] == 1)["selectable"]
        body = {**controls.body, "unit_ids": [1, 7]}
        preview = controls.request("POST", controls.url + "/preview", json=body)
        assert preview.status_code == 200
        assert preview.json()["unit_ids"] == [1, 7]
        assert preview.json()["towing"] == []
        response = controls.request(
            "POST",
            controls.url,
            json={**body, "preview_token": preview.json()["preview_token"]},
        )
        assert response.status_code == 200
        assert response.json()["original_units"] == 2
    finally:
        dialog.close()
        dialog.deleteLater()


def test_dispatch_delivers_infantry_without_debiting_tractors(world: Any) -> None:
    prepare(world)
    add_infantry(world)
    transit = dispatch_armor(
        world.game,
        world.source.id,
        Player.BLUE,
        (1, 7),
        world.destination,
        GameUpdateEvents(),
    )
    assert world.game.ground_movements.reserved_unit_ids == {1, 7}
    world.game.ground_movements = pickle.loads(
        pickle.dumps(world.game.ground_movements)
    )
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert world.game.ground_movements.transits[transit.order_id].finished
    assert world.b.base.armor[world.units[1]] == 1
    assert world.b.base.armor[world.units[7]] == 1
    assert {u.id for u in world.source.units} >= {5, 6}


def test_base_deployment_includes_infantry_without_adding_tractors(stock: Any) -> None:
    infantry = GroundUnitType.named("MANPADS Stinger")
    stock.a.base.commission_units({infantry: 2})
    transit = dispatch_base_movement(
        stock.game,
        stock.a.id,
        Player.BLUE,
        {infantry: 2, stock.units[7]: 1},
        GroundPosition(80, 10),
        GameUpdateEvents(),
    )
    manifest = stock.game.ground_movements.orders[transit.order_id].manifest
    assert len(manifest.unit_ids) == 3 and not manifest.towing
    assert stock.a.base.armor.get(infantry, 0) == 0
    assert stock.a.base.armor[stock.units[5]] == 3


def test_unknown_or_fixed_vehicles_still_cannot_move() -> None:
    for mode in (MobilityMode.UNKNOWN, MobilityMode.FIXED):
        vehicle = replace(
            GroundUnitType.named("M1A2 Abrams"), ground_mobility=GroundMobility(mode)
        )
        assert movement_mobility(vehicle).mode is mode
        with pytest.raises(ValueError, match="Mobility"):
            plan_transport({1: vehicle}, [1])
