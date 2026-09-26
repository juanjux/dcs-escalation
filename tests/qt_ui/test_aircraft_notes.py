"""Regression tests for a standalone UI feature."""

from __future__ import annotations
import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app() -> Any:
    return QApplication.instance() or QApplication([])


import pickle
from game.ato.aircraftnotes import notes_for_flight
from game.squadrons.pilot import Pilot, PilotStatus
from qt_ui.windows.playable.model import Aircraft
from qt_ui.windows.playable.notes import AircraftNotesPane


def flight(*pilots: Pilot, kind: str = "FA-18C_hornet") -> Any:
    return SimpleNamespace(
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=kind)),
        iter_members=lambda: iter(
            SimpleNamespace(is_player=True, pilot=p) for p in pilots
        ),
    )


def test_notes_follow_pilot_airframe_and_survive_save(app: Any) -> None:
    first, second = Pilot("One", player=True), Pilot("Two", player=True)
    pane = AircraftNotesPane()
    pane.show_aircraft(Aircraft(flight(first, second)))
    pane.editor.setPlainText("Hornet checklist")
    pane.players.setCurrentIndex(1)
    assert pane.editor.toPlainText() == ""
    pane.editor.setPlainText("Second pilot notes")
    pane.show_aircraft(Aircraft(flight(first, kind="F-16C_50")))
    assert pane.editor.toPlainText() == ""
    pane.editor.setPlainText("Viper checklist")
    restored = pickle.loads(pickle.dumps(first))
    assert notes_for_flight(flight(restored)) == [("One", "Hornet checklist")]
    assert notes_for_flight(flight(restored, kind="F-16C_50")) == [
        ("One", "Viper checklist")
    ]
    assert second.aircraft_notes == {"FA-18C_hornet": "Second pilot notes"}
    pane.show_aircraft(None)
    assert not pane.editor.isEnabled()
    pane.close()


def test_old_pilot_save_gets_independent_notes() -> None:
    pilot = Pilot("Old")
    state = dict(pilot.__dict__)
    state.pop("aircraft_notes")
    pilot.__setstate__(state)
    assert pilot.aircraft_notes == {}


def test_notes_preserve_pilot_constructor_and_identity() -> None:
    pilot = Pilot("Old", False, PilotStatus.OnLeave)
    assert pilot.status == PilotStatus.OnLeave
    assert pilot.aircraft_notes == {}
