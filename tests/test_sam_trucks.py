"""Towing trucks supplement a mobile battery under one shared purchase cap."""

from itertools import count
from types import MethodType, SimpleNamespace as NS
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from game.coalition import Coalition
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.mobility import GroundMobility, MobilityMode, movement_mobility
from game.groundmovement.samtrucks import buy_sam_trucks, sam_truck_options
from game.groundmovement.planning import armor_movement_options
from game.server.dependencies import GameContext
from game.server.tgos import router
from game.server.tgos.groundmovement import commands
from game.sim.gameupdateevents import GameUpdateEvents
from game.missiongenerator.tgogenerator import GroundObjectGenerator
from game.unitmap import UnitMap
from dcs import Mission
from game.theater.player import Player
from qt_ui.groundmovement import GroundMovementCommands, MovementCommandError
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_sam_movement import make_site, PATRIOT, KUB, move


@pytest.fixture
def battery(world: Any) -> Any:
    make_site(world, PATRIOT[:2])
    world.game.next_unit_id = count(1000).__next__
    for cp in (world.a, world.enemy):
        cp.coalition.budget = 100.0
        cp.coalition.faction = NS(
            accessible_units=[GroundUnitType.named("Truck Ural-375")]
        )
        cp.coalition.adjust_budget = MethodType(Coalition.adjust_budget, cp.coalition)
    return world


def options(w: Any) -> Any:
    return sam_truck_options(w.game, w.sam.id, w.a.captured)


def buy(w: Any, quantity: Any = 1, name: str = "Truck Ural-375") -> Any:
    return buy_sam_trucks(
        w.game, w.sam.id, w.a.captured, name, quantity, GameUpdateEvents()
    )


def test_cap_is_all_towable_pieces_plus_two_and_inspection_is_read_only(
    battery: Any,
) -> None:
    w = battery
    before = [(g, list(g.units)) for g in w.sam.groups]
    result = options(w)
    assert result.towed_units == 2 and result.truck_limit == result.remaining == 4
    assert result.owned_trucks == 0 and result.reason is None
    assert result.offers[0].unit_type == "Truck Ural-375"
    assert [(g, list(g.units)) for g in w.sam.groups] == before
    assert w.a.coalition.budget == 100


def test_buy_preserves_battery_and_makes_it_movable(battery: Any) -> None:
    w = battery
    old_groups, old_units = list(w.sam.groups), list(w.sam.units)
    assert not armor_movement_options(w.game, w.sam.id, Player.BLUE).enabled
    ids = buy(w, 2)
    assert len(ids) == 2 and len(set(ids)) == 2
    assert list(w.sam.units)[:2] == old_units
    assert w.sam.groups[: len(old_groups)] == old_groups
    assert all(u.ground_object is w.sam for u in w.sam.units)
    assert w.a.coalition.budget == 94
    assert armor_movement_options(w.game, w.sam.id, Player.BLUE).enabled
    assert options(w).owned_trucks == 2 and options(w).remaining == 2
    transit = move(w)
    assert len(w.game.ground_movements.orders[transit.order_id].manifest.towing) == 2


def test_new_trucks_generate_in_mission_and_keep_separate_native_positions(
    battery: Any,
) -> None:
    w = battery
    ids = buy(w, 4)
    mission = Mission(terrain=w.game.theater.terrain)
    w.game.settings.set_plugin_option("skynetiads", False)
    country = mission.country("USA")
    unit_map = UnitMap()
    with patch("game.missiongenerator.tgogenerator.GroundForcePainter"), patch(
        "game.missiongenerator.tgogenerator.shows_on_mfd", return_value=True
    ):
        GroundObjectGenerator(w.sam, country, w.game, mission, unit_map).generate()
    natives = [u for g in country.vehicle_group for u in g.units]
    assert len(natives) == 6
    trucks = [u for u in w.sam.units if u.id in ids]
    assert all(any(u.unit_name == n.name for n in natives) for u in trucks)
    for truck in trucks:
        assert all(
            truck is other or truck.position.distance_to_point(other.position) >= 15
            for other in w.sam.units
        )


def test_multiple_purchases_and_existing_trucks_share_one_cap(battery: Any) -> None:
    w = battery
    buy(w, 3)
    before_units, budget = list(w.sam.units), w.a.coalition.budget
    with pytest.raises(ValueError, match="at most 4"):
        buy(w, 2)
    assert list(w.sam.units) == before_units and w.a.coalition.budget == budget
    buy(w)
    assert options(w).owned_trucks == 4 and options(w).remaining == 0
    with pytest.raises(ValueError, match="limit"):
        buy(w)


def test_different_faction_tractor_models_share_one_cap(battery: Any) -> None:
    w = battery
    second = GroundUnitType.named("Truck Ural-4320T")
    w.a.coalition.faction.accessible_units.append(second)
    buy(w, 2)
    buy(w, 2, second.variant_id)
    assert options(w).owned_trucks == 4 and options(w).remaining == 0
    with pytest.raises(ValueError, match="limit"):
        buy(w, name=second.variant_id)


def test_destroyed_and_repairing_units_still_count_toward_cap(battery: Any) -> None:
    w = battery
    buy(w, 2)
    units = list(w.sam.units)
    units[0].alive = False
    units[2].alive = False
    units[2].repair_turns_remaining = 1
    assert options(w).towed_units == 2
    assert options(w).owned_trucks == 2 and options(w).truck_limit == 4
    buy(w, 2)
    with pytest.raises(ValueError, match="limit"):
        buy(w)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
def test_rejects_invalid_quantities_without_spending(
    battery: Any, quantity: Any
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        buy(battery, quantity)
    assert len(list(battery.sam.units)) == 2
    assert battery.a.coalition.budget == 100


def test_insufficient_budget_or_unavailable_type_does_not_mutate(battery: Any) -> None:
    w = battery
    w.a.coalition.budget = 2
    with pytest.raises(ValueError, match="money"):
        buy(w)
    with pytest.raises(ValueError, match="available faction"):
        buy(w, name="M1A2 Abrams")
    assert w.a.coalition.budget == 2 and len(list(w.sam.units)) == 2


def test_mobile_battery_without_towed_pieces_and_fixed_battery_are_excluded(
    battery: Any,
) -> None:
    kind = GroundUnitType.named(PATRIOT[0])
    with patch(
        "game.groundmovement.samtrucks.movement_mobility",
        side_effect=lambda unit: (
            GroundMobility(MobilityMode.FIXED)
            if unit == kind
            else movement_mobility(unit)
        ),
    ):
        assert options(battery).truck_limit == 0
        with pytest.raises(ValueError, match="mobile SAM"):
            buy(battery)
    make_site(battery, KUB)
    assert options(battery).truck_limit == 0


def test_ownership_and_in_transit_checks(battery: Any) -> None:
    w = battery
    with pytest.raises(PermissionError):
        sam_truck_options(w.game, w.sam.id, Player.RED)
    w.sam.in_transit = True
    with pytest.raises(ValueError, match="Stop"):
        buy(w)
    assert len(list(w.sam.units)) == 2 and w.a.coalition.budget == 100


def test_destroyed_battery_is_not_revived_by_buying_trucks(battery: Any) -> None:
    for unit in battery.sam.units:
        unit.alive = False
    with pytest.raises(ValueError, match="Repair"):
        buy(battery)
    assert battery.sam.is_dead


def test_rest_validates_cap_types_and_ownership(battery: Any) -> None:
    w = battery
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[GameContext.require] = lambda: w.game

    class Service:
        run = staticmethod(lambda action: action())
        inspect = staticmethod(lambda game, action: action())

        def buy_sam_trucks(
            self, game: Any, source: Any, owner: Any, name: str, quantity: int
        ) -> Any:
            return buy_sam_trucks(
                game, source, owner, name, quantity, GameUpdateEvents()
            )

    app.dependency_overrides[commands] = Service
    client = TestClient(app)
    url = f"/tgos/{w.sam.id}/towing-trucks"
    assert client.get(url).json()["truck_limit"] == 4
    assert (
        client.post(url, json={"unit_type": PATRIOT[2], "quantity": True}).status_code
        == 422
    )
    assert (
        client.post(url, json={"unit_type": PATRIOT[2], "quantity": 5}).status_code
        == 400
    )
    result = client.post(url, json={"unit_type": PATRIOT[2], "quantity": 4})
    assert result.status_code == 200, result.text
    assert result.json()["remaining"] == 0
    w.a.coalition.player = Player.RED
    assert (
        client.post(url, json={"unit_type": PATRIOT[2], "quantity": 1}).status_code
        == 403
    )


def test_qt_commands_require_planning_before_mutating(battery: Any) -> None:
    command: Any = NS(
        model=NS(game=battery.game, sim_controller=NS(game_loop=NS(started=True)))
    )
    command.require_campaign = lambda game: GroundMovementCommands.require_campaign(
        command, game
    )
    command.require_planning = lambda game: GroundMovementCommands.require_planning(
        command, game
    )
    with pytest.raises(MovementCommandError, match="during a mission"):
        GroundMovementCommands.buy_sam_trucks(
            command, battery.game, battery.sam.id, Player.BLUE, PATRIOT[2], 1
        )
    assert len(list(battery.sam.units)) == 2 and battery.a.coalition.budget == 100
