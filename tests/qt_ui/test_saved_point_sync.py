"""Map edits refresh the open aircraft dialog without losing user context."""

import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from dcs.terrain import Caucasus
from PySide6.QtWidgets import QApplication

from game.ato.savedpoints import PointKind, SavedPoint
from game.server.eventstream.models import GameUpdateEventsJs
from game.server.savedpoints.notifications import publish_points_changed
from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.playable.dialog import PlayableAircraftDialog
from qt_ui.windows.playable.rows import NAME


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
