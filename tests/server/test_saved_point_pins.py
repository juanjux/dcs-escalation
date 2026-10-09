"""Map edits share the same saved points as Player Aircrafts."""

import pickle
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from dcs.mapping import LatLng, Point
from dcs.terrain import Caucasus
from fastapi import FastAPI
from fastapi.testclient import TestClient

from game.ato.flight import Flight
from game.ato.savedpoints import PointKind, SavedPoint, points_of
from game.server import GameContext
from game.server.savedpoints import routes
from qt_ui.windows.playable.model import Aircraft, Clipboard


def _flight() -> Any:
    flight = MagicMock(spec=Flight)
    flight.id = uuid4()
    flight.client_count = 1
    flight.custom_name = "Hawg"
    flight.unit_type = SimpleNamespace(
        dcs_unit_type=SimpleNamespace(id="A-10C_2"), display_name="A-10C II"
    )
    flight.departure = SimpleNamespace(name="Base")
    flight.squadron = SimpleNamespace(saved_points=[])
    return flight


@pytest.fixture
def api(monkeypatch: Any) -> Any:
    flight = _flight()
    terrain = Caucasus()
    at = Point.from_latlng(LatLng(42, 42), terrain)
    point = SavedPoint(PointKind.WAYPOINT, "Target", at.x, at.y, 100)
    points_of(flight).append(point)
    flights = {flight.id: flight}
    package = SimpleNamespace(flights=[flight])
    game = SimpleNamespace(
        blue=SimpleNamespace(ato=SimpleNamespace(packages=[package])),
        db=SimpleNamespace(flights=SimpleNamespace(get=lambda key: flights[key])),
        theater=SimpleNamespace(terrain=terrain),
        settings=SimpleNamespace(coordinate_format=None),
    )
    notify = MagicMock()
    monkeypatch.setattr(routes, "publish_points_changed", notify)
    monkeypatch.setattr("game.elevation.elevation_ft", lambda lat, lng: 321)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[GameContext.require] = lambda: game
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            game=game,
            flight=flight,
            point=point,
            package=package,
            flights=flights,
            notify=notify,
            url=f"/saved-points/{flight.id}/points/{point.id}",
        )


def test_uuid_upgrade_is_stable_and_survives_save_reload() -> None:
    point = SavedPoint(PointKind.WAYPOINT, "Old", 1, 2)
    del point.id
    flight = _flight()
    flight.squadron.saved_points = [point]
    migrated = points_of(flight)[0]
    identity = migrated.id
    assert points_of(flight)[0].id == identity
    assert pickle.loads(pickle.dumps(migrated)).id == identity
    assert migrated == SavedPoint(PointKind.WAYPOINT, "Old", 1, 2)


def test_clipboard_paste_creates_independent_identities() -> None:
    source, target = _flight(), _flight()
    original = SavedPoint(PointKind.WAYPOINT, "Target", 1, 2)
    points_of(source).append(original)
    clipboard = Clipboard()
    clipboard.take_one(original, "Source")
    assert clipboard.paste_into(Aircraft(target)) == 1
    assert clipboard.paste_into(Aircraft(target)) == 1
    assert len({original.id, *(point.id for point in points_of(target))}) == 3


def test_list_returns_position_and_shared_identity(api: Any) -> None:
    another = _flight()
    another.squadron = api.flight.squadron
    api.package.flights.append(another)
    body = api.client.get("/saved-points/").json()
    assert [one["points"][0]["id"] for one in body] == [str(api.point.id)] * 2
    assert body[0]["points"][0]["position"]["lat"] == pytest.approx(42)
    assert body[0]["points"][0]["position"]["lng"] == pytest.approx(42)


def test_picker_add_notifies_and_returns_pin(api: Any) -> None:
    response = api.client.post(
        f"/saved-points/{api.flight.id}",
        json={
            "kind": "waypoint",
            "name": "New",
            "lat": 43,
            "lng": 43,
        },
    )
    assert response.status_code == 200
    assert response.json()["points"][-1]["id"] == str(points_of(api.flight)[-1].id)
    api.notify.assert_called_once()


def test_rename_updates_existing_object_without_moving(api: Any) -> None:
    before = api.point.x, api.point.y, api.point.altitude_ft
    assert api.client.patch(api.url, json={"name": " Renamed "}).status_code == 200
    assert api.point.name == "Renamed"
    assert (api.point.x, api.point.y, api.point.altitude_ft) == before
    assert points_of(api.flight)[0] is api.point
    api.notify.assert_called_once()


@pytest.mark.parametrize("height", [None, 456])
def test_drag_updates_position_and_available_ground_height(
    api: Any, monkeypatch: Any, height: Any
) -> None:
    monkeypatch.setattr("game.elevation.elevation_ft", lambda lat, lng: height)
    response = api.client.patch(api.url, json={"position": {"lat": 43, "lng": 43}})
    assert response.status_code == 200
    actual = Point(api.point.x, api.point.y, api.game.theater.terrain).latlng()
    assert actual.lat == pytest.approx(43)
    assert actual.lng == pytest.approx(43)
    assert api.point.altitude_ft == (100 if height is None else height)


def test_deleted_point_is_not_replaced_by_the_next_index(api: Any) -> None:
    other = SavedPoint(PointKind.WAYPOINT, "Other", 1, 2)
    points_of(api.flight).append(other)
    assert api.client.delete(api.url).status_code == 200
    assert api.client.patch(api.url, json={"name": "Wrong"}).status_code == 404
    assert api.client.delete(api.url).status_code == 404
    assert points_of(api.flight) == [other]
    assert other.name == "Other"
    api.notify.assert_called_once()


def test_delete_by_old_index_still_notifies(api: Any) -> None:
    assert api.client.delete(f"/saved-points/{api.flight.id}/0").status_code == 200
    assert points_of(api.flight) == []
    api.notify.assert_called_once()


@pytest.mark.parametrize("mode", ["cancelled", "ai", "enemy", "unknown"])
@pytest.mark.parametrize("method", ["patch", "delete"])
def test_only_active_blue_player_flights_can_edit(
    api: Any, mode: str, method: str
) -> None:
    if mode == "ai":
        api.flight.client_count = 0
    elif mode == "unknown":
        api.flights.clear()
    else:
        api.package.flights.clear()
    response = api.client.request(method, api.url, json={"name": "Wrong"})
    assert response.status_code == (404 if mode == "unknown" else 403)
    assert api.point.name == "Target"
    api.notify.assert_not_called()


def test_delete_during_elevation_lookup_cannot_apply_detached_move(
    api: Any, monkeypatch: Any
) -> None:
    before = api.point.x, api.point.y

    def lookup(lat: float, lng: float) -> int:
        points_of(api.flight).clear()
        return 321

    monkeypatch.setattr("game.elevation.elevation_ft", lookup)
    response = api.client.patch(
        api.url, json={"name": "Wrong", "position": {"lat": 43, "lng": 43}}
    )
    assert response.status_code == 404
    assert api.point.name == "Target"
    assert (api.point.x, api.point.y) == before
    api.notify.assert_not_called()


def test_invalid_move_does_not_partly_rename(api: Any) -> None:
    response = api.client.patch(
        api.url, json={"name": "Wrong", "position": {"lat": 100, "lng": 42}}
    )
    assert response.status_code == 422
    assert api.point.name == "Target"
    api.notify.assert_not_called()
