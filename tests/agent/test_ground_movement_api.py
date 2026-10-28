"""OPFOR uses shared movement rules without exposing or commanding BLUE reserves."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
import json
import os
import pickle
import threading
import time
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dcs import Point
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PySide6.QtWidgets import QApplication
import pytest

from game.agent import groundmovement, schemas, service
from game.groundmovement.dispatch import advance_armor
from game.groundmovement.settings import set_enabled
from game.server import EventStream
from game.server.dependencies import GameContext
from game.server.retributionai.routes import router
from game.server.security import ApiKeyManager
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import SamGroundObject, VehicleGroupGroundObject
from qt_ui.groundmovement import GroundMovementCommands, MovementCommandError
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_base_reserve_groups import stock  # noqa: F401

ROOT = "/retribution-ai/ground/movement"


@pytest.fixture
def api(stock: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    prepare(stock)
    stock.a._coalition.player = stock.b._coalition.player = Player.RED
    stock.enemy._coalition.player = Player.BLUE
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(GameUpdateSignal, "instance", None)
    signal = GameUpdateSignal()
    model: Any = SimpleNamespace(
        game=stock.game,
        sim_controller=SimpleNamespace(game_loop=SimpleNamespace(started=False)),
    )
    commands = GroundMovementCommands(model)
    model.ground_movement_commands = commands
    monkeypatch.setattr(GameContext, "_game_model", model, raising=False)
    monkeypatch.setattr(service, "note_ai_activity", lambda: None)
    events: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", events.append)
    routes = FastAPI()
    routes.include_router(router)
    client = TestClient(routes)
    executor = ThreadPoolExecutor(max_workers=1)

    def request(method: str, path: str = "", *, auth: bool = True, **kw: Any) -> Any:
        if auth:
            kw["headers"] = {"X-API-Key": ApiKeyManager.current_key()}
        future = executor.submit(client.request, method, ROOT + path, **kw)
        deadline = time.monotonic() + 15
        while not future.done() and time.monotonic() < deadline:
            app.processEvents()
            try:
                return future.result(timeout=0.002)
            except TimeoutError:
                pass
        return future.result(timeout=1)

    body = {
        "source_id": str(stock.source.id),
        "unit_ids": [1, 2],
        "destination_kind": "base",
        "base_id": str(stock.b.id),
    }
    yield SimpleNamespace(
        request=request,
        model=model,
        commands=commands,
        events=events,
        body=body,
        signal=signal,
        app=app,
    )
    app.processEvents()
    executor.shutdown()
    client.close()


def confirmed(api: Any, body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = api.body if body is None else body
    response = api.request("POST", "/preview", json=body)
    assert response.status_code == 200, response.text
    return {**body, "preview_token": response.json()["preview_token"]}


def gps(stock: Any, *, x: float = 80, base: bool = False) -> dict[str, Any]:
    at = Point(x, 10, stock.game.theater.terrain).latlng()
    return {
        "source_id": str(stock.a.id if base else stock.source.id),
        "source_kind": "base" if base else "armor",
        "destination_kind": "position",
        "lat": at.lat,
        "lng": at.lng,
        **({"units": {stock.units[1].variant_id: 2}} if base else {"unit_ids": [7]}),
    }


def test_read_only_options_preview_and_own_context(stock: Any, api: Any) -> None:
    before = pickle.dumps(stock.game)
    response = api.request(
        "GET", "/options", params={"source_id": str(stock.source.id)}
    )
    assert response.status_code == 200
    options = response.json()
    assert options["available_tractors"] == 2 and options["towed_pieces"] == 4
    assert {u["id"] for u in options["units"]} == set(range(1, 8))
    assert {b["id"] for b in options["bases"]} == {str(stock.a.id), str(stock.b.id)}
    assert options["fronts"] == [
        {
            "base_id": str(stock.a.id),
            "opposing_base_id": str(stock.enemy.id),
            "name": "A / Enemy",
        }
    ]
    preview = api.request("POST", "/preview", json=api.body).json()
    assert preview["unit_ids"] == [1, 2, 5, 6]
    assert preview["automatically_included_ids"] == [5, 6]
    assert preview["towing"] == [[1, 5], [2, 6]]
    assert preview["arrival_in_turns"] == 1 and preview["road_distance_m"] > 0
    assert (
        "segments" not in preview
    )  # Do not send hundreds of road points to the agent.
    assert preview["total_distance_m"] == pytest.approx(
        preview["road_distance_m"] + preview["offroad_distance_m"]
    )
    context = groundmovement.context(stock.game, Player.RED)
    assert context is not None and context.enabled
    assert [g.id for g in context.reserve_groups] == [str(stock.source.id)]
    assert context.orders == []
    assert pickle.dumps(stock.game) == before and not api.events


def test_dispatch_pause_stop_and_no_duplicate_inventory(stock: Any, api: Any) -> None:
    body = confirmed(api)
    response = api.request("POST", "/dispatch", json=body)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["status"] == "moving"
    assert order["surviving_units"] == order["original_units"] == 4
    assert order["remaining_turns"] == 1 and order["progress_percent"] == 0
    assert api.events
    assert api.request("GET").json() == [order]
    context = groundmovement.context(stock.game, Player.RED)
    assert context is not None
    moving = next(g for g in context.reserve_groups if g.in_transit)
    assert moving.selectable_units == 0
    all_ids = [
        u.id
        for cp in stock.game.theater.controlpoints
        for g in cp.ground_objects
        for u in g.units
    ]
    assert sorted(all_ids) == list(range(1, 9))
    before = pickle.dumps(stock.game)
    assert api.request("POST", "/dispatch", json=body).status_code == 400
    assert pickle.dumps(stock.game) == before
    set_enabled(stock.game.settings, False)
    paused = api.request("GET").json()[0]
    assert paused["status"] == "paused" and "pause_reason" in paused
    assert "remaining_turns" not in paused
    stopped = api.request("POST", "/stop", json={"order_id": order["order_id"]})
    assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"
    assert stopped.json()["pos"] == order["pos"]
    assert not stock.game.ground_movements.reserved_unit_ids
    assert (
        api.request("POST", "/stop", json={"order_id": order["order_id"]}).status_code
        == 200
    )


def test_road_losses_and_delivery_persist(stock: Any, api: Any) -> None:
    order = api.request("POST", "/dispatch", json=confirmed(api)).json()
    transit = stock.game.ground_movements.transits[UUID(order["order_id"])]
    group = stock.game.db.tgos.get(transit.detachment_id)
    next(u for u in group.units if u.id == 5).alive = False
    assert api.request("GET").json()[0]["surviving_units"] == 2
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    delivered = api.request("GET").json()[0]
    assert delivered["status"] == "arrived" and delivered["progress_percent"] == 100
    assert delivered["surviving_units"] == 2
    copied = pickle.loads(pickle.dumps(stock.game))
    assert groundmovement.orders(copied)[0].model_dump(exclude_none=True) == delivered


def test_base_stock_deployment_and_automatic_tractors(stock: Any, api: Any) -> None:
    options = api.request(
        "GET", "/options", params={"source_id": str(stock.a.id), "source_kind": "base"}
    ).json()
    assert {u["unit_type"]: u["available"] for u in options["units"]} == {
        stock.units[7].variant_id: 4,
        stock.units[5].variant_id: 3,
        stock.units[1].variant_id: 2,
    }
    body = gps(stock, base=True)
    before = pickle.dumps(stock.game)
    preview = api.request("POST", "/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["automatically_added"] == {stock.units[5].variant_id: 2}
    assert preview.json()["first_turn_stop"] == pytest.approx(
        preview.json()["destination"]
    )
    assert "unit_ids" not in preview.json()
    assert pickle.dumps(stock.game) == before
    response = api.request(
        "POST",
        "/dispatch",
        json={**body, "preview_token": preview.json()["preview_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_id"] == str(stock.a.id)
    assert stock.a.base.armor == {stock.units[7]: 4, stock.units[5]: 1}
    after = pickle.dumps(stock.game)
    assert (
        api.request(
            "POST",
            "/dispatch",
            json={**body, "preview_token": preview.json()["preview_token"]},
        ).status_code
        == 400
    )
    assert pickle.dumps(stock.game) == after


@pytest.mark.parametrize("destination", ["position", "frontline"])
def test_gps_and_frontline_destinations(stock: Any, api: Any, destination: str) -> None:
    body = (
        gps(stock)
        if destination == "position"
        else {
            **api.body,
            "destination_kind": "frontline",
            "base_id": str(stock.a.id),
            "opposing_base_id": str(stock.enemy.id),
        }
    )
    response = api.request("POST", "/dispatch", json=confirmed(api, body))
    assert response.status_code == 200, response.text
    assert response.json()["destination_kind"] == destination


@pytest.mark.parametrize(
    "change", ["turn", "budget", "casualty", "territory", "mission", "stock"]
)
def test_stale_confirmation_has_no_side_effects(
    stock: Any, api: Any, change: str
) -> None:
    body = confirmed(api, gps(stock, base=change == "stock"))
    if change == "turn":
        stock.game.turn += 1
    elif change == "budget":
        stock.game.settings.set_plugin_option("groundmovement.roadMilesPerTurn", 1)
    elif change == "casualty":
        next(u for u in stock.source.units if u.id == 7).alive = False
    elif change == "territory":
        stock.b._coalition.player = Player.BLUE
    elif change == "mission":
        api.model.sim_controller.game_loop.started = True
    else:
        stock.a.base.armor[stock.units[1]] = 1
    before = pickle.dumps(stock.game)
    response = api.request("POST", "/dispatch", json=body)
    assert response.status_code in (400, 403, 409), response.text
    assert pickle.dumps(stock.game) == before and not api.events


@pytest.mark.parametrize(
    "body_change",
    [
        {"unit_ids": [True]},
        {"unit_ids": []},
        {"unit_ids": [1, 1]},
        {"unit_ids": [999]},
        {"units": {"unknown": 1}},
        {"lat": 91},
        {"lng": 181},
        {"lat": "NaN"},
        {"owner": "blue"},
        {"source_id": "bad"},
    ],
)
def test_invalid_requests_do_not_mutate(
    stock: Any, api: Any, body_change: dict[str, Any]
) -> None:
    before = pickle.dumps(stock.game)
    response = api.request("POST", "/preview", json={**api.body, **body_change})
    assert response.status_code in (400, 422), response.text
    assert pickle.dumps(stock.game) == before and not api.events


@pytest.mark.parametrize(
    "change",
    [
        {"units": {"unknown": 1}},
        {"units": {"M1A2 Abrams": True}},
        {"units": {"M1A2 Abrams": -1}},
        {"units": {"M1A2 Abrams": 5}},
        {"lat": None},
        {"unit_ids": [7]},
    ],
)
def test_invalid_base_deployment_does_not_spend_stock(
    stock: Any, api: Any, change: dict[str, Any]
) -> None:
    before = pickle.dumps(stock.game)
    response = api.request("POST", "/preview", json={**gps(stock, base=True), **change})
    assert response.status_code in (400, 422), response.text
    assert pickle.dumps(stock.game) == before


def test_blue_and_sam_ids_are_not_readable_or_movable(stock: Any, api: Any) -> None:
    blue = VehicleGroupGroundObject(
        "Blue secret", PresetLocation("Blue", stock.enemy.position), stock.enemy, None
    )
    sam = SamGroundObject(
        "SAM", PresetLocation("SAM", stock.source.position), stock.a, None
    )
    for obj in (blue, sam):
        stock.game.db.tgos.add(obj.id, obj)
        obj.control_point.connected_objectives.append(obj)
    before = pickle.dumps(stock.game)
    for obj in (blue, sam):
        options = api.request("GET", "/options", params={"source_id": str(obj.id)})
        assert options.status_code == 400 and "Blue secret" not in options.text
        assert (
            api.request(
                "POST", "/preview", json={**api.body, "source_id": str(obj.id)}
            ).status_code
            == 400
        )
    assert (
        api.request(
            "GET",
            "/options",
            params={"source_id": str(stock.enemy.id), "source_kind": "base"},
        ).status_code
        == 400
    )
    assert api.request("POST", "/preview", json=gps(stock, x=195)).status_code == 403
    context = groundmovement.context(stock.game, Player.RED)
    assert context is not None and {g.id for g in context.reserve_groups} == {
        str(stock.source.id)
    }
    assert pickle.dumps(stock.game) == before


def test_auth_and_side_guards_precede_campaign_access(
    stock: Any, api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> Any:
        raise AssertionError("must not read campaign")

    monkeypatch.setattr(service, "_require_game", fail)
    assert api.request("GET", auth=False).status_code == 403
    assert api.request("GET", params={"side": "blue"}).status_code == 403
    assert (
        api.request("POST", "/preview", json={**api.body, "side": "blue"}).status_code
        == 403
    )
    assert (
        api.request(
            "POST",
            "/dispatch",
            json={**api.body, "side": "blue", "preview_token": "0" * 64},
        ).status_code
        == 403
    )
    assert (
        api.request(
            "POST", "/stop", json={"side": "blue", "order_id": str(uuid4())}
        ).status_code
        == 403
    )
    with pytest.raises(service.SideNotAllowedError):
        service.ground_movement_options("blue", str(stock.source.id))


def test_other_side_orders_are_hidden_and_stop_rechecks_ownership(
    stock: Any, api: Any
) -> None:
    order = api.request("POST", "/dispatch", json=confirmed(api)).json()
    order_id = UUID(order["order_id"])
    orders = stock.game.ground_movements.orders
    orders[order_id] = replace(orders[order_id], owner=Player.BLUE)
    before = pickle.dumps(stock.game)
    assert api.request("GET").json() == []
    assert (
        api.request("POST", "/stop", json={"order_id": str(order_id)}).status_code
        == 400
    )
    assert pickle.dumps(stock.game) == before


def test_disabled_dependency_rejects_new_orders_and_mission_blocks_stop(
    stock: Any, api: Any
) -> None:
    order = api.request("POST", "/dispatch", json=confirmed(api)).json()
    api.model.sim_controller.game_loop.started = True
    assert (
        api.request("POST", "/stop", json={"order_id": order["order_id"]}).status_code
        == 409
    )
    api.model.sim_controller.game_loop.started = False
    stock.game.settings.motorpool_enabled = False
    assert api.request("POST", "/preview", json=gps(stock)).status_code == 400
    assert api.request("GET").json()[0]["status"] == "paused"


def test_service_runs_commands_on_campaign_thread(
    stock: Any, api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[int] = []
    original = groundmovement.preview_view

    def preview(*args: Any) -> dict[str, Any]:
        called.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(groundmovement, "preview_view", preview)
    assert api.request("POST", "/preview", json=api.body).status_code == 200
    assert called == [threading.get_ident()]
    monkeypatch.setattr(service, "_require_game", lambda: SimpleNamespace())
    with pytest.raises(MovementCommandError, match="campaign changed"):
        service.ground_movements()


def test_mcp_tools_use_same_contract_and_service(stock: Any, api: Any) -> None:
    from game.mcp import server

    async def exercise() -> None:
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        for name in (
            "ground_movement_options",
            "preview_ground_movement",
            "dispatch_ground_movement",
            "ground_movements",
            "stop_ground_movement",
        ):
            assert name in tools
        request_schema = tools["preview_ground_movement"].inputSchema
        assert "request" in request_schema["properties"]
        result: Any = await server.mcp.call_tool(
            "preview_ground_movement", {"request": api.body}
        )
        blocks = result[0] if isinstance(result, tuple) else result
        preview = json.loads(blocks[0].text)
        assert preview == service.preview_ground_movement(
            "red", schemas.GroundMovementRequest(**api.body)
        )

    asyncio.run(exercise())
    body = confirmed(api)
    order = server.dispatch_ground_movement(
        schemas.GroundMovementDispatchRequest(**body)
    )
    assert server.ground_movements() == api.request("GET").json() == [order]
    assert server.stop_ground_movement(order["order_id"])["status"] == "stopped"
    with pytest.raises(service.SideNotAllowedError):
        server.ground_movements("blue")
