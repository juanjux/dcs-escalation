"""Early-refuel controls, route confirmation and rollback."""

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def options(monkeypatch: Any) -> Any:
    from PySide6.QtWidgets import QApplication
    from tests.test_pre_refuel import attack
    from game.ato import prerefuel
    from qt_ui.windows.mission.flight.waypoints.QPreRefuelOptions import (
        QPreRefuelOptions,
    )

    app = QApplication.instance() or QApplication([])
    flight = attack()
    flight.refuel_before_push = False
    flight.is_helo = False
    flight.state = SimpleNamespace(is_waiting_for_start=True)
    flight._flight_plan_builder = SimpleNamespace(
        existing_flight_plan=flight.flight_plan
    )
    flight.recreate_flight_plan = Mock()
    monkeypatch.setattr(
        prerefuel, "planned_tanker", lambda *_: SimpleNamespace(unit_type="KC-135")
    )
    changed = Mock()
    widget = QPreRefuelOptions(flight, changed)
    yield widget, changed
    widget.deleteLater()
    app.processEvents()


def test_cancel_leaves_route_and_option_unchanged(
    options: Any, monkeypatch: Any
) -> None:
    from PySide6.QtWidgets import QMessageBox

    widget, changed = options
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.No
    )
    widget.enabled.click()
    assert not widget.enabled.isChecked()
    assert not widget.flight.refuel_before_push
    widget.flight.recreate_flight_plan.assert_not_called()
    changed.assert_not_called()


def test_enable_and_change_time_then_reset_to_automatic(
    options: Any, monkeypatch: Any
) -> None:
    from PySide6.QtWidgets import QMessageBox

    widget, changed = options
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes
    )
    widget.enabled.click()
    assert widget.flight.refuel_before_push
    widget.flight.recreate_flight_plan.assert_called_once()
    assert widget.minutes.isEnabled()
    widget.minutes.setValue(30)
    assert widget.flight.tanking_minutes == 30
    widget.reset.click()
    assert widget.flight.tanking_minutes is None
    assert widget.minutes.value() == 9
    assert changed.call_count == 3


def test_failed_route_build_rolls_back(options: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    widget, changed = options
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "warning", Mock())
    widget.flight.recreate_flight_plan.side_effect = ValueError("bad route")
    widget.enabled.click()
    assert not widget.enabled.isChecked()
    assert not widget.flight.refuel_before_push
    changed.assert_not_called()


def test_missing_tanker_and_active_flight_disable_controls(
    options: Any, monkeypatch: Any
) -> None:
    from game.ato import prerefuel

    widget, _ = options
    monkeypatch.setattr(prerefuel, "planned_tanker", lambda *_: None)
    widget.refresh()
    assert not widget.enabled.isEnabled()
    assert not widget.minutes.isEnabled()
    widget.flight.state.is_waiting_for_start = False
    widget.refresh()
    assert not widget.enabled.isEnabled()
