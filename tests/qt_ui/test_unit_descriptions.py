"""What a unit row of a location calls the unit.

The class is the description almost always, and where it is wrong about one of its
units the unit says so itself. SpecializedRadar is the case that forced it: eight of
its nine units are the acquisition radar of a big SAM and the ninth is a radio mast.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _init_persistency(tmp_path_factory: pytest.TempPathFactory) -> None:
    # Unit loading reads the DCS saved-game folder, which only exists once the app
    # boots. An empty temp dir falls back to the bundled resources.
    from game import persistency

    persistency.setup(str(tmp_path_factory.mktemp("saved_games")), False, 16897)


def _unit(dcs_id: str, unit_class: Any) -> Any:
    """A theater unit thin enough for the two functions under test."""
    return SimpleNamespace(
        unit_type=SimpleNamespace(dcs_id=dcs_id, unit_class=unit_class)
    )


def test_a_specialized_radar_is_a_search_radar() -> None:
    from game.data.units import UnitClass
    from qt_ui.windows.groundobject.unitcard import describe_unit, unit_note

    clam_shell = _unit("S-300PS 40B6MD sr", UnitClass.SPECIALIZED_RADAR)

    assert describe_unit(cast(Any, clam_shell)) == "search radar"
    assert unit_note(cast(Any, clam_shell)) == "finds the targets"


def test_a_units_own_entry_beats_its_class() -> None:
    from game.data.units import UnitClass
    from qt_ui.windows.groundobject.unitcard import describe_unit, unit_note

    mast = _unit("Patriot AMG", UnitClass.SPECIALIZED_RADAR)

    assert describe_unit(cast(Any, mast)) == "comms relay"
    assert "radio links" in unit_note(cast(Any, mast))


def test_everything_else_still_reads_from_its_class() -> None:
    from game.data.units import UnitClass
    from qt_ui.windows.groundobject.unitcard import describe_unit

    assert describe_unit(cast(Any, _unit("Hawk tr", UnitClass.TRACK_RADAR))) == (
        "tracking radar"
    )
