"""Intel includes active GPS deployments without changing inventory ownership."""

from dataclasses import replace
import importlib
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pytest
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QDialog, QMainWindow, QVBoxLayout, QWidget

from game.groundmovement.base import preview_base_movement
from game.groundmovement.dispatch import advance_armor
from game.groundmovement.orders import DestinationKind, GroundPosition
from game.groundmovement.report import destination_label, preview_token
from game.groundmovement.settings import set_enabled
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater import Player
from game.transfers import TransferOrder
from qt_ui.models import TransferModel
from qt_ui.widgets.map.grounddestination import GroundDestinationPicker
from qt_ui.windows.basemenu.NewUnitTransferDialog import NewUnitTransferDialog
from qt_ui.windows.intel.groundmovements import GroundMovementEntry
from qt_ui.windows.intel.transfers import TransfersPane
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401
from tests.test_base_reserve_groups import stock  # noqa: F401
from tests.test_ground_destination_picker import at


class SimUpdates(QObject):
    sim_update = Signal(GameUpdateEvents)


class Pending(list[TransferOrder]):
    @property
    def pending_transfers(self) -> list[TransferOrder]:
        return self


@pytest.fixture
def intel(stock: Any, controls: Any) -> Any:
    blue, red = Pending(), Pending()
    stock.a.coalition.transfers = blue
    stock.b.coalition.transfers = blue
    stock.enemy.coalition.transfers = red
    stock.game.coalition_for = lambda player: NS(
        transfers=blue if player.is_blue else red
    )
    updates = SimUpdates()
    controls.model.sim_controller.sim_update = updates.sim_update
    model = TransferModel(controls.model)
    controls.model.transfer_model = model
    pane = TransfersPane(model)
    yield NS(pane=pane, model=model, blue=blue, red=red)
    pane.close()
    pane.deleteLater()
    controls.app.processEvents()


def dispatch(stock: Any, controls: Any) -> Any:
    stock.a.base.commission_units({stock.units[7]: 7})
    selected = {stock.units[7]: 11}
    destination = GroundPosition(80, 10)
    preview = preview_base_movement(
        stock.game, stock.a.id, Player.BLUE, selected, destination
    )
    transit = controls.service.dispatch_base(
        stock.game,
        stock.a.id,
        Player.BLUE,
        selected,
        destination,
        preview_token(stock.game, preview),
    )
    controls.app.processEvents()
    return transit


def test_gps_deployment_appears_with_group_count_coordinates_and_progress(
    stock: Any, controls: Any, intel: Any, tmp_path: Path
) -> None:
    transit = dispatch(stock, controls)
    assert intel.pane.proxy.rowCount() == 1
    index = intel.pane.proxy.index(0, 0)
    row = index.data(TransferModel.TransferRole)
    assert isinstance(row, GroundMovementEntry)
    assert row.order_id == transit.order_id
    name = stock.game.db.tgos.get(transit.detachment_id).name
    assert index.data() == f"11 units — {name}"
    destination = stock.game.ground_movements.orders[transit.order_id].destination
    assert (
        f"{stock.a.name} → GPS {destination_label(stock.game, destination)}"
        in row.description
    )
    assert "Moving" in row.description and "ETA" in row.description
    assert row.description in index.data(Qt.ItemDataRole.ToolTipRole)
    assert stock.a.base.armor.get(stock.units[7], 0) == 0
    # The Windows offscreen plugin has no system font database.
    font_id = QFontDatabase.addApplicationFont("resources/fonts/Inconsolata.otf")
    assert font_id >= 0
    try:
        intel.pane.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 11))
        intel.pane.resize(1000, 420)
        intel.pane.show()
        controls.app.processEvents()
        assert intel.pane.grab().save(str(tmp_path / "intel-gps-transfer.png"))
    finally:
        QFontDatabase.removeApplicationFont(font_id)
    for term in (name, "GPS", destination_label(stock.game, destination)):
        intel.pane.proxy.setFilterFixedString(term)
        assert intel.pane.proxy.rowCount() == 1
    intel.pane.proxy.setFilterFixedString("No such group")
    assert intel.pane.proxy.rowCount() == 0


def test_regular_transfers_keep_their_cancel_mapping_next_to_gps_movements(
    stock: Any, controls: Any, intel: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch(stock, controls)
    transfer = TransferOrder(stock.a, stock.b, {stock.units[7]: 1}, Player.BLUE)
    intel.blue.pending_transfers.append(transfer)
    intel.model.on_sim_update(GameUpdateEvents())
    assert intel.pane.proxy.rowCount() == 2
    assert intel.pane.proxy.index(0, 0).data(TransferModel.TransferRole) is transfer
    canceled = []
    monkeypatch.setattr(
        intel.model,
        "cancel_transfer_at_index",
        lambda index: canceled.append(index.row()),
    )
    intel.pane.view.setCurrentIndex(intel.pane.proxy.index(0, 0))
    intel.pane.cancel_selected()
    assert canceled == [0]


def test_paused_deployments_can_be_stopped_without_returning_units_to_stock(
    stock: Any, controls: Any, intel: Any
) -> None:
    transit = dispatch(stock, controls)
    set_enabled(stock.game.settings, False)
    controls.signal.ground_movements_changed.emit()
    controls.app.processEvents()
    index = intel.pane.proxy.index(0, 0)
    assert "Paused" in index.data(TransferModel.TransferRole).description
    intel.pane.view.setCurrentIndex(index)
    assert intel.pane.cancel.text() == "Stop selected movement"
    intel.pane.cancel_selected()
    assert transit.finished
    assert intel.pane.proxy.rowCount() == 0
    assert stock.a.base.armor.get(stock.units[7], 0) == 0
    assert (
        sum(u.alive for u in stock.game.db.tgos.get(transit.detachment_id).units) == 11
    )


def test_arrived_movements_leave_the_pending_view_but_keep_the_group(
    stock: Any, controls: Any, intel: Any
) -> None:
    transit = dispatch(stock, controls)
    stock.game.turn += 1
    advance_armor(stock.game, GameUpdateEvents())
    intel.model.on_sim_update(GameUpdateEvents())
    assert transit.finished
    assert intel.pane.proxy.rowCount() == 0
    assert len(list(stock.game.db.tgos.get(transit.detachment_id).units)) == 11


def test_surviving_count_updates_without_hiding_original_manifest(
    stock: Any, controls: Any, intel: Any
) -> None:
    transit = dispatch(stock, controls)
    units = list(stock.game.db.tgos.get(transit.detachment_id).units)
    units[0].alive = units[1].alive = False
    controls.signal.ground_movements_changed.emit()
    controls.app.processEvents()
    assert intel.pane.proxy.index(0, 0).data().startswith("9/11 units")
    controls.model.game = None
    intel.model.sync_game_and_visibility()
    assert intel.pane.proxy.rowCount() == 0


def test_movement_stop_is_rejected_during_a_mission(
    stock: Any, controls: Any, intel: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    transit = dispatch(stock, controls)
    controls.model.sim_controller.game_loop.started = True
    errors = []
    monkeypatch.setattr(
        "qt_ui.windows.intel.transfers.QMessageBox.warning",
        lambda parent, title, text: errors.append(text),
    )
    intel.pane.view.setCurrentIndex(intel.pane.proxy.index(0, 0))
    intel.pane.cancel_selected()
    assert not transit.finished
    assert errors and "during a mission" in errors[0]


def test_red_movements_follow_enemy_management_visibility_and_cannot_be_stopped(
    stock: Any, controls: Any, intel: Any
) -> None:
    transit = dispatch(stock, controls)
    order = stock.game.ground_movements.orders[transit.order_id]
    stock.game.ground_movements.orders[order.id] = replace(order, owner=Player.RED)
    intel.model.sync_game_and_visibility()
    intel.pane.show_side(Player.RED)
    assert intel.pane.proxy.rowCount() == 0
    stock.game.settings.enable_enemy_buy_sell = True
    intel.model.sync_game_and_visibility()
    assert intel.pane.proxy.rowCount() == 1
    intel.pane.view.setCurrentIndex(intel.pane.proxy.index(0, 0))
    assert not intel.pane.cancel.isEnabled()
    intel.pane.cancel_selected()
    assert not transit.finished
    stock.game.settings.enable_enemy_buy_sell = False
    intel.model.sync_game_and_visibility()
    assert intel.pane.proxy.rowCount() == 0


def test_base_dialog_opened_from_campaign_can_choose_a_gps_destination_on_its_map(
    stock: Any, controls: Any, intel: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("qt_ui.windows.QLiberationWindow")

    class BaseDialog(QDialog):
        def __init__(self, parent: QWidget, cp: Any, model: Any):
            super().__init__(parent)

    monkeypatch.setattr(module, "QBaseMenu2", BaseDialog)
    window: Any = QMainWindow()
    window.game_model = controls.model
    central = QWidget(window)
    window.setCentralWidget(central)
    window.liberation_map = QWidget(central)
    QVBoxLayout(central).addWidget(window.liberation_map)
    module.QLiberationWindow.open_control_point_info_dialog(window, stock.a)
    base = window._cp_dialog
    assert base.parentWidget() is window
    assert base.isWindow()
    dialog = NewUnitTransferDialog(controls.model, stock.a, parent=base)
    combo = dialog.dest_panel.source_combo_box
    combo.setCurrentIndex(combo.findData(DestinationKind.POSITION))
    dialog.transfer_panel.transfers[stock.units[7]] = 1
    picked = []

    def choose(picker: GroundDestinationPicker) -> QDialog.DialogCode:
        assert picker.window is window and picker.owner is dialog
        picked.append(picker)
        picker.selected = at(stock)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(GroundDestinationPicker, "exec", choose)
    try:
        dialog.choose_on_map()
        assert len(picked) == 1
        assert dialog.preview is not None, dialog.details.text()
        assert dialog.submit_button.isEnabled()
        assert dialog.coordinates.text()
        assert not stock.game.ground_movements.transits
    finally:
        dialog.close()
        base.close()
        window.close()
        window.deleteLater()
