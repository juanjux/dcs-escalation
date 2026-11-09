"""Map edits refresh the open aircraft dialog without losing user context."""

import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from dcs.terrain import Caucasus
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog, QLabel

from game.ato.savedpoints import PointKind, SavedPoint
from game.server.eventstream.models import GameUpdateEventsJs
from game.server.savedpoints.notifications import publish_points_changed
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.playable.dialog import PlayableAircraftDialog
from qt_ui.windows.playable.rows import ELEVATION, NAME


@pytest.fixture
def dialog(monkeypatch: pytest.MonkeyPatch) -> Any:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    previous_signal = GameUpdateSignal.instance
    signal = GameUpdateSignal()
    monkeypatch.setattr(GameUpdateSignal, "instance", signal)
    point = SavedPoint(PointKind.WAYPOINT, "TARGET", 0, 0, 100)
    member = SimpleNamespace(is_player=True, pilot=SimpleNamespace(name="Pilot"))
    flight = SimpleNamespace(
        iter_members=lambda: iter([member]),
        client_count=1,
        custom_name="Hawg",
        unit_type=SimpleNamespace(
            dcs_unit_type=SimpleNamespace(id="A-10C_2"),
            display_name="A-10C II",
            helicopter=False,
        ),
        squadron=SimpleNamespace(
            nickname="Hawg", name="Squadron", saved_points=[point]
        ),
        flight_type=SimpleNamespace(value="Strike"),
        package=None,
    )
    game = SimpleNamespace(
        blue=SimpleNamespace(
            ato=SimpleNamespace(packages=[SimpleNamespace(flights=[flight])])
        ),
        settings=SimpleNamespace(coordinate_format=None),
        theater=SimpleNamespace(terrain=Caucasus()),
        turn=1,
        conditions=SimpleNamespace(start_time=datetime(2026, 1, 1)),
    )
    flight.squadron.coalition = game.blue
    game.blue.air_wing = SimpleNamespace(iter_squadrons=lambda: iter([flight.squadron]))
    send = Mock()
    monkeypatch.setattr(
        "game.server.savedpoints.notifications.EventStream.put_nowait", send
    )
    window = PlayableAircraftDialog(SimpleNamespace(game=game))
    window.points_view.setCurrentIndex(window.points_model.index(1, NAME))
    yield SimpleNamespace(app=app, window=window, point=point, flight=flight, send=send)
    window.close()
    window.deleteLater()
    app.processEvents()
    GameUpdateSignal.instance = previous_signal


def test_map_edits_refresh_points_keep_selection_and_notes(dialog: Any) -> None:
    window = dialog.window
    selected = window.selected
    editor = window.notes.editors[0]
    editor.setPlainText("Checklist in progress")
    dialog.point.name = "BRIDGE"
    dialog.point.altitude_ft = 420
    publish_points_changed()
    dialog.app.processEvents()
    assert window.selected is selected
    assert window.current_point().point is dialog.point
    assert window.notes.editors[0] is editor
    assert editor.toPlainText() == "Checklist in progress"
    assert "BRIDGE" in window.points_model.index(1, NAME).data()
    assert window.current_point().point.altitude_ft == 420
    event = dialog.send.call_args.args[0]
    assert GameUpdateEventsJs.from_events(event, None).saved_points_updated


def test_map_deletion_refreshes_the_open_list(dialog: Any) -> None:
    dialog.flight.squadron.saved_points.clear()
    publish_points_changed()
    dialog.app.processEvents()
    assert dialog.window.current_point() is None
    assert dialog.window.selected.total_used == 0
    assert not dialog.window.copy_all.isEnabled()


def test_switch_player_to_another_aircraft_keeps_global_points(dialog: Any) -> None:
    window = dialog.window
    original = dialog.flight
    original.client_count = 0
    replacement = SimpleNamespace(**original.__dict__)
    replacement.client_count = 1
    replacement.squadron = SimpleNamespace(
        nickname="Hornet", name="Other squadron", coalition=original.squadron.coalition
    )
    replacement.unit_type = SimpleNamespace(
        dcs_unit_type=SimpleNamespace(id="FA-18C_hornet"),
        display_name="F/A-18C",
        helicopter=False,
    )
    window.game.blue.ato.packages[0].flights.append(replacement)
    window.reload()
    assert window.selected.flight is replacement
    assert window.selected.points == [dialog.point]
    assert "TARGET" in window.points_model.index(1, NAME).data()
    window.game.blue.ato.packages.clear()
    window.reload()
    assert window.selected is None
    window.game.blue.ato.packages.append(SimpleNamespace(flights=[replacement]))
    window.reload()
    restored = getattr(window, "selected")
    assert restored is not None
    assert restored.points[0].id == dialog.point.id


@pytest.mark.parametrize("remove_flight", [False, True])
def test_global_points_remain_visible_without_player_seats(
    dialog: Any, remove_flight: bool
) -> None:
    window = dialog.window
    if remove_flight:
        window.game.blue.ato.packages.clear()
    else:
        dialog.flight.client_count = 0
    window.reload()
    assert window.selected is None
    assert window.saved_points == [dialog.point]
    assert "TARGET" in window.points_model.index(1, NAME).data()
    assert window.points_model.index(0, NAME).data() == "WAYPOINTS     1 saved"
    assert window.copy_all.isEnabled()
    assert window.add.isEnabled()
    labels = [label.text() for label in window.headline.findChildren(QLabel)]
    assert "1" in labels and "  saved points" in labels


def test_global_points_are_loaded_when_opening_without_any_flights(dialog: Any) -> None:
    game = dialog.window.game
    game.blue.ato.packages.clear()
    game.blue.saved_points.clear()
    game.blue.air_wing.iter_squadrons = lambda: iter(
        [SimpleNamespace(saved_points=[dialog.point])]
    )
    window = PlayableAircraftDialog(SimpleNamespace(game=game))
    try:
        assert window.selected is None
        assert "TARGET" in window.points_model.index(1, NAME).data()
        assert window.saved_points[0].id == dialog.point.id
    finally:
        window.close()
        window.deleteLater()


def test_global_points_can_be_edited_copied_pasted_and_deleted_without_flights(
    dialog: Any,
) -> None:
    window = dialog.window
    window.game.blue.ato.packages.clear()
    window.reload()
    index = window.points_model.index(1, NAME)
    assert window.points_model.setData(index, "GLOBAL")
    assert window.points_model.setData(window.points_model.index(1, ELEVATION), "1234")
    assert dialog.point.name == "GLOBAL" and dialog.point.altitude_ft == 1234
    window.points_view.setCurrentIndex(index)
    window.copy_coordinates()
    assert QApplication.clipboard().text() == window._coordinates(dialog.point)
    assert window.paste.isEnabled()
    window.copy_everything()
    window.paste_everything()
    assert len(window.saved_points) == 2
    copied = window.saved_points[1]
    assert copied == dialog.point and copied is not dialog.point
    assert copied.id != dialog.point.id
    window.points_view.setCurrentIndex(window.points_model.index(1, NAME))
    window.delete_current()
    assert len(window.saved_points) == 1 and window.saved_points[0] is copied
    assert window.selected is None
    assert dialog.send.call_args.args[0].saved_points_updated


def test_add_global_point_without_a_selected_aircraft(
    dialog: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dcs.mapping import LatLng
    from qt_ui.windows.playable import dialog as module

    window = dialog.window
    window.game.blue.ato.packages.clear()
    window.reload()
    asked = Mock(
        return_value=SimpleNamespace(
            exec=lambda: QDialog.DialogCode.Accepted,
            latlng=LatLng(43, 44),
            name=SimpleNamespace(text=lambda: "GLOBAL"),
            altitude_ft=1200,
        )
    )
    monkeypatch.setattr(module, "NewPoint", asked)
    window.add.click()
    asked.assert_called_once_with(None, window)
    assert len(window.saved_points) == 2
    saved = window.saved_points[-1]
    assert saved.name == "GLOBAL" and saved.altitude_ft == 1200
    assert saved.kind is PointKind.WAYPOINT
    assert "GLOBAL" in window.points_model.index(2, NAME).data()
    assert dialog.send.call_args.args[0].saved_points_updated


def test_map_edits_and_stale_selections_are_safe_without_flights(dialog: Any) -> None:
    window = dialog.window
    window.game.blue.ato.packages.clear()
    window.reload()
    window.points_view.setCurrentIndex(window.points_model.index(1, NAME))
    dialog.point.name = "MAP EDIT"
    publish_points_changed()
    dialog.app.processEvents()
    assert window.current_point().point is dialog.point
    assert "MAP EDIT" in window.points_model.index(1, NAME).data()
    window.show_current_on_map()
    assert dialog.send.call_args.args[0].fly_to is not None
    other = SavedPoint(PointKind.MARKPOINT, "OTHER", 1, 1)
    window.saved_points[:] = [other]
    assert not window.points_model.setData(window.points_model.index(1, NAME), "WRONG")
    window.delete_current()
    assert window.saved_points == [other] and other.name == "OTHER"
    assert window.points_model.index(0, NAME).data() == "MARKPOINTS     1 saved"


def test_qt_rename_and_delete_publish_map_refresh(dialog: Any) -> None:
    window = dialog.window
    assert window.points_model.setData(window.points_model.index(1, NAME), "RENAMED")
    assert dialog.point.name == "RENAMED"
    assert dialog.send.call_args.args[0].saved_points_updated
    dialog.app.processEvents()
    window.delete_current()
    assert dialog.flight.squadron.saved_points == []
    assert dialog.send.call_count == 2


def test_stale_qt_selection_does_not_delete_or_edit_the_next_point(dialog: Any) -> None:
    other = SavedPoint(PointKind.WAYPOINT, "OTHER", 1, 1)
    dialog.flight.squadron.saved_points[:] = [other]
    # The map deletion has happened, but Qt has not handled its queued refresh.
    window = dialog.window
    assert not window.points_model.setData(window.points_model.index(1, NAME), "WRONG")
    window.delete_current()
    assert dialog.flight.squadron.saved_points == [other]
    assert other.name == "OTHER"


def test_drawing_map_refresh_and_qt_delete_preserve_aircraft_selection(
    dialog: Any,
) -> None:
    from game.ato.savedpoints import SavedDrawing, drawings_of

    drawing = SavedDrawing("ZONE", [(0, 0), (100, 100)])
    drawings_of(dialog.flight).append(drawing)
    identical = SavedDrawing("ZONE", [(0, 0), (100, 100)])
    drawings_of(dialog.flight).append(identical)
    selected = dialog.window.selected
    publish_points_changed()
    dialog.app.processEvents()
    pane = dialog.window.drawings
    assert pane.list.count() == 2
    pane.list.setCurrentRow(0)
    drawing.name = "BRIDGE"
    publish_points_changed()
    dialog.app.processEvents()
    assert pane._selected() is drawing
    assert "BRIDGE" in pane.list.currentItem().text()
    identical.name = "BRIDGE"
    pane.refresh()
    pane.list.setCurrentRow(1)
    pane.delete_current()
    assert len(drawings_of(dialog.flight)) == 1
    assert drawings_of(dialog.flight)[0] is drawing
    assert dialog.window.selected is selected
    assert dialog.send.call_args.args[0].saved_points_updated
