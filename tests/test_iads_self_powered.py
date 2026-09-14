"""A site that deploys with its own generator does not live off the grid.

A Patriot battery brings an EPP-III, a SAMP/T an MGE. Bombing whichever substation
happened to be nearest used to switch the battery off, because the IADS gave every SAM
in range a power dependency without asking whether it needed one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.data.units import UnitClass
from game.theater.iadsnetwork.iadsnetwork import brings_its_own_power


def _unit(unit_class: UnitClass, alive: bool = True) -> Any:
    return SimpleNamespace(
        alive=alive, unit_type=SimpleNamespace(unit_class=unit_class)
    )


def _group(*units: Any) -> Any:
    return SimpleNamespace(units=list(units))


def test_a_battery_with_a_live_generator_powers_itself() -> None:
    group = _group(
        _unit(UnitClass.LAUNCHER),
        _unit(UnitClass.SEARCH_RADAR),
        _unit(UnitClass.POWER),
    )
    assert brings_its_own_power(group)


def test_a_site_with_no_generator_lives_off_the_grid() -> None:
    assert not brings_its_own_power(
        _group(_unit(UnitClass.LAUNCHER), _unit(UnitClass.SEARCH_RADAR))
    )


def test_killing_the_generator_puts_the_site_back_on_the_grid() -> None:
    """The point of asking at mission-generation time rather than when the network is
    built: the EPP is a unit in the group and can be struck like any other."""
    group = _group(_unit(UnitClass.LAUNCHER), _unit(UnitClass.POWER, alive=False))
    assert not brings_its_own_power(group)


def test_a_group_whose_units_have_no_type_does_not_raise() -> None:
    """Save compatibility: a unit whose type no longer resolves reads as no generator
    rather than taking mission generation down with it."""
    group = _group(SimpleNamespace(alive=True, unit_type=None))
    assert not brings_its_own_power(group)


def test_an_empty_group_brings_nothing() -> None:
    assert not brings_its_own_power(_group())


def test_the_generators_the_campaign_data_knows_about() -> None:
    """Guards the choice of reading the unit class instead of a list of ids: if the
    class stops being set on these, the feature silently stops working."""
    from pathlib import Path

    units = Path(__file__).resolve().parent.parent / "resources/units/ground_units"
    classed = {
        path.stem
        for path in units.glob("*.yaml")
        if "class: Power" in path.read_text(encoding="utf-8")
    }
    assert "Patriot EPP" in classed, "the stock Patriot generator lost its class"
    assert "SAMPT_MGE" in classed, "the SAMP/T generator lost its class"
