"""Armor previews validate real unit identities, destinations and terrain routes."""

from __future__ import annotations

from dataclasses import replace
import math
import os
import pickle
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dcs import Point
from dcs.terrain import Caucasus
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from shapely.geometry import MultiPolygon, box

from game.db.gamedb import GameDb
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.journey import GroundJourney, GroundRoute, GroundSegment
from game.groundmovement.orders import (
    DestinationKind,
    GroundMovementOrders,
    GroundPosition as P,
    MovementDestination,
    MovementSource,
)
from game.groundmovement.planning import (
    armor_movement_options,
    movement_destination,
    preview_armor_movement,
)
from game.groundmovement.routing import CampaignGroundRouter, GroundRouteError
from game.groundmovement.settings import set_enabled
from game.point_with_heading import PointWithHeading
from game.server.dependencies import GameContext
from game.server.tgos import router
from game.server.tgos.groundmovement import commands
from game.settings import Settings
from game.theater.controlpoint import Fob
from game.theater.landmap import Landmap
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import SamGroundObject, VehicleGroupGroundObject
from game.theater.theatergroup import TheaterGroup, TheaterUnit
from game.utils import Heading


def landmap(*exclusions: Any) -> Landmap:
    return Landmap(
        MultiPolygon([box(-10000, -10000, 10000, 10000)]),
        MultiPolygon(exclusions),
        MultiPolygon(),
    )


def road(*points: tuple[float, float]) -> GroundRoute:
    return GroundRoute.from_points(P(*point) for point in points)


def test_nearest_road_access_and_mixed_budget() -> None:
    planner = CampaignGroundRouter(landmap(), [road((0, 0), (100, 0))])
    result = planner.plan(P(0, 10), P(100, 10), 100, 50)
    assert sum(s.length for s in result.segments if s.on_road) == pytest.approx(100)
    assert sum(s.length for s in result.segments if not s.on_road) == pytest.approx(20)
    assert result.segments[0] == GroundSegment(P(0, 10), P(0, 0), False)
    journey = GroundJourney(result)
    journey.advance(1, 100, 50)
    assert journey.position == P(80, 0)
    journey.advance(2, 100, 50)
    assert journey.completed and journey.position == P(100, 10)


def test_entries_on_same_road_do_not_detour_via_its_endpoints() -> None:
    planner = CampaignGroundRouter(
        landmap(), [road((0, 0), (100, 0)), road((100, 0), (0, 0))]
    )
    result = planner.plan(P(20, 0), P(80, 0), 100, 50)
    assert result.length == pytest.approx(60)
    assert all(s.on_road for s in result.segments)


def test_blocked_nearest_access_uses_another_reachable_road() -> None:
    planner = CampaignGroundRouter(
        landmap(box(-20, 20, 20, 80)),
        [road((-100, 0), (-100, 100), (100, 100), (100, 0))],
    )
    result = planner.plan(P(0, 10), P(0, 90), 100, 50)
    assert all(planner.allowed(segment) for segment in result.segments)
    assert result.segments[0].end.x in (-100, 100)
    assert any(segment.on_road for segment in result.segments)


def test_polyline_crossing_is_not_assumed_to_be_a_junction() -> None:
    planner = CampaignGroundRouter(
        landmap(), [road((0, 0), (100, 0)), road((50, -50), (50, 50))]
    )
    result = planner.plan(P(0, 0), P(50, 50), 100, 50)
    assert sum(s.length for s in result.segments if not s.on_road) == pytest.approx(50)


def test_base_access_connects_different_authored_departure_points() -> None:
    planner = CampaignGroundRouter(
        landmap(),
        [road((0, 0), (100, 0)), road((110, 10), (210, 10))],
        [GroundSegment(P(100, 0), P(110, 10), False)],
    )
    result = planner.plan(P(0, 0), P(210, 10), 100, 50)
    assert sum(s.length for s in result.segments if s.on_road) == pytest.approx(200)
    assert sum(s.length for s in result.segments if not s.on_road) == pytest.approx(
        math.sqrt(200)
    )


def test_no_campaign_roads_allow_only_a_validated_direct_offroad_route() -> None:
    planner = CampaignGroundRouter(landmap(), [])
    result = planner.plan(P(0, 0), P(100, 0), 100, 50)
    assert result.segments == (GroundSegment(P(0, 0), P(100, 0), False),)
    blocked = CampaignGroundRouter(landmap(box(40, -10, 60, 10)), [])
    with pytest.raises(GroundRouteError, match="off-road"):
        blocked.plan(P(0, 0), P(100, 0), 100, 50)


def test_unverified_water_crossing_is_not_treated_as_a_bridge() -> None:
    water = box(40, -10, 60, 10)
    terrain = Landmap(
        MultiPolygon([box(-10, -10, 40, 10), box(60, -10, 110, 10)]),
        MultiPolygon(),
        MultiPolygon([water]),
    )
    planner = CampaignGroundRouter(terrain, [road((0, 0), (100, 0))])
    with pytest.raises(GroundRouteError, match="water"):
        planner.plan(P(0, 0), P(100, 0), 100, 50)


def test_disconnected_roads_do_not_report_missing_access() -> None:
    planner = CampaignGroundRouter(
        landmap(box(40, -10000, 60, 10000)),
        [road((0, 0), (30, 0), (70, 0), (100, 0))],
    )
    with pytest.raises(GroundRouteError, match="Both ends can reach a road"):
        planner.plan(P(0, 10), P(100, 10), 100, 50)


@pytest.mark.parametrize("reverse", [False, True])
def test_blocked_access_identifies_the_affected_endpoint(reverse: bool) -> None:
    planner = CampaignGroundRouter(
        landmap(box(-10000, 40, 10000, 60)), [road((0, 0), (100, 0))]
    )
    endpoints = (P(0, 100), P(100, 10))
    origin, destination = endpoints[::-1] if reverse else endpoints
    label = "destination" if reverse else "group"
    with pytest.raises(GroundRouteError, match=f"access connects the {label}"):
        planner.plan(origin, destination, 100, 50)


@pytest.mark.parametrize("budget", [0, -1, True, math.inf, math.nan])
def test_invalid_budget_rejected(budget: Any) -> None:
    with pytest.raises(GroundRouteError, match="budgets"):
        CampaignGroundRouter(landmap(), []).plan(P(0, 0), P(100, 0), budget, 50)


def test_missing_map_excluded_destination_and_zero_length_rejected() -> None:
    with pytest.raises(GroundRouteError, match="exclusion-zone data"):
        CampaignGroundRouter(None, [])
    planner = CampaignGroundRouter(landmap(box(40, -10, 60, 10)), [])
    with pytest.raises(GroundRouteError, match="exclusion zone"):
        planner.plan(P(0, 0), P(50, 0), 100, 50)
    with pytest.raises(GroundRouteError, match="mapped land"):
        planner.plan(P(0, 0), P(20000, 0), 100, 50)
    with pytest.raises(GroundRouteError, match="already"):
        planner.plan(P(0, 0), P(0, 0), 100, 50)


@pytest.fixture
def world() -> Any:
    terrain = Caucasus()
    game: Any = SimpleNamespace(
        turn=1,
        settings=Settings(),
        db=GameDb(),
        ground_movements=GroundMovementOrders(),
        theater=SimpleNamespace(terrain=terrain, landmap=landmap(), controlpoints=[]),
    )
    set_enabled(game.settings, True)
    a = Fob("A", Point(0, 0, terrain), cast(Any, game.theater), Player.BLUE)
    b = Fob("B", Point(100, 0, terrain), cast(Any, game.theater), Player.BLUE)
    enemy = Fob("Enemy", Point(200, 0, terrain), cast(Any, game.theater), Player.RED)
    for cp in (a, b, enemy):
        cp._coalition = cast(Any, SimpleNamespace(player=cp.starting_coalition))
    a.convoy_routes[b] = (a.position, b.position)
    b.convoy_routes[a] = (b.position, a.position)
    a.front_lines[enemy] = cast(Any, object())
    game.theater.controlpoints = [a, b, enemy]
    source = VehicleGroupGroundObject(
        "Armor", PresetLocation("Armor", Point(10, 10, terrain)), a, None
    )
    gun = GroundUnitType.named("AAA ZU-23 Emplacement")
    truck = GroundUnitType.named("Truck Ural-375")
    tank = GroundUnitType.named("M1A2 Abrams")
    unit_types = {1: gun, 2: gun, 3: gun, 4: gun, 5: truck, 6: truck, 7: tank, 8: gun}
    source.groups = [
        TheaterGroup(
            1,
            "Armor",
            PointWithHeading.from_point(source.position, Heading.from_degrees(0)),
            [
                TheaterUnit(
                    i,
                    str(i),
                    unit.dcs_unit_type,
                    PointWithHeading.from_point(
                        source.position, Heading.from_degrees(0)
                    ),
                    source,
                    alive=i != 8,
                )
                for i, unit in unit_types.items()
            ],
            source,
        )
    ]
    a.connected_objectives.append(source)
    game.db.tgos.add(source.id, source)
    destination = movement_destination(
        game, Player.BLUE, DestinationKind.BASE, base_id=b.id
    )
    return SimpleNamespace(
        game=game,
        a=a,
        b=b,
        enemy=enemy,
        source=source,
        units=unit_types,
        destination=destination,
    )


def test_options_warn_about_shortage_and_dead_units_are_unavailable(world: Any) -> None:
    result = armor_movement_options(world.game, world.source.id, Player.BLUE)
    assert result.towed_pieces == 4 and result.available_tractors == 2
    assert {unit.id for unit in result.units} == set(range(1, 8))
    assert any("only 2" in warning for warning in result.warnings)
    with pytest.raises(ValueError, match="only 2"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, [1, 2, 3, 4], world.destination
        )


def test_partial_preview_auto_includes_tractors_without_changing_a_save(
    world: Any,
) -> None:
    before = pickle.dumps(world.game)
    result = preview_armor_movement(
        world.game, world.source.id, Player.BLUE, [1, 2], world.destination
    )
    assert result.manifest.unit_ids == (1, 2, 5, 6)
    assert result.manifest.towing == ((1, 5), (2, 6))
    assert result.remaining_unit_ids == (3, 4, 7)
    assert result.first_turn_stop == world.destination.position
    assert result.arrival_in_turns == 1 and result.road_distance_m == pytest.approx(90)
    assert pickle.dumps(world.game) == before


def test_reservations_include_automatically_assigned_tractors(world: Any) -> None:
    order = world.game.ground_movements.plan(
        world.game.settings,
        source_id=world.source.id,
        source_kind=MovementSource.ARMOR,
        owner=Player.BLUE,
        origin=P(10, 10),
        destination=world.destination,
        units={i: u for i, u in world.units.items() if i != 8},
        selected=[1],
        turn=0,
    )
    options = armor_movement_options(world.game, world.source.id, Player.BLUE)
    assert {unit.id for unit in options.units if unit.reserved} == {1, 5}
    assert options.available_tractors == 1
    result = preview_armor_movement(
        world.game, world.source.id, Player.BLUE, [2], world.destination
    )
    assert result.manifest.towing == ((2, 6),)
    assert {1, 5} <= set(result.remaining_unit_ids)
    world.game.ground_movements.cancel(order.id)
    assert (
        armor_movement_options(
            world.game, world.source.id, Player.BLUE
        ).available_tractors
        == 2
    )


@pytest.mark.parametrize("selected", [[], [1, 1], [8], [999], [True]])
def test_bad_or_dead_selection_does_not_modify_the_game(
    world: Any, selected: list[int]
) -> None:
    before = pickle.dumps(world.game)
    with pytest.raises(ValueError):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, selected, world.destination
        )
    assert pickle.dumps(world.game) == before


def test_frontline_requires_a_current_enemy_neighbor_and_uses_base_stock(
    world: Any,
) -> None:
    destination = movement_destination(
        world.game,
        Player.BLUE,
        DestinationKind.FRONTLINE,
        base_id=world.a.id,
        opposing_base_id=world.enemy.id,
    )
    assert destination.position == P(0, 0)
    result = preview_armor_movement(
        world.game, world.source.id, Player.BLUE, [7], destination
    )
    assert result.destination.target_id == world.a.id
    world.a.front_lines.clear()
    with pytest.raises(ValueError, match="active front"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, [7], destination
        )


def test_enemy_source_and_destination_are_rejected(world: Any) -> None:
    with pytest.raises(PermissionError):
        armor_movement_options(world.game, world.source.id, Player.RED)
    with pytest.raises(PermissionError):
        movement_destination(
            world.game, Player.BLUE, DestinationKind.BASE, base_id=world.enemy.id
        )
    with pytest.raises(ValueError, match="stale"):
        preview_armor_movement(
            world.game,
            world.source.id,
            Player.BLUE,
            [7],
            replace(world.destination, position=P(123, 456)),
        )


def test_red_uses_the_same_validation_with_its_own_roads(world: Any) -> None:
    world.a._coalition.player = Player.RED
    world.b._coalition.player = Player.RED
    result = preview_armor_movement(
        world.game, world.source.id, Player.RED, [7], world.destination
    )
    assert result.road_distance_m > 0
    with pytest.raises(PermissionError):
        armor_movement_options(world.game, world.source.id, Player.BLUE)


def test_destination_must_be_able_to_host_ground_units(
    world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Fob, "can_deploy_ground_units", property(lambda _cp: False))
    with pytest.raises(ValueError, match="cannot host"):
        movement_destination(
            world.game, Player.BLUE, DestinationKind.BASE, base_id=world.b.id
        )


def test_sams_and_disabled_movement_are_not_accepted(world: Any) -> None:
    sam = SamGroundObject(
        "SAM", PresetLocation("SAM", world.source.position), world.a, None
    )
    world.game.db.tgos.add(sam.id, sam)
    with pytest.raises(ValueError, match="armor group"):
        armor_movement_options(world.game, sam.id, Player.BLUE)
    set_enabled(world.game.settings, False)
    assert not armor_movement_options(world.game, world.source.id, Player.BLUE).enabled
    with pytest.raises(ValueError, match="Motor Pool"):
        preview_armor_movement(
            world.game, world.source.id, Player.BLUE, [7], world.destination
        )


def test_preview_estimates_multiple_turns_and_the_first_stop(world: Any) -> None:
    world.b.position.x = 4000
    world.game.settings.set_plugin_option("groundmovement.roadMilesPerTurn", 1)
    world.game.settings.set_plugin_option("groundmovement.offRoadMilesPerTurn", 1)
    destination = movement_destination(
        world.game, Player.BLUE, DestinationKind.BASE, base_id=world.b.id
    )
    result = preview_armor_movement(
        world.game, world.source.id, Player.BLUE, [7], destination
    )
    assert result.arrival_in_turns == 3
    assert result.travel_turns == pytest.approx(4000 / 1609.344)
    assert result.first_turn_stop.x == pytest.approx(1609.344)
    assert result.first_turn_stop.z == 0


@pytest.fixture
def client(world: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[GameContext.require] = lambda: world.game
    app.dependency_overrides[commands] = lambda: SimpleNamespace(
        run=lambda action: action(), inspect=lambda game, action: action()
    )
    return TestClient(app)


def test_rest_preview_has_distances_towing_and_does_not_mutate(
    world: Any, client: TestClient
) -> None:
    before = pickle.dumps(world.game)
    url = f"/tgos/{world.source.id}/ground-movement"
    assert client.get(url + "/options").json()["available_tractors"] == 2
    response = client.post(
        url + "/preview",
        json={
            "unit_ids": [1, 2],
            "destination_kind": "base",
            "base_id": str(world.b.id),
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["automatically_included_ids"] == [5, 6]
    assert result["remaining_unit_ids"] == [3, 4, 7]
    assert result["towing"] == [[1, 5], [2, 6]] and result["dispatch_available"]
    assert result["road_distance_m"] > 0 and result["offroad_distance_m"] > 0
    assert pickle.dumps(world.game) == before


@pytest.mark.parametrize(
    "ids,status", [([True], 422), ([1, 1], 400), ([8], 400), ([999], 400)]
)
def test_rest_rejects_bad_unit_ids(
    world: Any, client: TestClient, ids: list[Any], status: int
) -> None:
    response = client.post(
        f"/tgos/{world.source.id}/ground-movement/preview",
        json={"unit_ids": ids, "destination_kind": "base", "base_id": str(world.b.id)},
    )
    assert response.status_code == status


def test_rest_rejects_enemy_source_and_unknown_fields(
    world: Any, client: TestClient
) -> None:
    url = f"/tgos/{world.source.id}/ground-movement"
    body = {"unit_ids": [7], "destination_kind": "base", "base_id": str(world.b.id)}
    assert (
        client.post(url + "/preview", json={**body, "side": "red"}).status_code == 422
    )
    world.a._coalition.player = Player.RED
    assert client.get(url + "/options").status_code == 403
    assert client.post(url + "/preview", json=body).status_code == 403


@pytest.mark.parametrize("owner", [Player.BLUE, Player.RED])
def test_ground_transport_card_warns_about_missing_tractors(
    world: Any, owner: Player
) -> None:
    from PySide6.QtWidgets import QApplication, QLabel
    from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu

    app = QApplication.instance() or QApplication([])
    world.a._coalition.player = owner
    window: Any = SimpleNamespace(
        game=world.game,
        ground_object=world.source,
        _friendly=True,
        _viewer=owner,
        _move_units=lambda: None,
    )
    card = QGroundObjectMenu._ground_transport(window)
    assert app is not None and card is not None
    texts = [label.text() for label in card.findChildren(QLabel)]
    assert any("2 tractors available" in text for text in texts)
    assert any("only 2 are available" in text for text in texts)
    set_enabled(world.game.settings, False)
    assert QGroundObjectMenu._ground_transport(window) is None
