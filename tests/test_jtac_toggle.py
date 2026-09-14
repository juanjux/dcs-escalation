"""Turning the faction's JTAC off without starting a new campaign.

The JTAC aircraft spawns from the FACTION's has_jtac flag, whose only control was the
checkbox on the new-game wizard's faction page, so a running campaign could not switch
it off. The CTLD plugin's options only change what the JTAC does once it is there.
"""

from __future__ import annotations

from game.settings import Settings


def test_the_jtac_is_on_by_default() -> None:
    """Off by default would silently drop the JTAC from every existing campaign."""
    assert Settings().use_jtac


def test_a_save_written_before_the_option_still_gets_its_jtac() -> None:
    """__setstate__ fills a setting the pickle never had, and the fill must be True."""
    old = Settings()
    state = dict(old.__dict__)
    del state["use_jtac"]

    restored = Settings.__new__(Settings)
    restored.__setstate__(state)

    assert restored.use_jtac


def test_it_sits_beside_the_other_jtac_option() -> None:
    """Both JTAC controls in one place: they are confusing enough apart."""
    import dataclasses

    from game.settings.optiondescription import SETTING_DESCRIPTION_KEY

    options = {
        f.name: f.metadata[SETTING_DESCRIPTION_KEY]
        for f in dataclasses.fields(Settings)
        if f.name in {"use_jtac", "jtac_count"}
    }
    assert options["use_jtac"].page == "Mission Generator"
    assert options["use_jtac"].section == options["jtac_count"].section == "Gameplay"
