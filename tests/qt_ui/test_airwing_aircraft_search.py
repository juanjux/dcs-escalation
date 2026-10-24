"""Aircraft search preserves the Add Squadron dialog's selection and dependencies."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def aircraft(tmp_path: Any) -> Any:
    from game import persistency
    from game.dcs.aircrafttype import AircraftType

    persistency.setup(str(tmp_path), False, 0)
    return (
        AircraftType.named("A-10C Thunderbolt II (Suite 7)"),
        AircraftType.named("UH-1H Iroquois"),
    )


def test_search_preserves_sorted_items_and_initial_selection(
    qt_app: Any, aircraft: Any
) -> None:
    from qt_ui.widgets.searchablecombo import SearchableComboBox
    from qt_ui.windows.airwingconfig.popups import SquadronAircraftTypeSelector

    selected = aircraft[1]
    combo = SquadronAircraftTypeSelector(set(aircraft), selected.display_name)
    try:
        assert isinstance(combo, SearchableComboBox)
        assert combo.currentData() is selected
        assert [combo.itemText(row) for row in range(combo.count())] == sorted(
            item.display_name for item in aircraft
        )
        assert {combo.itemData(row) for row in range(combo.count())} == set(aircraft)
    finally:
        combo.close()


def test_filtered_choice_updates_dialog_dependencies(
    qt_app: Any, aircraft: Any
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from qt_ui.windows.airwingconfig.popups import SquadronConfigPopup

    first, second = aircraft
    bases: Any = [
        SimpleNamespace(name=item.display_name, can_operate=lambda ac, t=item: ac is t)
        for item in aircraft
    ]
    preset: Any = SimpleNamespace(name="Test squadron", nickname=None, claimed=False)
    dialog = SquadronConfigPopup(
        first.display_name, set(aircraft), bases, {second: [preset]}
    )
    combo = dialog.aircraft_type_selector
    combo.threshold = 2
    try:
        dialog.show()
        combo.showPopup()
        combo._search.setText("iroQUOis")
        visible = [
            combo.itemData(row)
            for row in range(combo.count())
            if not combo._list.isRowHidden(row)
        ]
        assert visible == [second]
        assert combo.currentData() is first

        QTest.keyClick(combo._search, Qt.Key.Key_Return)

        assert combo.currentData() is second
        assert dialog.squadron_base_selector.currentData() is bases[1]
        assert dialog.squadron_def_selector.itemData(1) is preset
        tasks = dialog.primary_task_selector
        assert {tasks.itemData(row) for row in range(tasks.count())} == set(
            second.iter_task_capabilities()
        )
        assert dialog.accept_button.isEnabled()
        assert not combo._popup.isVisible()

        combo.showPopup()
        assert combo._search.text() == ""
        assert not any(combo._list.isRowHidden(row) for row in range(combo.count()))
    finally:
        combo.hidePopup()
        dialog.close()


@pytest.mark.parametrize("key", ["Key_Return", "Key_Escape"])
def test_no_match_does_not_change_selection(
    qt_app: Any, aircraft: Any, key: str
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from qt_ui.windows.airwingconfig.popups import SquadronAircraftTypeSelector

    selected = aircraft[0]
    combo = SquadronAircraftTypeSelector(set(aircraft), selected.display_name)
    combo.threshold = 2
    try:
        combo.show()
        combo.showPopup()
        combo._search.setText("no matching aircraft")
        QTest.keyClick(combo._search, getattr(Qt.Key, key))

        assert combo.currentData() is selected
        assert not combo._popup.isVisible()
    finally:
        combo.hidePopup()
        combo.close()
