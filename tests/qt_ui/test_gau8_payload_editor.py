"""The GAU-8 selector follows the current payload without changing it on refresh."""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dcs import lua
from dcs.planes import A_10C_2

from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon
from game.data.gunammunition import GAU8_AMMUNITION

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from qt_ui.windows.mission.flight.payload.QLoadoutEditor import QLoadoutEditor

    monkeypatch.setattr(
        Pylon, "iter_pylons", classmethod(lambda cls, aircraft: iter(()))
    )
    member = FlightMember(None, Loadout("Test", {}, None))
    flight: Any = SimpleNamespace(unit_type=SimpleNamespace(dcs_unit_type=A_10C_2))
    game: Any = SimpleNamespace()
    return QLoadoutEditor(flight, member, game)


def test_selector_requires_custom_loadout_and_does_not_mutate_on_refresh(
    editor: Any,
) -> None:
    combo = editor.ammunition_selector
    assert [combo.itemText(i) for i in range(combo.count())] == list(
        GAU8_AMMUNITION.values()
    )
    assert combo.currentData() == 1
    assert not combo.isEnabled()
    assert editor.flight_member.loadout.ammo_type is None
    editor.flight_member.loadout = editor.flight_member.loadout.derive_custom("Custom")
    editor.setChecked(True)
    assert combo.isEnabled()
    combo.setCurrentIndex(combo.findData(2))
    assert editor.flight_member.loadout.ammo_type == 2
    second = FlightMember(None, Loadout("Practice", {}, None, ammo_type=3))
    first = editor.flight_member
    editor.set_flight_member(second)
    assert combo.currentData() == 3
    assert not combo.isEnabled()
    assert first.loadout.ammo_type == 2
    assert second.loadout.ammo_type == 3
    second.loadout = Loadout("Combat", {}, None)
    editor.reset_pylons()
    assert combo.currentData() == 1
    assert second.loadout.ammo_type is None


def test_selector_is_absent_for_other_aircraft(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from qt_ui.windows.mission.flight.payload.QLoadoutEditor import QLoadoutEditor

    monkeypatch.setattr(
        Pylon, "iter_pylons", classmethod(lambda cls, aircraft: iter(()))
    )
    flight: Any = SimpleNamespace(
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id="FA-18C_hornet"))
    )
    game: Any = SimpleNamespace()
    editor = QLoadoutEditor(flight, FlightMember(None, Loadout.empty_loadout()), game)
    assert editor.ammunition_selector is None


@pytest.mark.parametrize("ammo", [1, 2, 3, None])
def test_save_payload_round_trip_preserves_ammunition(
    editor: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ammo: int | None
) -> None:
    import importlib

    module = importlib.import_module(
        "qt_ui.windows.mission.flight.payload.QLoadoutEditor"
    )
    monkeypatch.setattr(module, "payloads_dir", lambda **kwargs: tmp_path)
    monkeypatch.setattr(A_10C_2, "payloads", {})
    monkeypatch.setattr(
        A_10C_2, "add_to_payload_cache", classmethod(lambda cls, path: None)
    )
    monkeypatch.setattr(A_10C_2, "load_payloads", classmethod(lambda cls: cls.payloads))
    monkeypatch.setattr(editor, "_create_backup_if_needed", lambda ac_id: None)
    editor.flight_member.loadout.ammo_type = ammo
    path = editor._persist_payload("Test ammo")
    assert path is not None
    entry = lua.loads(path.read_text(encoding="utf-8"))["unitPayloads"]["payloads"][1]
    assert entry.get("ammo_type") == ammo
    assert next(Loadout.iter_for_aircraft(editor.flight.unit_type)).ammo_type == ammo
    # Updating the same named payload must replace the previous ammunition too.
    editor.flight_member.loadout.ammo_type = 3
    editor._persist_payload("Test ammo")
    entry = lua.loads(path.read_text(encoding="utf-8"))["unitPayloads"]["payloads"][1]
    assert entry["ammo_type"] == 3
