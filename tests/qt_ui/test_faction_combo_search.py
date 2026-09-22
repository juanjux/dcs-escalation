"""The faction editor's add-a-unit lists are searchable.

Every one of them offers what the faction does not already have, which for aircraft,
ground units and ships is most of DCS. Finding one meant scrolling a few hundred
entries.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _init_persistency(tmp_path_factory: pytest.TempPathFactory) -> None:
    from game import persistency

    persistency.setup(str(tmp_path_factory.mktemp("saved_games")), False, 16897)


@pytest.fixture
def widget(qt_app: Any) -> Any:
    from game.factions import FACTIONS
    from qt_ui.windows.newgame.WizardPages.QFactionSelection import QFactionUnits

    return QFactionUnits(FACTIONS["USA 2005"])


COMBOS = [
    "add_ac_combo",
    "add_awacs_combo",
    "add_tanker_combo",
    "add_frontline_combo",
    "add_artillery_combo",
    "add_logistics_combo",
    "add_infantry_combo",
    "add_preset_group_combo",
    "add_air_defense_combo",
    "add_naval_combo",
    "add_missile_combo",
]


@pytest.mark.parametrize("name", COMBOS)
def test_every_add_list_can_be_searched(widget: Any, name: str) -> None:
    from qt_ui.widgets.searchablecombo import SearchableComboBox

    assert isinstance(getattr(widget, name), SearchableComboBox)


def test_typing_narrows_the_list(widget: Any) -> None:
    combo = widget.add_naval_combo
    combo._list.setModel(combo.model())
    needle = combo.itemText(0).split()[0].lower()
    combo._filter(needle)

    shown = [
        combo.itemText(row)
        for row in range(combo.count())
        if not combo._list.isRowHidden(row)
    ]
    assert shown
    assert all(needle in text.lower() for text in shown)
    assert len(shown) < combo.count()


def test_clearing_the_field_brings_everything_back(widget: Any) -> None:
    combo = widget.add_naval_combo
    combo._list.setModel(combo.model())
    combo._filter(combo.itemText(0).split()[0].lower())
    combo._filter("")

    assert not any(combo._list.isRowHidden(row) for row in range(combo.count()))


def test_the_items_are_unchanged(widget: Any) -> None:
    """The combo still carries the unit type as item data, which + reads."""
    from game.dcs.shipunittype import ShipUnitType

    combo = widget.add_naval_combo
    assert combo.count() > 0
    assert all(
        isinstance(combo.itemData(row), ShipUnitType) for row in range(combo.count())
    )
