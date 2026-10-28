"""RED missile commands share player rules and cannot access BLUE launchers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import pickle
import threading
import time
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from game import missiletargets as mt
from game.agent import schemas, service
from game.server.dependencies import GameContext
from game.server.retributionai.routes import router
from game.server.security import ApiKeyManager
from game.theater.player import Player
from tests.test_missile_targets import missiles  # noqa: F401
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401


@pytest.fixture
def missile_api(missiles: Any, controls: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    w = missiles
    w.a._coalition.player = w.b._coalition.player = Player.RED
    w.enemy._coalition.player = Player.BLUE
    monkeypatch.setattr(GameContext, "_game_model", controls.model, raising=False)
    monkeypatch.setattr(service, "note_ai_activity", lambda: None)
    monkeypatch.setattr(service, "_missile_intel", lambda game: {str(w.target.id)})
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as worker:

        def request(
            method: str, path: str = "", *, auth: bool = True, **kwargs: Any
        ) -> Any:
            if auth:
                kwargs["headers"] = {"X-API-Key": ApiKeyManager.current_key()}
            future = worker.submit(
                client.request, method, "/retribution-ai/missiles" + path, **kwargs
            )
            deadline = time.monotonic() + 15
            while not future.done() and time.monotonic() < deadline:
                controls.app.processEvents()
                try:
                    return future.result(timeout=0.002)
                except TimeoutError:
                    pass
            return future.result(timeout=1)

        yield request


def body(w: Any) -> dict[str, Any]:
    return {"source_id": str(w.site.id), "target_id": str(w.target.id)}


def test_rest_preview_assign_list_and_cancel(
    missiles: Any, controls: Any, missile_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = missiles
    calls: list[int] = []
    assign = mt.assign

    def recorded(*args: Any, **kwargs: Any) -> Any:
        calls.append(threading.get_ident())
        return assign(*args, **kwargs)

    monkeypatch.setattr(mt, "assign", recorded)
    assert {item["source_id"] for item in missile_api("GET").json()} == {
        str(w.site.id),
        str(w.ship.id),
    }
    options = missile_api("GET", f"/{w.site.id}").json()
    assert [t["id"] for t in options["targets"]] == [str(w.target.id)]
    before = pickle.dumps(w.game)
    assert missile_api("POST", "/preview", json=body(w)).json()["target_name"] == "MINK"
    assert pickle.dumps(w.game) == before
    response = missile_api("POST", "/target", json=body(w))
    assert response.status_code == 200, response.text
    assert calls == [threading.get_ident()] and controls.sent
    order = mt.stored(w.site)
    assert order is not None and order.owner is Player.RED
    response = missile_api("DELETE", f"/{w.site.id}/target")
    assert response.status_code == 200 and response.json()["cleared"]
    assert mt.stored(w.site) is None


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", ""),
        ("GET", "/bad"),
        ("POST", "/preview"),
        ("POST", "/target"),
        ("DELETE", "/bad/target"),
    ],
)
def test_token_and_side_guard_all_routes(
    missiles: Any, missile_api: Any, method: str, path: str
) -> None:
    args = (
        {"json": {**body(missiles), "side": "blue"}}
        if method == "POST"
        else {"params": {"side": "blue"}}
    )
    assert missile_api(method, path, auth=False, **args).status_code == 403
    assert missile_api(method, path, **args).status_code == 403


def test_other_side_sources_and_hidden_targets_are_refused(
    missiles: Any, missile_api: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = missiles
    before = pickle.dumps(w.game)
    assert missile_api("GET", f"/{w.target.id}").status_code == 400
    assert (
        missile_api(
            "POST",
            "/target",
            json={"source_id": str(w.target.id), "target_id": str(w.site.id)},
        ).status_code
        == 400
    )
    assert missile_api("DELETE", f"/{w.target.id}/target").status_code == 400
    monkeypatch.setattr(service, "_missile_intel", lambda game: set())
    response = missile_api("POST", "/preview", json=body(w))
    assert response.status_code == 400 and "MINK" not in response.text
    assert pickle.dumps(w.game) == before


def test_phase_and_changed_ownership_rechecked(
    missiles: Any, controls: Any, missile_api: Any
) -> None:
    w = missiles
    assert missile_api("POST", "/preview", json=body(w)).status_code == 200
    controls.model.sim_controller.game_loop.started = True
    assert missile_api("POST", "/target", json=body(w)).status_code == 409
    assert missile_api("DELETE", f"/{w.site.id}/target").status_code == 409
    controls.model.sim_controller.game_loop.started = False
    w.a._coalition.player = Player.BLUE
    assert missile_api("POST", "/target", json=body(w)).status_code == 400
    assert mt.stored(w.site) is None


def test_empty_gps_explicit_confirmation_and_schema_bounds(
    missiles: Any, missile_api: Any
) -> None:
    from dcs import Point

    w = missiles
    at = Point(70000, 1000, w.game.theater.terrain).latlng()
    request = {"source_id": str(w.site.id), "lat": at.lat, "lng": at.lng}
    assert missile_api("POST", "/preview", json=request).json()["requires_confirmation"]
    assert missile_api("POST", "/target", json=request).status_code == 400
    assert (
        missile_api(
            "POST", "/target", json={**request, "confirm_empty": True}
        ).status_code
        == 200
    )
    for extra in ({"lat": 91}, {"lat": "NaN"}, {"owner": "blue"}):
        assert (
            missile_api("POST", "/target", json={**request, **extra}).status_code == 422
        )


def test_mcp_schema_and_transport_use_same_service(
    missiles: Any, missile_api: Any
) -> None:
    from game.mcp import server

    w = missiles

    async def check() -> None:
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        assert "request" in tools["assign_missile_target"].inputSchema["properties"]
        result: Any = await server.mcp.call_tool(
            "preview_missile_target", {"request": body(w)}
        )
        blocks = result[0] if isinstance(result, tuple) else result
        assert "MINK" in blocks[0].text

    asyncio.run(check())
    response = server.assign_missile_target(schemas.MissileTargetRequest(**body(w)))
    assert response["target_id"] == str(w.target.id)
    assert server.clear_missile_target(str(w.site.id))["cleared"]
    with pytest.raises(service.SideNotAllowedError):
        server.missile_launchers("blue")
