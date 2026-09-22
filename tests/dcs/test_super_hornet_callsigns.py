"""The CJS Super Hornet ships four callsign pools, and pydcs looks them up by shortname.

The extension carried a single pool, and the names in it were the Australian ones, so
every US Rhino, Growler and tanker called as a RAAF jet and the other three nations had
no pool at all. A block copied straight out of an export keys by the name DCS displays,
which resolves for USA alone and silently drops the rest.
"""

from __future__ import annotations

import pytest

TYPES = ["FA_18E", "FA_18F", "EA_18G", "FA_18ET", "FA_18FT"]


def _callnames(type_name: str) -> dict[str, list[str]]:
    # `game` first: importing a pydcs_extensions submodule on its own re-enters the
    # package while `persistency` is still being read out of it.
    import game  # noqa: F401
    from pydcs_extensions.fa18efg import fa18efg

    return getattr(fa18efg, type_name).callnames


@pytest.mark.parametrize("type_name", TYPES)
def test_all_four_nations_have_a_pool(type_name: str) -> None:
    assert set(_callnames(type_name)) == {"USA", "AUS", "KWT", "AUSAF"}


@pytest.mark.parametrize("type_name", TYPES)
def test_the_keys_are_shortnames_pydcs_can_resolve(type_name: str) -> None:
    """`Mission._assign_callsign` reads `callnames.get(country.shortname)`."""
    import dcs.countries as countries

    shortnames = {
        cls.shortname
        for cls in vars(countries).values()
        if isinstance(cls, type) and hasattr(cls, "shortname")
    }
    assert set(_callnames(type_name)) <= shortnames


@pytest.mark.parametrize("type_name", TYPES)
def test_the_us_pool_is_not_the_australian_one(type_name: str) -> None:
    names = _callnames(type_name)
    assert "Hornet" in names["USA"]
    assert "Brutal" not in names["USA"]
    assert "Brutal" in names["AUS"]


def test_a_task_force_squadron_chains_every_pool() -> None:
    """pydcs gives Combined Joint Task Forces the union, so the count is the sum."""
    names = _callnames("FA_18E")
    assert sum(len(pool) for pool in names.values()) == 66
