"""Unticking a unit in the New Game wizard has to survive adding another one.

The list of tick boxes is rebuilt from the faction whenever anything is added to it,
and a box that has just been built is ticked, so every unit dropped before pressing +
came back.
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
    # Unit and preset loading reads the DCS saved-game folder, which only exists once
    # the app boots. An empty temp dir falls back to the bundled resources.
    from game import persistency

    persistency.setup(str(tmp_path_factory.mktemp("saved_games")), False, 16897)


@pytest.fixture
def faction() -> Any:
    """A real faction: the widget reads a dozen of their fields."""
    from game.factions import FACTIONS

    return FACTIONS["USA 2005"]


def _units(faction: Any) -> Any:
    from qt_ui.windows.newgame.WizardPages.QFactionSelection import QFactionUnits

    return QFactionUnits(faction)


def test_an_unticked_unit_stays_unticked_when_another_is_added(
    qt_app: Any, faction: Any
) -> None:
    widget = _units(faction)
    name = next(name for name in widget.checkboxes if "F-14" in name)
    widget.checkboxes[name].setChecked(False)

    # What pressing + does: the faction gains a unit and the list is rebuilt.
    widget.updateFaction(faction)

    assert not widget.checkboxes[name].isChecked()


def test_the_rest_are_left_ticked(qt_app: Any, faction: Any) -> None:
    widget = _units(faction)
    dropped = next(name for name in widget.checkboxes if "F-14" in name)
    widget.checkboxes[dropped].setChecked(False)

    widget.updateFaction(faction)

    assert all(
        cb.isChecked() for name, cb in widget.checkboxes.items() if name != dropped
    )


def test_changing_faction_starts_clean(qt_app: Any, faction: Any) -> None:
    """A different faction has different units, and nobody unticked those."""
    from copy import deepcopy

    widget = _units(faction)
    name = next(iter(widget.checkboxes))
    widget.checkboxes[name].setChecked(False)

    widget.updateFaction(deepcopy(faction))

    assert all(cb.isChecked() for cb in widget.checkboxes.values())
