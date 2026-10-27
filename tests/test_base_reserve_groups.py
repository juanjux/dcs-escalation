"""Base stock becomes one counted, persistent and combat-capable detachment."""

from __future__ import annotations

from datetime import datetime
from itertools import count
from dataclasses import replace
import pickle
from types import SimpleNamespace
from typing import Any

from dcs import Point
from dcs.task import OptAlarmState, OptROE
from PySide6.QtCore import QObject, Signal
import pytest
from shapely.geometry import MultiPolygon, Point as MapPoint, box

from game.coordinates import CoordinateFormat, format_latlng
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.base import (
    available_stock,
    dispatch_base_movement,
    formation,
    preview_base_movement,
)
from game.groundmovement.dispatch import (
    advance_armor,
    dispatch_armor,
    rehome_before_capture,
    stop_armor,
)
from game.groundmovement.orders import (
    DestinationKind,
    GroundPosition as P,
    MovementSource,
)
from game.groundmovement.planning import movement_destination
from game.groundmovement.report import preview_token
from game.groundmovement.settings import set_enabled
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from qt_ui.windows.basemenu.NewUnitTransferDialog import NewUnitTransferDialog
from qt_ui.windows.groundobject.common import kind_of
from tests.test_armor_movement_dispatch import native
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401


def faction_for(player: Player) -> Any:
    return SimpleNamespace(
        ground_units={
            GroundUnitType.named(n)
            for n in ("M1A2 Abrams", "Truck Ural-375", "AAA ZU-23 Emplacement")
        }
    )


def has_path(*args: Any) -> bool:
    return True


def network_for(owner: Player) -> Any:
    return SimpleNamespace(has_path_between=has_path)


@pytest.fixture
def stock(world: Any) -> Any:
    world.a.base.commission_units(
        {world.units[7]: 4, world.units[5]: 3, world.units[1]: 2}
    )
    world.a.coalition.transfers = []
    world.b.coalition.transfers = []
    world.game.next_unit_id = count(1000).__next__
    world.game.next_group_id = count(100).__next__
    world.game.faction_for = faction_for
    world.game.transit_network_for = network_for
    return world


def send(w: Any) -> Any:
    return dispatch_base_movement(
        w.game,
        w.a.id,
        Player.BLUE,
        {w.units[7]: 1, w.units[1]: 1},
        P(80, 10),
        GameUpdateEvents(),
    )


def test_preview_is_read_only_and_adds_owned_tractors(stock: Any) -> None:
    before = pickle.dumps(stock.game)
    result = preview_base_movement(
        stock.game, stock.a.id, Player.BLUE, {stock.units[1]: 2}, P(80, 10)
    )
    assert dict(result.units) == {
        stock.units[1].variant_id: 2,
        stock.units[5].variant_id: 2,
    }
    assert dict(result.automatically_added) == {stock.units[5].variant_id: 2}
    assert len(result.manifest.towing) == 2
    assert pickle.dumps(stock.game) == before


def test_pending_transfers_cannot_spend_the_same_stock(stock: Any) -> None:
    stock.a.coalition.transfers = [
        SimpleNamespace(origin=stock.a, departed=False, units={stock.units[7]: 3})
    ]
    assert available_stock(stock.a)[stock.units[7]] == 1
    before = pickle.dumps(stock.game)
    with pytest.raises(ValueError, match="Not enough"):
        preview_base_movement(
            stock.game, stock.a.id, Player.BLUE, {stock.units[7]: 2}, P(80, 10)
        )
    assert pickle.dumps(stock.game) == before


@pytest.mark.parametrize(
    "selection", [{}, {"unknown": 1}, {7: 1}, {"tank": True}, {"tank": -1}, {"tank": 5}]
)
def test_bad_selection_does_not_consume_stock_or_ids(
    stock: Any, selection: dict[Any, Any]
) -> None:
    selected = {stock.units[7] if k == "tank" else k: v for k, v in selection.items()}
    before = pickle.dumps(stock.game)
    with pytest.raises(ValueError):
        dispatch_base_movement(
            stock.game, stock.a.id, Player.BLUE, selected, P(80, 10), GameUpdateEvents()
        )
    assert pickle.dumps(stock.game) == before


def test_no_trucks_enemy_destination_and_disabled_plugin_are_rejected(
    stock: Any,
) -> None:
    stock.a.base.armor.pop(stock.units[5])
    with pytest.raises(ValueError, match="tractors"):
        preview_base_movement(
            stock.game, stock.a.id, Player.BLUE, {stock.units[1]: 1}, P(80, 10)
        )
    with pytest.raises(PermissionError):
        preview_base_movement(
            stock.game, stock.a.id, Player.BLUE, {stock.units[7]: 1}, P(195, 10)
        )
    with pytest.raises(PermissionError):
        preview_base_movement(
            stock.game, stock.a.id, Player.RED, {stock.units[7]: 1}, P(80, 10)
        )
    set_enabled(stock.game.settings, False)
    with pytest.raises(ValueError, match="enabled"):
        preview_base_movement(
            stock.game, stock.a.id, Player.BLUE, {stock.units[7]: 1}, P(80, 10)
        )


def test_stock_debit_arrival_layout_and_combat_posture_survive_reload(
    stock: Any,
) -> None:
    initial = stock.a.base.total_armor
    transit = send(stock)
    order = stock.game.ground_movements.orders[transit.order_id]
    tgo = stock.game.db.tgos.get(transit.detachment_id)
    assert order.source_kind is MovementSource.BASE
    assert initial - stock.a.base.total_armor == 3 == len(list(tgo.units))
    assert all(u.id >= 1000 for u in tgo.units)
    assert (
        tgo.in_transit
        and tgo.reserve_from_base
        and kind_of(tgo) == "RESERVE ARMOR GROUP"
    )
    moving, _ = native(stock, transit)
    assert len(moving.units) == 2  # Loaded ZU-23 shares the Ural's identity/loss.
    assert len(moving.points) > 1
    del stock.game.iads_considerate_culling
    stock.game = pickle.loads(pickle.dumps(stock.game))
    stock.a = next(cp for cp in stock.game.theater.controlpoints if cp.id == stock.a.id)
    transit = stock.game.ground_movements.transits[transit.order_id]
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    tgo = stock.game.db.tgos.get(transit.detachment_id)
    assert transit.finished and not tgo.in_transit and len(list(tgo.units)) == 3
    assert stock.a.base.total_armor == initial - 3
    coords = {(u.position.x, u.position.y) for u in tgo.units}
    assert len(coords) == 3
    for x, z in coords:
        assert stock.game.theater.landmap.inclusion_zones.covers(MapPoint(x, z))
        assert not stock.game.theater.landmap.exclusion_zones.intersects(MapPoint(x, z))
    stationary, _ = native(stock, transit)
    assert len(stationary.units) == 3
    assert any(
        isinstance(t, OptAlarmState) and t.params["action"]["params"]["value"] == 2
        for t in stationary.points[0].tasks
    )
    assert any(
        isinstance(t, OptROE)
        and t.params["action"]["params"]["value"] == OptROE.Values.WeaponFree
        for t in stationary.points[0].tasks
    )


def test_cargo_loss_and_stop_do_not_refund_or_duplicate_stock(stock: Any) -> None:
    initial = stock.a.base.total_armor
    transit = send(stock)
    tgo = stock.game.db.tgos.get(transit.detachment_id)
    next(u for u in tgo.units if u.unit_type == stock.units[5]).alive = False
    stop_armor(stock.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    assert sum(u.alive for u in tgo.units) == 1
    assert stock.a.base.total_armor == initial - 3
    assert not tgo.in_transit
    stop_armor(stock.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    assert stock.a.base.total_armor == initial - 3


def test_finished_remote_group_is_not_deleted_with_origin_base(stock: Any) -> None:
    transit = send(stock)
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    tgo = stock.game.db.tgos.get(transit.detachment_id)
    assert transit.finished
    rehome_before_capture(stock.game, stock.a, GameUpdateEvents())
    stock.a.depopulate_uncapturable_tgos()
    assert tgo.control_point is stock.b and len(list(tgo.units)) == 3


def test_concurrent_arrivals_do_not_reserve_overlapping_parking(stock: Any) -> None:
    first = send(stock)
    second = dispatch_base_movement(
        stock.game,
        stock.a.id,
        Player.BLUE,
        {stock.units[7]: 1},
        P(80, 10),
        GameUpdateEvents(),
    )
    assert first.arrival_positions is not None
    assert second.arrival_positions is not None
    a = set(first.arrival_positions.values())
    b = set(second.arrival_positions.values())
    assert not a & b
    assert all((p.x - q.x) ** 2 + (p.z - q.z) ** 2 >= 225 for p in a for q in b)


def test_formation_checks_occupied_diagonal_corners(stock: Any) -> None:
    stock.game.theater.landmap = replace(
        stock.game.theater.landmap,
        inclusion_zones=MultiPolygon([box(584, 584, 586, 586)]),
    )
    unit = next(iter(stock.source.units))
    unit.position.x = unit.position.y = 585
    with pytest.raises(ValueError, match="Not enough safe ground"):
        formation(stock.game, P(0, 0), 1)


def test_red_stock_can_deploy_and_disabled_orders_resume(stock: Any) -> None:
    stock.a._coalition.player = stock.b._coalition.player = Player.RED
    transit = dispatch_base_movement(
        stock.game,
        stock.a.id,
        Player.RED,
        {stock.units[7]: 1},
        P(80, 10),
        GameUpdateEvents(),
    )
    initial = stock.a.base.total_armor
    set_enabled(stock.game.settings, False)
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    assert not transit.finished and transit.journey.travelled_distance == 0
    assert transit.pause_reason == "Ground Movement is disabled"
    set_enabled(stock.game.settings, True)
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    resumed = stock.game.ground_movements.transits[transit.order_id]
    assert resumed.finished and resumed.pause_reason is None
    assert stock.a.base.total_armor == initial


def test_variant_identity_is_preserved_when_delivered_back_to_stock(
    stock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    variant = replace(stock.units[7], variant_id="Reserve test variant")
    monkeypatch.setitem(GroundUnitType._by_name, variant.variant_id, variant)
    stock.a.base.commission_units({variant: 1})
    transit = dispatch_base_movement(
        stock.game, stock.a.id, Player.BLUE, {variant: 1}, P(80, 10), GameUpdateEvents()
    )
    tgo = stock.game.db.tgos.get(transit.detachment_id)
    assert next(iter(tgo.units)).unit_type is variant
    stop_armor(stock.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    destination = movement_destination(
        stock.game, Player.BLUE, DestinationKind.BASE, base_id=stock.b.id
    )
    returning = dispatch_armor(
        stock.game,
        tgo.id,
        Player.BLUE,
        [u.id for u in tgo.units],
        destination,
        GameUpdateEvents(),
    )
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    assert returning.finished and stock.b.base.armor[variant] == 1


def test_gps_preview_rejects_unsafe_formation_before_spending_stock(stock: Any) -> None:
    from shapely.geometry import MultiPolygon, box

    stock.game.theater.landmap = replace(
        stock.game.theater.landmap,
        exclusion_zones=MultiPolygon([box(50, -1000, 1000, 1000)]),
    )
    before = pickle.dumps(stock.game)
    with pytest.raises(ValueError):
        send(stock)
    assert pickle.dumps(stock.game) == before


def body(w: Any) -> dict[str, Any]:
    ll = Point(80, 10, w.game.theater.terrain).latlng()
    return {
        "units": {w.units[7].variant_id: 1, w.units[1].variant_id: 1},
        "position": {"lat": ll.lat, "lng": ll.lng},
    }


def test_api_preview_dispatch_retry_and_reports(stock: Any, controls: Any) -> None:
    url = f"/control-points/{stock.a.id}/ground-movement"
    initial = stock.a.base.total_armor
    result = controls.request("POST", url + "/preview", json=body(stock))
    assert result.status_code == 200, result.text
    preview = result.json()
    assert preview["automatically_added"] == {stock.units[5].variant_id: 1}
    assert stock.a.base.total_armor == initial
    request = {**body(stock), "preview_token": preview["preview_token"]}
    sent = controls.request("POST", url, json=request)
    assert sent.status_code == 200, sent.text
    after = pickle.dumps(stock.game)
    assert controls.request("POST", url, json=request).status_code == 409
    assert pickle.dumps(stock.game) == after
    assert len(controls.request("GET", url).json()) == 1
    assert stock.a.base.total_armor == initial - 3
    assert stock.a in controls.sent[-1].updated_control_points


@pytest.mark.parametrize(
    "change", ["stock", "capture", "mission", "campaign", "disabled"]
)
def test_api_revalidates_before_debit(stock: Any, controls: Any, change: str) -> None:
    url = f"/control-points/{stock.a.id}/ground-movement"
    request = body(stock)
    preview = controls.request("POST", url + "/preview", json=request).json()
    if change == "stock":
        stock.a.base.commit_losses({stock.units[7]: 4})
    elif change == "capture":
        stock.a._coalition.player = Player.RED
    elif change == "mission":
        controls.model.sim_controller.game_loop.started = True
    elif change == "campaign":
        controls.model.game = None
    else:
        set_enabled(stock.game.settings, False)
    before = pickle.dumps(stock.game)
    response = controls.request(
        "POST", url, json={**request, "preview_token": preview["preview_token"]}
    )
    assert response.status_code in (400, 403, 409), response.text
    assert pickle.dumps(stock.game) == before


class InventoryModel(QObject):
    inventory_changed = Signal()


def test_transfer_dialog_gps_preview_and_dispatch(stock: Any, controls: Any) -> None:
    controls.model.transfer_model = InventoryModel()
    dialog = NewUnitTransferDialog(controls.model, stock.a)
    combo = dialog.dest_panel.source_combo_box
    combo.setCurrentIndex(combo.findData(DestinationKind.POSITION))
    assert dialog.gps_mode and not dialog.dest_panel.transport_type.isEnabled()
    dialog.transfer_panel.transfers[stock.units[7]] = 1
    dialog.coordinates.setText(
        format_latlng(
            Point(80, 10, stock.game.theater.terrain).latlng(), CoordinateFormat.DDM
        )
    )
    dialog.calculate()
    assert dialog.preview is not None, dialog.details.text()
    assert dialog.submit_button.isEnabled()
    dialog.on_submit()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert stock.a.base.armor[stock.units[7]] == 3
    dialog.deleteLater()


def test_transfer_dialog_keeps_original_base_transfer(
    stock: Any, controls: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    module = importlib.import_module("qt_ui.windows.basemenu.NewUnitTransferDialog")
    controls.model.transfer_model = InventoryModel()
    controls.model.sim_controller.current_time_in_sim = datetime(2026, 1, 1)
    calls = []
    monkeypatch.setattr(
        module, "submit_transfer", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    dialog = NewUnitTransferDialog(controls.model, stock.a)
    dialog.transfer_panel.transfers[stock.units[7]] = 1
    dialog.on_transfer_quantity_changed()
    assert not dialog.gps_mode and dialog.submit_button.isEnabled()
    dialog.on_submit()
    assert len(calls) == 1 and calls[0][0][2] is stock.b
    dialog.deleteLater()


def test_transfer_dialog_invalidates_on_external_inventory_change(
    stock: Any, controls: Any
) -> None:
    controls.model.transfer_model = InventoryModel()
    dialog = NewUnitTransferDialog(controls.model, stock.a)
    combo = dialog.dest_panel.source_combo_box
    combo.setCurrentIndex(combo.findData(DestinationKind.POSITION))
    dialog.transfer_panel.transfers[stock.units[7]] = 1
    dialog.coordinates.setText(
        format_latlng(
            Point(80, 10, stock.game.theater.terrain).latlng(), CoordinateFormat.DDM
        )
    )
    dialog.calculate()
    controls.model.transfer_model.inventory_changed.emit()
    controls.app.processEvents()
    assert (
        not dialog.submit_button.isEnabled() and not dialog.preview_button.isEnabled()
    )
    dialog.on_submit()
    assert not stock.game.ground_movements.transits
    dialog.deleteLater()
