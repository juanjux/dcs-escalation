"""Site repairs publish once and do not rebuild closed location windows."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
from qt_ui.windows.groundobject import QGroundObjectMenu as menu


def _drain(app: Any) -> None:
    # Deliver queued signals and then their coalesced zero-interval timer.
    for _ in range(3):
        app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def location(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    app = QApplication.instance() or QApplication([])
    monkeypatch.setitem(menu.EVENT_ICONS, "capture", QIcon())
    monkeypatch.setattr(GameUpdateSignal, "instance", None)
    signal = GameUpdateSignal()
    updates: list[Any] = []
    signal.gameupdated.connect(updates.append)
    events: list[Any] = []
    monkeypatch.setattr(menu.EventStream, "put_nowait", events.append)
    builds: list[Any] = []
    monkeypatch.setattr(
        menu.QGroundObjectMenu, "_build", lambda window: builds.append(window)
    )
    game = SimpleNamespace(
        blue=SimpleNamespace(budget=100),
        settings=SimpleNamespace(ground_object_repair_turns=2, building_repair_turns=2),
        theater=SimpleNamespace(iads_network=SimpleNamespace(update_tgo=Mock())),
        ato_for=lambda **kwargs: SimpleNamespace(packages=[]),
        get_destroyed_units=lambda: [],
    )
    units = [
        SimpleNamespace(
            unit_name=f"unit-{index}",
            alive=False,
            repairable=True,
            repair_turns_remaining=None,
            unit_type=SimpleNamespace(price=2),
        )
        for index in range(4)
    ]
    cp: Any = SimpleNamespace(name="Base")
    site = Mock(
        spec=menu.BuildingGroundObject,
        obj_name="Site",
        control_point=cp,
        units=units,
        statics=units,
    )
    site.repair_cost.return_value = 2
    model: Any = SimpleNamespace(game=game)
    windows = []

    def create() -> Any:
        window = menu.QGroundObjectMenu(None, site, cp, model)
        windows.append(window)
        window.show()
        _drain(app)
        return window

    window = create()
    builds.clear()
    yield SimpleNamespace(
        app=app,
        signal=signal,
        updates=updates,
        events=events,
        builds=builds,
        game=game,
        units=units,
        cp=cp,
        site=site,
        model=model,
        window=window,
        create=create,
    )
    for window in windows:
        if shiboken6.isValid(window):
            window.close()
    _drain(app)


@pytest.mark.parametrize("building", [False, True])
@pytest.mark.parametrize("turns", [0, 2])
def test_individual_repair_publishes_and_rebuilds_once(
    location: Any, building: bool, turns: int
) -> None:
    state = location
    state.game.settings.ground_object_repair_turns = turns
    state.game.settings.building_repair_turns = turns
    repair = state.window._repair_building if building else state.window._repair_unit
    repair(state.units[0], 2)
    _drain(state.app)

    assert state.game.blue.budget == 98
    assert state.units[0].alive == (turns == 0)
    assert state.units[0].repair_turns_remaining == (turns or None)
    assert state.updates == [state.game]
    assert len(state.events) == 1
    assert state.site in state.events[0].updated_tgos
    state.game.theater.iads_network.update_tgo.assert_called_once_with(
        state.site, state.events[0]
    )
    assert state.builds == [state.window]


@pytest.mark.parametrize("building", [False, True])
@pytest.mark.parametrize("budget, count", [(100, 4), (5, 2)])
def test_bulk_repair_publishes_once_for_the_whole_affordable_batch(
    location: Any, building: bool, budget: int, count: int
) -> None:
    state = location
    state.game.blue.budget = budget
    repair = (
        state.window._repair_all_buildings if building else state.window._repair_all
    )
    repair()
    _drain(state.app)

    assert state.game.blue.budget == budget - count * 2
    assert sum(unit.repair_turns_remaining == 2 for unit in state.units) == count
    assert state.updates == [state.game]
    assert len(state.events) == 1
    assert state.builds == [state.window]


def test_movement_and_game_notifications_share_one_refresh(location: Any) -> None:
    state = location
    new_cp = SimpleNamespace(name="Destination")
    state.site.control_point = new_cp
    state.signal.ground_movements_changed.emit()
    state.signal.updateGame(state.game)
    state.signal.ground_movements_changed.emit()
    _drain(state.app)

    assert state.window.cp is new_cp
    assert state.builds == [state.window]


def test_hidden_window_refreshes_only_when_shown_again(location: Any) -> None:
    state = location
    state.window.hide()
    state.signal.updateGame(state.game)
    _drain(state.app)
    assert state.builds == []
    state.window.show()
    _drain(state.app)
    assert state.builds == [state.window]


def test_closed_windows_are_deleted_and_do_not_rebuild(location: Any) -> None:
    state = location
    closed = [state.create() for _ in range(5)]
    state.builds.clear()
    for window in closed:
        window.close()
    # Queue an update before deferred deletion, as well as after it.
    state.signal.updateGame(state.game)
    _drain(state.app)
    assert all(not shiboken6.isValid(window) for window in closed)
    assert state.builds == [state.window]
    state.builds.clear()
    state.signal.updateGame(state.game)
    _drain(state.app)
    assert state.builds == [state.window]


@pytest.mark.parametrize("replacement", [None, SimpleNamespace()])
def test_campaign_unload_or_replacement_closes_the_window(
    location: Any, replacement: Any
) -> None:
    state = location
    state.model.game = replacement
    state.signal.updateGame(replacement)
    _drain(state.app)
    assert not shiboken6.isValid(state.window)
    assert state.builds == []


def test_campaign_change_between_notification_and_timer_is_safe(location: Any) -> None:
    state = location
    state.window._refresh_movement()
    state.model.game = None
    _drain(state.app)
    assert not shiboken6.isValid(state.window)
    assert state.builds == []


def test_repair_still_replans_enemy_packages_targeting_the_site(location: Any) -> None:
    state = location
    state.game.ato_for = lambda **kwargs: SimpleNamespace(
        packages=[SimpleNamespace(target=state.site)]
    )
    state.game.initialize_turn = Mock()
    state.window._repair_unit(state.units[0], 2)
    _drain(state.app)

    state.game.initialize_turn.assert_called_once_with(
        state.events[0], for_red=True, for_blue=False
    )
    assert state.updates == [state.game]
    assert state.builds == [state.window]
