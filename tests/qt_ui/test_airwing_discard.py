"""Discarding the air wing changes has to undo the ones already written.

Max size, the pilot limit and the cheat's aircraft buttons take effect the moment they
are touched, because the parking counts are drawn from them. Discard used to rebuild
the cards from the wing those edits had already gone into, so it put back only what was
still sitting in the form: the name, the nickname, the task, the livery and the base.
"""

from __future__ import annotations

import os
from collections import defaultdict
from types import SimpleNamespace
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Wing:
    """An air wing as far as a discard reaches into one."""

    def __init__(self, squadrons: dict[str, list[Any]]) -> None:
        self.squadrons: Any = defaultdict(list, squadrons)
        self.claimed: list[Any] = []
        self.unclaimed: list[Any] = []

    def iter_squadrons(self) -> Any:
        for group in self.squadrons.values():
            yield from group

    def claim_squadron_def(self, squadron: Any) -> None:
        self.claimed.append(squadron)

    def unclaim_squadron_def(self, squadron: Any) -> None:
        self.unclaimed.append(squadron)


class _Squadron:
    """A squadron with the fields a discard puts back, and hashable like the real one."""

    def __init__(self, name: str, size: int = 12, owned: int = 12) -> None:
        self.name = name
        self.max_size = size
        self.pilot_limit_override: Any = None
        self.owned_aircraft = owned
        self.untasked_aircraft = owned

    def __repr__(self) -> str:
        return self.name


def _squadron(name: str, size: int = 12, owned: int = 12) -> Any:
    return _Squadron(name, size, owned)


def _tab(wing: _Wing) -> Any:
    """The tab, built without its user interface: a discard touches neither."""
    from qt_ui.windows.airwingconfig.dialog import AirWingConfigurationTab

    tab = AirWingConfigurationTab.__new__(AirWingConfigurationTab)
    tab.coalition = cast(Any, SimpleNamespace(air_wing=wing))
    tab._at_open = tab._snapshot()
    return tab


def test_a_number_the_player_changed_goes_back() -> None:
    hornets = _squadron("VFA-106", size=12, owned=12)
    wing = _Wing({"F/A-18C": [hornets]})
    tab = _tab(wing)

    hornets.max_size = 24
    hornets.owned_aircraft = 30
    hornets.untasked_aircraft = 30
    hornets.pilot_limit_override = 3

    tab.discard()

    assert hornets.max_size == 12
    assert hornets.owned_aircraft == 12
    assert hornets.untasked_aircraft == 12
    assert hornets.pilot_limit_override is None


def test_a_squadron_the_player_deleted_comes_back() -> None:
    hornets = _squadron("VFA-106")
    vipers = _squadron("VFA-34")
    wing = _Wing({"F/A-18C": [hornets, vipers]})
    tab = _tab(wing)

    wing.squadrons["F/A-18C"] = [hornets]

    tab.discard()

    assert list(wing.iter_squadrons()) == [hornets, vipers]
    assert vipers in wing.claimed


def test_a_squadron_the_player_added_goes_away_and_gives_its_preset_back() -> None:
    hornets = _squadron("VFA-106")
    newcomer = _squadron("VFA-999")
    wing = _Wing({"F/A-18C": [hornets]})
    tab = _tab(wing)

    wing.squadrons["F/A-18C"] = [hornets, newcomer]

    tab.discard()

    assert list(wing.iter_squadrons()) == [hornets]
    assert wing.unclaimed == [newcomer]


def test_the_snapshot_is_not_the_wings_own_lists() -> None:
    """Otherwise editing the wing edits the copy it is supposed to be restored from."""
    hornets = _squadron("VFA-106")
    wing = _Wing({"F/A-18C": [hornets]})
    tab = _tab(wing)

    wing.squadrons["F/A-18C"].clear()

    tab.discard()

    assert list(wing.iter_squadrons()) == [hornets]
