"""Library UI does not edit flights or lose unsaved drafts during navigation."""

import os
from types import SimpleNamespace
from typing import Any

import pytest

from tests.test_payloadlibrary import library  # noqa: F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app: Any, library: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from game.dcs.aircrafttype import AircraftType
    from qt_ui.windows.payloads import PayloadsDialog

    airframe: Any = SimpleNamespace(
        dcs_id=library.plane.id,
        display_name="Test aircraft",
        dcs_unit_type=library.plane,
    )
    monkeypatch.setattr(
        AircraftType, "iter_all", classmethod(lambda cls: iter([airframe]))
    )
    widget = PayloadsDialog(aircraft=airframe)
    yield widget
    widget.dirty = False
    widget.close()


def test_sources_unknown_store_and_aircraft_are_preserved(
    dialog: Any, library: Any
) -> None:
    assert dialog.aircraft.dcs_id == library.plane.id
    assert [dialog.tree.topLevelItem(i).text(0) for i in range(2)] == [
        "Escalation",
        "Custom",
    ]
    assert dialog.pylons[2].currentData() == "unknown-mod-store"
    assert not dialog.dirty
    assert dialog.save_payload()
    updated = next(
        e for e in library.lib.entries(library.plane.id) if e.source == "Escalation"
    )
    assert updated.payload["pylons"] == library.raw["pylons"]
    assert updated.payload["custom_field"] == {9: "keep"}
    assert updated.payload["ammo_type"] == 3


def test_new_duplicate_and_delete_custom_payload(
    dialog: Any, library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog.new_payload()
    dialog.name_edit.setText("New Custom")
    assert dialog.save_payload()
    assert dialog.entry.source == "Custom"
    dialog.duplicate()
    assert dialog.entry is None
    assert dialog.save_payload()
    assert getattr(dialog.entry, "name") == "New Custom copy"
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    dialog.delete_payload()
    names = {e.name for e in library.lib.entries(library.plane.id)}
    assert "New Custom" in names and "New Custom copy" not in names


def test_cancel_selection_change_retains_draft(
    dialog: Any, library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    library.lib.save(library.plane, {**library.raw, "name": "Other"})
    dialog._reload()
    previous = dialog.tree.currentItem()
    dialog.name_edit.setText("Unsaved")
    dialog._changed()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(1).child(0))
    assert dialog.tree.currentItem() is previous
    assert dialog.name_edit.text() == "Unsaved" and dialog.dirty
    assert not any(e.name == "Unsaved" for e in library.lib.entries(library.plane.id))


def test_save_then_select_does_not_use_deleted_tree_items(
    dialog: Any, library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    library.lib.save(library.plane, {**library.raw, "name": "Other"})
    dialog._reload()
    dialog.name_edit.setText("Renamed")
    dialog._changed()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save
    )
    dialog.tree.setCurrentItem(dialog.tree.topLevelItem(1).child(0))
    assert dialog.entry.name == "Other"
    assert dialog.tree.currentItem().text(0) == "Other"
    assert any(e.name == "Renamed" for e in library.lib.entries(library.plane.id))


def test_save_pending_on_aircraft_switch_uses_original_aircraft(
    dialog: Any, library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dcs.unittype import FlyingType
    from PySide6.QtWidgets import QMessageBox

    class OtherPlane(FlyingType):
        id = "OtherPlane"
        payloads = None

    other = SimpleNamespace(
        dcs_id=OtherPlane.id, display_name="Other aircraft", dcs_unit_type=OtherPlane
    )
    dialog.aircraft_combo.addItem("Other aircraft", other)
    dialog.name_edit.setText("Old aircraft edit")
    dialog._changed()
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save
    )
    dialog.aircraft_combo.setCurrentIndex(dialog.aircraft_combo.count() - 1)
    assert dialog.aircraft.dcs_id == OtherPlane.id
    assert any(
        e.name == "Old aircraft edit" for e in library.lib.entries(library.plane.id)
    )
    assert library.lib.entries(OtherPlane.id) == []


def test_training_filter_is_not_a_payload_edit(dialog: Any) -> None:
    before = dialog.draft.copy()
    dialog.training.setChecked(True)
    dialog.training.setChecked(False)
    assert not dialog.dirty and dialog.draft == before


def test_unknown_ammunition_is_retained_on_unrelated_edits(
    dialog: Any, library: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import qt_ui.windows.payloads as module

    monkeypatch.setattr(module, "GAU8_AIRCRAFT", {library.plane.id})
    dialog.draft["ammo_type"] = 42
    dialog._build_editor()
    assert dialog.ammo_combo.currentData() == 42
    assert dialog.save_payload()
    assert dialog.entry.payload["ammo_type"] == 42


def test_discard_before_duplicate_uses_saved_payload(
    dialog: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    original = dialog.entry.name
    dialog.name_edit.setText("Unsaved name")
    dialog._changed()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
    dialog.duplicate()
    assert dialog.name_edit.text() == original + " copy"


def test_none_removes_station_and_weapon_settings(dialog: Any) -> None:
    combo = dialog.pylons[2]
    combo.setCurrentIndex(combo.findData(""))
    assert dialog._station(2) == {}
    assert dialog.save_payload()
    assert not dialog.entry.payload["pylons"]


@pytest.mark.parametrize("changed", [False, True])
def test_flight_entry_point_preselects_aircraft_and_preserves_assigned_snapshot(
    app: Any, monkeypatch: pytest.MonkeyPatch, changed: bool
) -> None:
    from PySide6.QtWidgets import QComboBox
    from game.ato.loadouts import Loadout
    from qt_ui.windows.mission.flight.payload.QFlightPayloadTab import QFlightPayloadTab
    import qt_ui.windows.payloads as module

    current = Loadout("CAS", {}, None, ammo_type=1)
    replacement = Loadout("CAS", {}, None, ammo_type=2 if changed else 1)
    airframe = object()
    tab: Any = SimpleNamespace(
        flight=SimpleNamespace(unit_type=airframe),
        member_selector=SimpleNamespace(
            selected_member=SimpleNamespace(loadout=current)
        ),
        loadout_selector=QComboBox(),
    )
    calls = []

    class FakeDialog:
        modified = True

        def __init__(self, parent: Any, aircraft: Any) -> None:
            calls.append((parent, aircraft))

        def exec(self) -> None:
            pass

    monkeypatch.setattr(module, "PayloadsDialog", FakeDialog)
    monkeypatch.setattr(
        Loadout, "iter_for", staticmethod(lambda flight: iter([replacement]))
    )
    signals: list[int] = []
    tab.loadout_selector.currentIndexChanged.connect(signals.append)
    QFlightPayloadTab.open_payloads_editor(tab)
    assert calls == [(tab, airframe)]
    assert tab.member_selector.selected_member.loadout is current
    assert current.ammo_type == 1
    assert not signals
    selected = tab.loadout_selector.currentData()
    assert selected is (current if changed else replacement)


def test_main_menu_entry_point_opens_standalone_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from qt_ui.windows.QLiberationWindow import QLiberationWindow
    import qt_ui.windows.payloads as module

    calls = []
    window: Any = object()

    class FakeDialog:
        def __init__(self, parent: Any) -> None:
            calls.append(parent)

        def exec(self) -> None:
            calls.append("opened")

    monkeypatch.setattr(module, "PayloadsDialog", FakeDialog)
    QLiberationWindow.showPayloadsEditor(window)
    assert calls == [window, "opened"]
