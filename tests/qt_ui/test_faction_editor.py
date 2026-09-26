"""Exercise the campaign editor without touching the shared faction templates."""

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(qt_app: Any, tmp_path: Path) -> Iterator[Any]:
    from game import persistency
    from game.factions import FACTIONS
    from qt_ui.widgets.factioneditor import FactionEditor

    persistency.setup(str(tmp_path), False, 16897)
    widget = FactionEditor(deepcopy(FACTIONS["USA 2005"]), side="OWNFOR")
    yield widget
    widget.close()
    widget.deleteLater()
    qt_app.processEvents()


def test_all_pools_show_the_correct_collection_and_add_catalogue(editor: Any) -> None:
    from qt_ui.widgets.factioneditor import POOLS

    for index, (_, attribute, combo_name, _) in enumerate(POOLS):
        editor.categories.setCurrentItem(editor.categories.topLevelItem(index))
        collection = getattr(editor.faction, attribute)
        assert editor.units.topLevelItemCount() == len(collection)
        assert editor.categories.topLevelItem(index).text(1) == str(len(collection))
        combo = getattr(editor, combo_name)
        assert all(combo.itemData(i) not in collection for i in range(combo.count()))


def test_remove_and_add_preserve_filter_category_and_emit_changes(editor: Any) -> None:
    from PySide6.QtCore import Qt

    editor.categories.setCurrentItem(editor.categories.topLevelItem(2))
    item = editor.units.topLevelItem(0)
    unit = item.data(0, Qt.ItemDataRole.UserRole)
    name = item.text(0)
    editor.search.setText(name)
    editor.units.setCurrentItem(item)
    changes: list[Any] = []
    editor.faction_changed.connect(changes.append)
    editor.remove_button.click()
    assert unit not in editor.faction.tankers
    assert editor.search.text() == name
    assert editor.categories.indexOfTopLevelItem(editor.categories.currentItem()) == 2
    combo = editor.add_tanker_combo
    index = next(i for i in range(combo.count()) if combo.itemData(i) == unit)
    combo.setCurrentIndex(index)
    editor.add_button.click()
    assert unit in editor.faction.tankers
    assert len(changes) == 2
    assert editor.search.text() == name


def test_in_use_rows_explain_why_removal_is_disabled(editor: Any) -> None:
    editor.in_use = lambda unit: "2 squadrons fly it"
    editor.updateFaction(editor.faction)
    item = editor.units.topLevelItem(0)
    editor.units.setCurrentItem(item)
    assert item.text(1) == "In use"
    assert not editor.remove_button.isEnabled()
    assert "2 squadrons" in editor.selection_hint.text()


def test_filter_clears_hidden_selection_and_has_empty_state(editor: Any) -> None:
    editor.units.setCurrentItem(editor.units.topLevelItem(0))
    editor.search.setText("no such aircraft zzz")
    assert not editor.units.selectedItems()
    assert not editor.remove_button.isEnabled()
    assert not editor.empty.isHidden()
    editor.search.clear()
    assert editor.empty.isHidden()
    assert all(
        not editor.units.topLevelItem(i).isHidden()
        for i in range(editor.units.topLevelItemCount())
    )


def test_settings_update_faction_and_notify_campaign(editor: Any) -> None:
    changes: list[Any] = []
    editor.faction_changed.connect(changes.append)
    editor.jtac.click()
    assert editor.faction.has_jtac == editor.jtac.isChecked()
    index = (editor.doctrine_combo.currentIndex() + 1) % editor.doctrine_combo.count()
    editor.doctrine_combo.setCurrentIndex(index)
    assert editor.faction.doctrine is editor.doctrine_combo.currentData()
    assert len(changes) == 2
