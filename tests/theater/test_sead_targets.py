"""A SEAD flight is pointed at emitters, not at the site's fuel bowsers.

It shoots anti-radiation missiles from a standoff orbit, so a cargo truck is not
something it can be steered to, and listing every vehicle also publishes the site's
exact composition on a kneeboard page written to withhold it. DEAD is not filtered: it
kills individual vehicles, and the trucks are what a mobile SAM moves with.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional, cast

import pytest

from game.data.units import UnitClass


def _unit(name: str, unit_class: Optional[UnitClass], alive: bool = True) -> Any:
    unit_type = None if unit_class is None else SimpleNamespace(unit_class=unit_class)
    return SimpleNamespace(name=name, alive=alive, unit_type=unit_type)


class _Unregistered:
    """A mod unit whose type does not resolve: `unit_type` raises, as pydcs does."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.alive = True

    @property
    def unit_type(self) -> Any:
        raise StopIteration(self.name)


def _site(units: list[Any]) -> Any:
    """A bare objective: the two lists read `groups`, nothing else."""
    from game.theater.theatergroundobject import MissileSiteGroundObject

    site = MissileSiteGroundObject.__new__(MissileSiteGroundObject)
    site.groups = [cast(Any, SimpleNamespace(units=units))]
    return site


SA2 = [
    _unit("SNR-75 track radar", UnitClass.TRACK_RADAR),
    _unit("P-19 search radar", UnitClass.SEARCH_RADAR),
    _unit("launcher 1", UnitClass.LAUNCHER),
    _unit("launcher 2", UnitClass.LAUNCHER),
    _unit("ZU-23", UnitClass.AAA),
    _unit("GAZ-66", UnitClass.LOGISTICS),
    _unit("TZ-22 bowser", UnitClass.LOGISTICS),
]


def test_sead_gets_the_emitters() -> None:
    names = [u.name for u in _site(SA2).sead_targets]
    assert names == [
        "SNR-75 track radar",
        "P-19 search radar",
        "launcher 1",
        "launcher 2",
    ]


def test_dead_still_gets_the_whole_site() -> None:
    assert len(_site(SA2).strike_targets) == 7


def test_a_dead_bowser_is_in_neither_list() -> None:
    site = _site(SA2 + [_unit("wreck", UnitClass.LOGISTICS, alive=False)])
    assert "wreck" not in [u.name for u in site.strike_targets]
    assert "wreck" not in [u.name for u in site.sead_targets]


def test_an_unresolvable_type_is_kept() -> None:
    """Unknown is not absent: a mod radar the fork has no data for must not vanish."""
    site = _site([_Unregistered("HDS Big Bird"), _unit("GAZ-66", UnitClass.LOGISTICS)])
    assert [u.name for u in site.sead_targets] == ["HDS Big Bird"]


def test_a_site_with_no_emitter_falls_back_to_everything() -> None:
    """Hand-fragging SEAD at an emitterless site must still leave it a target."""
    site = _site([_unit("GAZ-66", UnitClass.LOGISTICS), _unit("ZU-23", UnitClass.AAA)])
    assert len(site.sead_targets) == 2


@pytest.mark.parametrize(
    "unit_class",
    [
        UnitClass.SEARCH_RADAR,
        UnitClass.SEARCH_TRACK_RADAR,
        UnitClass.TRACK_RADAR,
        UnitClass.SPECIALIZED_RADAR,
        UnitClass.EARLY_WARNING_RADAR,
        UnitClass.TELAR,
        UnitClass.SHORAD,
        UnitClass.LAUNCHER,
    ],
)
def test_every_emitter_class_survives(unit_class: UnitClass) -> None:
    site = _site([_unit("x", unit_class), _unit("truck", UnitClass.LOGISTICS)])
    assert [u.name for u in site.sead_targets] == ["x"]
