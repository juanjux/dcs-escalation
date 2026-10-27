"""Player commands revalidate previews and synchronize the map and Qt controls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
import os
import pickle
import threading
import time
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
import pytest

from game.groundmovement.dispatch import advance_armor
from game.groundmovement.orders import DestinationKind
from game.groundmovement.report import movement_reports
from game.coordinates import CoordinateFormat, format_latlng
from dcs import Point
from game.groundmovement.settings import set_enabled
from game.server import EventStream
from game.server.dependencies import GameContext
from game.server.tgos import router
from game.server.tgos.groundmovement import commands
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from qt_ui.groundmovement import GroundMovementCommands
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.groundobject.movementdialog import ArmorMovementDialog
from tests.test_armor_movement_dispatch import prepare
from tests.test_armor_movement_planning import world  # noqa: F401


@pytest.fixture
def controls(world: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    prepare(world)
    app = QApplication.instance() or QApplication([])
    previous_signal = GameUpdateSignal.instance
    monkeypatch.setattr(GameUpdateSignal, "instance", None)
    signal = GameUpdateSignal()
    model: Any = SimpleNamespace(
        game=world.game,
        get=lambda: world.game,
        sim_controller=SimpleNamespace(game_loop=SimpleNamespace(started=False)),
    )
    service = GroundMovementCommands(model)
    model.ground_movement_commands = service
    sent: list[Any] = []
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[GameContext.require] = lambda: world.game
    api.dependency_overrides[commands] = lambda: service
    client = TestClient(api)
    executor = ThreadPoolExecutor(max_workers=1)

    def request(method: str, url: str, **kwargs: Any) -> Any:
        future = executor.submit(client.request, method, url, **kwargs)
        deadline = time.monotonic() + 15
        while not future.done() and time.monotonic() < deadline:
            app.processEvents()
            try:
                return future.result(timeout=0.002)
            except TimeoutError:
                pass
        return future.result(timeout=1)

    url = f"/tgos/{world.source.id}/ground-movement"
    body = {"unit_ids": [1, 2], "destination_kind": "base", "base_id": str(world.b.id)}
    result = SimpleNamespace(
        app=app,
        signal=signal,
        model=model,
        service=service,
        sent=sent,
        request=request,
        url=url,
        body=body,
    )
    yield result
    app.processEvents()
    executor.shutdown()
    client.close()
    GameUpdateSignal.instance = previous_signal


def confirmed_body(controls: Any) -> dict[str, Any]:
    response = controls.request("POST", controls.url + "/preview", json=controls.body)
    assert response.status_code == 200
    return {**controls.body, "preview_token": response.json()["preview_token"]}


def test_api_dispatch_reports_and_stop_even_when_plugin_disabled(
    world: Any, controls: Any
) -> None:
    changed: list[bool] = []
    controls.signal.ground_movements_changed.connect(lambda: changed.append(True))
    response = controls.request("POST", controls.url, json=confirmed_body(controls))
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "moving"
    assert report["surviving_units"] == report["original_units"] == 4
    assert report["remaining_turns"] == 1 and report["progress"] == 0
    assert len(report["towing"]) == 2
    assert len(controls.sent[0].updated_tgos) == 2 and changed
    moving_url = f"/tgos/{report['detachment_id']}/ground-movement"
    assert controls.request("GET", moving_url).json()[0] == report
    set_enabled(world.game.settings, False)
    paused = controls.request("GET", moving_url).json()[0]
    assert paused["status"] == "paused" and paused["remaining_turns"] is None
    stop_url = f"{moving_url}/{report['order_id']}/stop"
    assert controls.request("POST", stop_url).json()["status"] == "stopped"
    assert controls.request("POST", stop_url).json()["status"] == "stopped"
    assert not world.game.ground_movements.reserved_unit_ids
    assert all(
        not unit.transported_by_id
        for unit in world.game.db.tgos.get(uuid_from(report["detachment_id"])).units
    )


def uuid_from(value: str) -> Any:
    from uuid import UUID

    return UUID(value)


def test_duplicate_dispatch_cannot_duplicate_units(world: Any, controls: Any) -> None:
    body = confirmed_body(controls)
    assert controls.request("POST", controls.url, json=body).status_code == 200
    after = pickle.dumps(world.game)
    assert controls.request("POST", controls.url, json=body).status_code == 400
    assert len(world.game.ground_movements.transits) == 1
    assert pickle.dumps(world.game) == after


@pytest.mark.parametrize(
    "change",
    ["turn", "inventory", "budget", "destination", "mission", "campaign", "disabled"],
)
def test_stale_or_unavailable_commands_leave_inventory_unchanged(
    world: Any, controls: Any, change: str
) -> None:
    body = confirmed_body(controls)
    if change == "turn":
        world.game.turn += 1
    elif change == "inventory":
        world.source.groups[0].units = [
            unit for unit in world.source.units if unit.id != 7
        ]
    elif change == "budget":
        world.game.settings.set_plugin_option("groundmovement.roadMilesPerTurn", 100)
    elif change == "destination":
        world.b._coalition.player = Player.RED
    elif change == "mission":
        controls.model.sim_controller.game_loop.started = True
    elif change == "campaign":
        controls.model.game = None
    else:
        set_enabled(world.game.settings, False)
    before = pickle.dumps(world.game)
    response = controls.request("POST", controls.url, json=body)
    assert response.status_code in (400, 403, 409)
    assert pickle.dumps(world.game) == before
    assert not controls.sent


def test_api_stop_rejects_foreign_unrelated_unknown_and_in_mission(
    world: Any, controls: Any
) -> None:
    report = controls.request(
        "POST", controls.url, json=confirmed_body(controls)
    ).json()
    path = f"{controls.url}/{report['order_id']}/stop"
    controls.model.sim_controller.game_loop.started = True
    assert controls.request("POST", path).status_code == 409
    controls.model.sim_controller.game_loop.started = False
    assert controls.request("POST", f"{controls.url}/{uuid4()}/stop").status_code == 400
    order_id = uuid_from(report["order_id"])
    store = world.game.ground_movements
    store.orders[order_id] = replace(store.orders[order_id], owner=Player.RED)
    assert controls.request("POST", path).status_code == 400
    assert controls.request("GET", controls.url).json() == []


def test_command_runs_in_qt_thread(controls: Any) -> None:
    main = threading.get_ident()
    with ThreadPoolExecutor() as executor:
        future = executor.submit(controls.service.run, threading.get_ident)
        deadline = time.monotonic() + 2
        while not future.done() and time.monotonic() < deadline:
            controls.app.processEvents()
        assert future.result(timeout=1) == main


def test_cancelled_queued_command_never_runs(controls: Any) -> None:
    from concurrent.futures import Future

    action = []
    future: Future[Any] = Future()
    future.cancel()
    controls.service._execute(lambda: action.append(True), future)
    assert not action


def test_progress_arrival_casualties_and_pickle(world: Any, controls: Any) -> None:
    report = controls.request(
        "POST", controls.url, json=confirmed_body(controls)
    ).json()
    transit = next(iter(world.game.ground_movements.transits.values()))
    moving = world.game.db.tgos.get(transit.detachment_id)
    next(unit for unit in moving.units if unit.id == 5).alive = False
    assert (
        movement_reports(world.game, world.source.id, Player.BLUE)[0].surviving_units
        == 2
    )
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    progress = movement_reports(world.game, transit.detachment_id, Player.BLUE)[0]
    assert progress.status == "arrived" and progress.progress == 1
    assert progress.surviving_units == 2
    copied = pickle.loads(pickle.dumps(world.game))
    assert movement_reports(copied, transit.detachment_id, Player.BLUE)[0] == progress


def test_dialog_selection_preview_invalidation_dispatch_and_cancel(
    world: Any, controls: Any
) -> None:
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.units[1].setChecked(True)
    dialog.units[2].setChecked(True)
    dialog.kind.setCurrentIndex(dialog.kind.findData(DestinationKind.BASE))
    dialog.target.setCurrentIndex(
        next(
            index
            for index in range(dialog.target.count())
            if dialog.target.itemData(index).target_id == world.b.id
        )
    )
    dialog.calculate()
    assert dialog.preview is not None and dialog.dispatch_button.isEnabled()
    assert "Automatically added tractors" in dialog.details.text()
    assert "#5" in dialog.details.text() and "#6" in dialog.details.text()
    dialog.units[2].setChecked(False)
    assert getattr(dialog, "preview") is None
    assert not dialog.dispatch_button.isEnabled()
    dialog.calculate()
    dialog.dispatch()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert len(world.game.ground_movements.transits) == 1
    controls.app.processEvents()
    dialog.deleteLater()
    before = pickle.dumps(world.game)
    cancelled = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    cancelled.select_all(True)
    cancelled.reject()
    assert pickle.dumps(world.game) == before
    cancelled.deleteLater()


def test_dialog_external_change_and_invalid_coordinates(
    world: Any, controls: Any
) -> None:
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.units[7].setChecked(True)
    dialog.coordinates.setText("invalid")
    dialog.calculate()
    assert "valid coordinates" in dialog.details.text()
    assert dialog.details.property("movementBlocked") is True
    assert "Movement blocked" in dialog.details.text()
    assert "border-left" in dialog.details.styleSheet()
    controls.signal.ground_movements_changed.emit()
    controls.app.processEvents()
    assert (
        not dialog.preview_button.isEnabled() and not dialog.dispatch_button.isEnabled()
    )
    dialog.deleteLater()


def test_dialog_clears_blocking_banner_after_correcting_selection(
    world: Any, controls: Any
) -> None:
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.kind.setCurrentIndex(dialog.kind.findData(DestinationKind.BASE))
    dialog.calculate()
    assert dialog.details.property("movementBlocked") is True
    assert dialog.preview is None and not dialog.dispatch_button.isEnabled()
    dialog.units[7].setChecked(True)
    assert dialog.details.property("movementBlocked") is False
    assert not dialog.details.styleSheet()
    dialog.calculate()
    assert getattr(dialog, "preview") is not None and dialog.dispatch_button.isEnabled()
    assert dialog.details.property("movementBlocked") is False
    dialog.game.turn += 1
    dialog.dispatch()
    assert dialog.preview is None and not dialog.dispatch_button.isEnabled()
    assert dialog.details.property("movementBlocked") is True
    dialog.deleteLater()


def test_paused_transport_card_keeps_stop_control(world: Any, controls: Any) -> None:
    from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu

    controls.request("POST", controls.url, json=confirmed_body(controls))
    moving = next(iter(world.game.ground_movements.transits.values()))
    set_enabled(world.game.settings, False)
    window: Any = SimpleNamespace(
        game=world.game,
        ground_object=world.game.db.tgos.get(moving.detachment_id),
        _friendly=True,
        _viewer=Player.BLUE,
        _stop_movement=lambda *args: None,
    )
    card = QGroundObjectMenu._ground_transport(window)
    assert card is not None
    assert any(
        button.objectName() == "stop-ground-movement"
        for button in card.findChildren(QPushButton)
    )
    assert any("Paused" in label.text() for label in card.findChildren(QLabel))


@pytest.mark.parametrize("format", list(CoordinateFormat))
def test_dialog_can_paste_map_coordinates(
    world: Any, controls: Any, format: CoordinateFormat
) -> None:
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.units[7].setChecked(True)
    point = Point(110, 10, world.game.theater.terrain)
    controls.app.clipboard().setText(format_latlng(point.latlng(), format))
    dialog.paste_coordinates()
    dialog.calculate()
    assert dialog.preview is not None, dialog.details.text()
    assert dialog.preview.destination.kind is DestinationKind.POSITION
    # Integer-second DMS is deliberately less precise than the other formats.
    destination = dialog.preview.destination.position
    assert abs(destination.x - point.x) < 35 and abs(destination.z - point.y) < 35
    dialog.close()
    dialog.deleteLater()


def test_invalid_budget_pauses_but_does_not_prevent_stopping(
    world: Any, controls: Any
) -> None:
    report = controls.request(
        "POST", controls.url, json=confirmed_body(controls)
    ).json()
    world.game.settings.set_plugin_option("groundmovement.roadMilesPerTurn", 0)
    paused = controls.request("GET", controls.url).json()[0]
    assert paused["status"] == "paused" and "distance" in paused["pause_reason"]
    assert (
        controls.request("POST", f"{controls.url}/{report['order_id']}/stop").json()[
            "status"
        ]
        == "stopped"
    )


def test_stopped_history_is_stable_after_redispatch(world: Any, controls: Any) -> None:
    report = controls.request(
        "POST", controls.url, json=confirmed_body(controls)
    ).json()
    moving_url = f"/tgos/{report['detachment_id']}/ground-movement"
    controls.request("POST", f"{moving_url}/{report['order_id']}/stop")
    preview = controls.request(
        "POST", moving_url + "/preview", json=controls.body
    ).json()
    response = controls.request(
        "POST",
        moving_url,
        json={**controls.body, "preview_token": preview["preview_token"]},
    )
    assert response.status_code == 200
    old, new = controls.request("GET", moving_url).json()
    assert old["status"] == "stopped" and old["surviving_units"] == 4
    assert not old["towing"]
    assert new["status"] == "moving" and new["surviving_units"] == 4


def test_location_refreshes_after_commands_and_closes_on_campaign_change(
    world: Any, controls: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtGui import QIcon
    from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu
    from qt_ui.uiconstants import EVENT_ICONS

    builds: list[bool] = []
    monkeypatch.setitem(EVENT_ICONS, "capture", QIcon())
    monkeypatch.setattr(QGroundObjectMenu, "_build", lambda self: builds.append(True))
    window = QGroundObjectMenu(None, world.source, world.a, controls.model)
    window.show()
    controls.signal.ground_movements_changed.emit()
    controls.app.processEvents()
    assert len(builds) == 2
    controls.model.game = None
    controls.signal.ground_movements_changed.emit()
    controls.app.processEvents()
    assert not window.isVisible() and len(builds) == 2
    window.deleteLater()
