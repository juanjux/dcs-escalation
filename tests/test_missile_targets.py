"""Missile assignments preserve ownership, exact GPS points and finite magazines."""

import json
import pickle
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from dcs import Point
from dcs.ships import USS_Arleigh_Burke_IIa
from dcs.vehicles import vehicle_map
from PySide6.QtWidgets import QMessageBox
import pytest

from game import missiletargets as mt
from game.cruise_raids import plan_cruise_raids, remaining_missiles
from game.point_with_heading import PointWithHeading
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    MissileSiteGroundObject,
    ShipGroundObject,
    VehicleGroupGroundObject,
)
from game.theater.theatergroup import TheaterGroup, TheaterUnit
from game.utils import Heading
from qt_ui.widgets.map.grounddestination import GroundDestinationBridge
from qt_ui.windows.groundobject.missiletargetdialog import MissileTargetDialog
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_armor_movement_controls import controls  # noqa: F401


def populate(game: Any, obj: Any, kind: Any, identity: int) -> Any:
    at = PointWithHeading.from_point(obj.position, Heading.from_degrees(0))
    obj.groups = [
        TheaterGroup(
            identity,
            obj.name,
            at,
            [TheaterUnit(identity, obj.name, kind, at, obj)],
            obj,
        )
    ]
    obj.control_point.connected_objectives.append(obj)
    game.db.tgos.add(obj.id, obj)
    return obj


@pytest.fixture
def missiles(world: Any) -> Any:
    w = world
    w.game.cruise_missile_magazines = {}
    w.game.settings.set_plugin_option("cruisemissiles", True)
    w.game.settings.set_plugin_option("cruisemissiles.autoRaids", False)
    w.site = populate(
        w.game,
        MissileSiteGroundObject(
            "SCUD", PresetLocation("SCUD", Point(0, 0, w.game.theater.terrain)), w.a
        ),
        vehicle_map["Scud_B"],
        100,
    )
    w.target = populate(
        w.game,
        VehicleGroupGroundObject(
            "MINK",
            PresetLocation("MINK", Point(50000, 0, w.game.theater.terrain)),
            w.enemy,
            None,
        ),
        w.units[7].dcs_unit_type,
        101,
    )
    w.ship = populate(
        w.game,
        ShipGroundObject(
            "BURKE",
            PresetLocation("BURKE", Point(-50000, 0, w.game.theater.terrain)),
            w.a,
        ),
        USS_Arleigh_Burke_IIa,
        102,
    )
    return w


def test_preview_read_only_and_named_assignment_survives_pickle(missiles: Any) -> None:
    w = missiles
    before = pickle.dumps(w.game)
    _, preview = mt.preview(w.game, w.site.id, Player.BLUE, target_name="mink")
    assert preview["target_id"] == str(w.target.id) and not preview["empty_position"]
    assert pickle.dumps(w.game) == before
    mt.assign(w.game, w.site.id, Player.BLUE, target_id=w.target.id)
    copied = pickle.loads(pickle.dumps(w.game))
    assert mt.stored(copied.db.tgos.get(w.site.id)) == mt.stored(w.site)
    assert mt.aimpoint(w.game, w.site) == w.target.position
    w.target.position = Point(60000, 0, w.game.theater.terrain)
    assert mt.aimpoint(w.game, w.site) == w.target.position
    mt.clear(w.game, w.site.id, Player.BLUE)
    assert mt.stored(w.site) is None


def test_empty_gps_requires_confirmation_and_persists(missiles: Any) -> None:
    w = missiles
    at = Point(70000, 1000, w.game.theater.terrain).latlng()
    before = pickle.dumps(w.game)
    _, preview = mt.preview(w.game, w.site.id, Player.BLUE, lat=at.lat, lng=at.lng)
    assert (
        preview["requires_confirmation"]
        and "No known enemy target" in preview["warning"]
    )
    with pytest.raises(ValueError, match="confirm_empty"):
        mt.assign(w.game, w.site.id, Player.BLUE, lat=at.lat, lng=at.lng)
    assert pickle.dumps(w.game) == before
    mt.assign(
        w.game, w.site.id, Player.BLUE, lat=at.lat, lng=at.lng, confirm_empty=True
    )
    order = mt.stored(w.site)
    w.game.turn += 1
    mt.remove_invalid(w.game)
    assert mt.stored(w.site) == order
    point = mt.aimpoint(w.game, w.site)
    assert point is not None and point.x == pytest.approx(70000)


def test_gps_at_known_target_links_lifetime_and_destruction_clears(
    missiles: Any,
) -> None:
    w = missiles
    at = w.target.position.latlng()
    mt.assign(w.game, w.site.id, Player.BLUE, lat=at.lat, lng=at.lng)
    order = mt.stored(w.site)
    assert order is not None and order.target_id == w.target.id
    w.target.groups[0].units[0].alive = False
    with pytest.raises(ValueError, match="destroyed"):
        mt.aimpoint(w.game, w.site)
    mt.remove_invalid(w.game)
    assert mt.stored(w.site) is None


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"target_id": uuid4()},
        {"target_name": "unknown"},
        {"lat": 91, "lng": 0},
        {"lat": float("nan"), "lng": 0},
        {"lat": 1},
    ],
)
def test_invalid_selection_never_changes_assignment(
    missiles: Any, selection: dict[str, Any]
) -> None:
    w = missiles
    before = pickle.dumps(w.game)
    with pytest.raises(ValueError):
        mt.assign(w.game, w.site.id, Player.BLUE, **selection)
    assert pickle.dumps(w.game) == before


def test_range_ownership_and_known_target_boundaries(missiles: Any) -> None:
    w = missiles
    with pytest.raises(ValueError, match="Unknown own"):
        mt.preview(w.game, w.site.id, Player.RED, target_id=w.target.id)
    with pytest.raises(ValueError, match="Unknown or ambiguous"):
        mt.preview(w.game, w.site.id, Player.BLUE, target_id=w.target.id, allowed=set())
    with pytest.raises(ValueError, match="Unknown or ambiguous"):
        mt.preview(w.game, w.site.id, Player.BLUE, target_id=w.source.id)
    assert not mt.in_range(w.game, w.site, Point(300000, 0, w.game.theater.terrain))
    w.target.position = Point(300000, 0, w.game.theater.terrain)
    with pytest.raises(ValueError, match="engagement ranges"):
        mt.preview(w.game, w.site.id, Player.BLUE, target_id=w.target.id)
    w.target.position = Point(50000, 0, w.game.theater.terrain)
    assert mt.options(w.game, w.site.id, Player.BLUE)["targets"][0]["in_range"]
    mt.assign(w.game, w.site.id, Player.BLUE, target_id=w.target.id)
    w.enemy._coalition.player = Player.BLUE
    mt.remove_invalid(w.game)
    assert mt.stored(w.site) is None


def test_ship_assignment_launches_without_auto_raids_and_does_not_spend_stock(
    missiles: Any,
) -> None:
    w = missiles
    mt.assign(w.game, w.ship.id, Player.BLUE, target_id=w.target.id)
    before = pickle.dumps(w.game)
    raids = plan_cruise_raids(w.game)
    assert len(raids) == 1 and raids[0].target_name == "MINK" and raids[0].missiles == 6
    assert plan_cruise_raids(w.game) == raids and pickle.dumps(w.game) == before
    group = w.ship.groups[0]
    w.game.cruise_missile_magazines[group.group_name] = 2
    assert plan_cruise_raids(w.game)[0].missiles == 2
    w.game.cruise_missile_magazines[group.group_name] = 0
    assert plan_cruise_raids(w.game) == []
    assert mt.options(w.game, w.ship.id, Player.BLUE)["assignment"] is not None
    mt.clear(w.game, w.ship.id, Player.BLUE)
    assert remaining_missiles(w.game, group) == 0


def test_invalid_assignment_never_falls_back_to_automatic_ship_target(
    missiles: Any,
) -> None:
    w = missiles
    mt.assign(w.game, w.ship.id, Player.BLUE, target_id=w.target.id)
    w.game.settings.set_plugin_option("cruisemissiles.autoRaids", True)
    w.target.position = Point(1000000, 0, w.game.theater.terrain)
    assert plan_cruise_raids(w.game) == []
    w.target.groups[0].units[0].alive = False
    assert plan_cruise_raids(w.game) == []


def test_map_bridge_range_validation_and_missile_details(
    missiles: Any, controls: Any
) -> None:
    w = missiles
    model = controls.model

    def preview(position: Any) -> dict[str, Any]:
        at = Point(position.x, position.z, w.game.theater.terrain).latlng()
        return mt.preview(w.game, w.site.id, Player.BLUE, lat=at.lat, lng=at.lng)[1]

    picks: list[Any] = []
    bridge = GroundDestinationBridge(
        model,
        w.site.position,
        w.site.name,
        preview,
        picks.append,
        lambda: None,
        details={"mode": "missile", "max_range_m": 250000},
    )
    assert json.loads(bridge.initial())["mode"] == "missile"
    at = w.target.position.latlng()
    assert json.loads(bridge.preview(at.lat, at.lng))["valid"]
    far = Point(1000000, 0, w.game.theater.terrain).latlng()
    assert not json.loads(bridge.pick(far.lat, far.lng))["valid"] and not picks
    assert json.loads(bridge.pick(at.lat, at.lng))["valid"] and picks
    assert mt.stored(w.site) is None


def test_dialog_empty_target_confirmation_and_cancel(
    missiles: Any, controls: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = missiles
    dialog = MissileTargetDialog(controls.model, w.site.id)
    at = Point(70000, 1000, w.game.theater.terrain).latlng()
    dialog.coordinates.setText(f"{at.lat}, {at.lng}")
    assert (
        dialog.assign_button.isEnabled()
        and "No known enemy target" in dialog.message.text()
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No
    )
    dialog.assign()
    assert mt.stored(w.site) is None
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes
    )
    dialog.assign()
    order = mt.stored(w.site)
    assert order is not None and order.target_id is None
    dialog.deleteLater()


def test_assignment_and_generator_use_same_site_safety_fraction(missiles: Any) -> None:
    from game.data.missile_ranges import USABLE_RANGE_FRACTION

    w = missiles
    launcher = mt.launchers(w.game, w.site)[0]
    assert (
        launcher.maximum == vehicle_map["Scud_B"].threat_range * USABLE_RANGE_FRACTION
    )


def test_missile_site_generator_fires_at_assignment_not_an_automatic_target(
    missiles: Any,
) -> None:
    from dcs.task import FireAtPoint
    from tests.missiongenerator.test_missile_site_targets import _Generator

    w = missiles
    w.game.settings.generate_fire_tasks_for_missile_sites = True
    mt.assign(w.game, w.site.id, Player.BLUE, target_id=w.target.id)
    tasks: list[Any] = []
    group = SimpleNamespace(
        name="SCUD", points=[SimpleNamespace(add_task=tasks.append)]
    )
    generator = _Generator(w.site, w.game, 300000)
    generator.m = SimpleNamespace(find_group=lambda name: group)  # type: ignore[assignment]
    generator.plan_fire_mission()
    fired = [task for task in tasks if isinstance(task, FireAtPoint)]
    assert len(fired) == 1
    assert fired[0].params["x"] == w.target.position.x
    assert fired[0].params["y"] == w.target.position.y
    tasks.clear()
    w.target.position = Point(1000000, 0, w.game.theater.terrain)
    generator.plan_fire_mission()
    assert tasks == []


def test_base_and_carrier_target_panel_lists_all_launchers(
    missiles: Any, controls: Any
) -> None:
    from PySide6.QtWidgets import QPushButton
    from qt_ui.windows.groundobject.missiletargetdialog import MissileTargetPanel

    w = missiles
    panel = MissileTargetPanel(controls.model, [w.site, w.ship])
    assert len(panel.findChildren(QPushButton)) == 2
    panel.deleteLater()


@pytest.mark.parametrize("entry", ["location", "base"])
def test_map_selection_does_not_finish_the_target_dialog(
    missiles: Any, controls: Any, entry: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QDialog, QLabel, QMainWindow, QVBoxLayout, QWidget
    from qt_ui.windows.groundobject.missiletargetdialog import MissileTargetPanel
    from qt_ui.windows.groundobject.QGroundObjectMenu import QGroundObjectMenu
    from qt_ui.widgets.map.grounddestination import GroundDestinationPicker

    w = missiles
    completions: list[int] = []

    class CampaignMap(QWidget):
        def begin_ground_selection(self, bridge: GroundDestinationBridge) -> None:
            bridge.ready()

        def end_ground_selection(self, bridge: GroundDestinationBridge) -> None:
            pass

    window = QMainWindow()
    window.liberation_map = CampaignMap(window)  # type: ignore[attr-defined]
    window.setCentralWidget(window.liberation_map)  # type: ignore[attr-defined]
    parent = QDialog(window)
    panel = MissileTargetPanel(controls.model, [w.site])
    QVBoxLayout(parent).addWidget(panel)
    window.show()
    parent.show()

    def modal_exec(_: MissileTargetDialog) -> int:
        pytest.fail("Target assignment must not start a modal event loop")

    original_exec = GroundDestinationPicker.exec

    def select_on_map(picker: GroundDestinationPicker) -> QDialog.DialogCode:
        def select() -> int:
            assert not dialog.isVisible() and not parent.isVisible()
            assert window.liberation_map.isVisible()  # type: ignore[attr-defined]
            at = w.target.position.latlng()
            assert json.loads(picker.bridge.pick(at.lat, at.lng))["valid"]
            picker.reject()
            return 0

        # Keep the real picker setup, bridge validation and window restoration,
        # but do not run pending timers from unrelated tests in Qt's shared loop.
        monkeypatch.setattr(picker.loop, "exec", select)
        try:
            return original_exec(picker)
        finally:
            picker.deleteLater()
            QCoreApplication.sendPostedEvents(picker, QEvent.Type.DeferredDelete)

    monkeypatch.setattr(MissileTargetDialog, "exec", modal_exec)
    monkeypatch.setattr(GroundDestinationPicker, "exec", select_on_map)
    try:
        # Opening must return immediately: hiding a dialog running exec() to
        # borrow the map prematurely terminates that dialog's nested event loop.
        if entry == "base":
            panel.open_target(w.site.id, panel.findChildren(QLabel)[0])
        else:
            location: Any = parent
            location.game_model = controls.model
            location.ground_object = w.site
            QGroundObjectMenu._choose_missile_target(location)
        dialogs = parent.findChildren(MissileTargetDialog)
        assert len(dialogs) == 1 and dialogs[0].isVisible()
        dialog = dialogs[0]
        dialog.finished.connect(completions.append)
        for _ in range(2):
            dialog.pick()
            assert dialog.isVisible() and not completions
            assert controls.app.activeModalWidget() is None
            assert parent.isEnabled() and window.isEnabled()
            assert dialog.assign_button.isEnabled()
            assert mt.stored(w.site) is None
        dialog.assign()
        assert completions == [QDialog.DialogCode.Accepted]
        assert not dialog.isVisible()
        assert mt.stored(w.site) is not None
    finally:
        window.close()
        window.deleteLater()


def test_currenthill_ship_minimum_and_weapon_range_are_not_sam_range(
    missiles: Any,
) -> None:
    from pydcs_extensions.usamilitaryassetspack import CH_Arleigh_Burke_III

    w = missiles
    w.ship.groups[0].units[0].type = CH_Arleigh_Burke_III
    w.game.settings.set_plugin_option("cruisemissiles.playerRangeNm", 1000)
    launcher = mt.launchers(w.game, w.ship)[0]
    assert launcher.minimum == 10000 and launcher.maximum == 1600000
    assert not mt.in_range(w.game, w.ship, Point(-45000, 0, w.game.theater.terrain))
