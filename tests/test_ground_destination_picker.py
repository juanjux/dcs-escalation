"""Map previews are read-only and picking never bypasses route validation."""

import json
import math
import pickle
from typing import Any

from dcs import Point
from dcs.mapping import LatLng
from PySide6.QtWidgets import QDialog
import pytest

from game.groundmovement.base import preview_base_movement
from game.groundmovement.orders import DestinationKind, GroundPosition
from game.groundmovement.planning import movement_destination, preview_armor_movement
from game.theater.player import Player
from qt_ui.widgets.map.grounddestination import GroundDestinationBridge
from qt_ui.windows.groundobject.movementdialog import ArmorMovementDialog
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_base_reserve_groups import stock, InventoryModel  # noqa: F401


@pytest.fixture
def bridge(world: Any, controls: Any) -> Any:
    chosen: list[LatLng] = []
    canceled: list[bool] = []

    def preview(position: GroundPosition) -> Any:
        return preview_armor_movement(
            world.game,
            world.source.id,
            Player.BLUE,
            [7],
            movement_destination(
                world.game, Player.BLUE, DestinationKind.POSITION, position=position
            ),
        )

    return (
        GroundDestinationBridge(
            controls.model,
            world.source.position,
            world.source.name,
            preview,
            chosen.append,
            lambda: canceled.append(True),
        ),
        chosen,
        canceled,
    )


def at(world: Any, x: float = 80, z: float = 10) -> LatLng:
    return Point(x, z, world.game.theater.terrain).latlng()


def test_initial_and_hover_are_read_only(
    world: Any, controls: Any, bridge: Any
) -> None:
    backend, chosen, _ = bridge
    before = pickle.dumps(world.game)
    assert json.loads(backend.initial())["name"] == world.source.name
    point = at(world)
    result = json.loads(backend.preview(point.lat, point.lng))
    assert result["valid"] and result["arrival_in_turns"] == 1
    assert result["road_distance_m"] > 0 and result["segments"]
    assert any(not s["on_road"] for s in result["segments"])
    assert not chosen and not controls.sent and pickle.dumps(world.game) == before


@pytest.mark.parametrize(
    "change", ["turn", "campaign", "mission", "enemy", "disabled", "units"]
)
def test_click_revalidates_after_a_valid_hover(
    world: Any, controls: Any, bridge: Any, change: str
) -> None:
    backend, chosen, _ = bridge
    point = at(world)
    assert json.loads(backend.preview(point.lat, point.lng))["valid"]
    if change == "turn":
        world.game.turn += 1
    elif change == "campaign":
        controls.model.game = None
    elif change == "mission":
        controls.model.sim_controller.game_loop.started = True
    elif change == "enemy":
        world.b._coalition.player = Player.RED
    elif change == "disabled":
        world.game.settings.set_plugin_option("groundmovement", False)
    else:
        world.source.groups[0].units = [u for u in world.source.units if u.id != 7]
    before = pickle.dumps(world.game)
    assert not json.loads(backend.pick(point.lat, point.lng))["valid"]
    assert not chosen and not controls.sent and pickle.dumps(world.game) == before


def test_click_only_selects_and_repeated_click_cannot_select_twice(
    world: Any, controls: Any, bridge: Any
) -> None:
    backend, chosen, _ = bridge
    point = at(world)
    before = pickle.dumps(world.game)
    assert json.loads(backend.pick(point.lat, point.lng))["valid"]
    assert len(chosen) == 1 and chosen[0] == point
    assert not json.loads(backend.pick(point.lat, point.lng))["valid"]
    assert not controls.sent and pickle.dumps(world.game) == before


@pytest.mark.parametrize(
    "latitude,longitude", [(math.nan, 0), (0, math.inf), (91, 0), (0, -181)]
)
def test_invalid_coordinates_never_reach_planner(
    bridge: Any, latitude: float, longitude: float
) -> None:
    backend, chosen, _ = bridge
    assert not json.loads(backend.preview(latitude, longitude))["valid"]
    assert not chosen


def test_cancel_discards_selection(bridge: Any, world: Any) -> None:
    backend, chosen, canceled = bridge
    backend.dismiss()
    point = at(world)
    assert canceled == [True] and not chosen
    assert not json.loads(backend.pick(point.lat, point.lng))["valid"]


def test_base_stock_uses_the_same_picker_without_debit(
    stock: Any, controls: Any
) -> None:
    point = at(stock)
    before = pickle.dumps(stock.game)
    backend = GroundDestinationBridge(
        controls.model,
        stock.a.position,
        stock.a.name,
        lambda position: preview_base_movement(
            stock.game, stock.a.id, Player.BLUE, {stock.units[7]: 1}, position
        ),
        lambda _: None,
        lambda: None,
    )
    assert json.loads(backend.preview(point.lat, point.lng))["valid"]
    assert pickle.dumps(stock.game) == before


def fake_picker(position: LatLng | None) -> Any:
    class Picker:
        selected = position

        def __init__(
            self, model: Any, origin: Any, name: str, preview: Any, parent: Any
        ) -> None:
            if position is not None:
                point = Point.from_latlng(position, model.game.theater.terrain)
                preview(GroundPosition(point.x, point.y))

        def exec(self) -> int:
            return (
                QDialog.DialogCode.Accepted
                if position is not None
                else QDialog.DialogCode.Rejected
            )

        def deleteLater(self) -> None:
            pass

    return Picker


@pytest.mark.parametrize("accepted", [True, False])
def test_armor_dialog_returns_to_preview_without_dispatch(
    world: Any, controls: Any, monkeypatch: pytest.MonkeyPatch, accepted: bool
) -> None:
    monkeypatch.setattr(
        "qt_ui.windows.groundobject.movementdialog.GroundDestinationDialog",
        fake_picker(at(world) if accepted else None),
    )
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.units[7].setChecked(True)
    before = pickle.dumps(world.game)
    dialog.choose_on_map()
    assert (dialog.preview is not None) is accepted
    assert dialog.dispatch_button.isEnabled() is accepted
    assert not controls.sent and pickle.dumps(world.game) == before
    dialog.deleteLater()


def test_base_dialog_returns_to_preview_without_dispatch(
    stock: Any, controls: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qt_ui.windows.basemenu.NewUnitTransferDialog import NewUnitTransferDialog

    controls.model.transfer_model = InventoryModel()
    monkeypatch.setattr(
        "qt_ui.widgets.map.grounddestination.GroundDestinationDialog",
        fake_picker(at(stock)),
    )
    dialog = NewUnitTransferDialog(controls.model, stock.a)
    combo = dialog.dest_panel.source_combo_box
    combo.setCurrentIndex(combo.findData(DestinationKind.POSITION))
    dialog.transfer_panel.transfers[stock.units[7]] = 1
    before = pickle.dumps(stock.game)
    dialog.choose_on_map()
    assert dialog.preview is not None and dialog.submit_button.isEnabled()
    assert not controls.sent and pickle.dumps(stock.game) == before
    dialog.deleteLater()


def test_empty_selection_does_not_open_map(
    world: Any, controls: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: Any) -> None:
        pytest.fail("The map must not open without a selection")

    monkeypatch.setattr(
        "qt_ui.windows.groundobject.movementdialog.GroundDestinationDialog", unexpected
    )
    dialog = ArmorMovementDialog(controls.model, world.source.id, Player.BLUE)
    dialog.choose_on_map()
    assert "Select units" in dialog.details.text()
    dialog.deleteLater()
