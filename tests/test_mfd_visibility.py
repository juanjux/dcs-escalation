"""What the cockpit displays are allowed to show of the enemy's air defence.

Two questions decide it -- how far the site shoots and whether it shoots from where it
drives -- and the player's own answer for a site beats both.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.data.units import UnitClass
from game.mfd import (
    Band,
    MfdIntel,
    band_of,
    campaign_shows,
    is_mobile,
    remember_positions,
    shows_on_mfd,
)
from game.settings import Settings
from game.utils import meters


def _unit(type_id: str, threat_km: float, unit_class: UnitClass) -> Any:
    return SimpleNamespace(
        type=SimpleNamespace(id=type_id),
        unit_type=SimpleNamespace(unit_class=unit_class),
        threat_range=meters(threat_km * 1000),
    )


def _at(x: float, y: float = 0.0) -> Any:
    return SimpleNamespace(
        x=x,
        y=y,
        distance_to_point=lambda other: ((x - other.x) ** 2 + (y - other.y) ** 2)
        ** 0.5,
    )


def _site(*units: Any, at: float = 0.0, chosen: Any = None) -> Any:
    return SimpleNamespace(
        units=list(units),
        position=_at(at),
        hide_on_mfd=chosen,
        mfd_seen_at=None,
    )


def _patriot() -> Any:
    return _site(_unit("Patriot ln", 100, UnitClass.LAUNCHER))


def _hawk() -> Any:
    return _site(_unit("Hawk ln", 45, UnitClass.LAUNCHER))


def _buk() -> Any:
    return _site(_unit("SA-11 Buk LN 9A310M1", 50, UnitClass.TELAR))


def _tor() -> Any:
    return _site(_unit("Tor 9A331", 12, UnitClass.TELAR))


def _flak() -> Any:
    return _site(_unit("KS-19", 20, UnitClass.AAA))


def test_the_band_is_how_far_the_site_shoots() -> None:
    assert band_of(_patriot()) is Band.LONG
    assert band_of(_hawk()) is Band.MEDIUM
    assert band_of(_tor()) is Band.SHORT


def test_a_gun_site_is_short_range_whatever_its_ceiling() -> None:
    """A KS-19 reaches 20 km straight up and is still a gun emplacement."""
    assert band_of(_flak()) is Band.SHORT


def test_a_system_that_shoots_from_where_it_drives_is_mobile() -> None:
    assert is_mobile(_buk())
    assert is_mobile(_tor())
    assert not is_mobile(_patriot())


def test_a_battery_guarded_by_a_mobile_gun_is_still_emplaced() -> None:
    site = _site(
        _unit("Hawk ln", 45, UnitClass.LAUNCHER),
        _unit("M6 Linebacker", 4.5, UnitClass.SHORAD),
    )

    assert not is_mobile(site)


def test_a_mod_is_read_off_its_unit_class() -> None:
    site = _site(_unit("Some Mod TELAR", 30, UnitClass.TELAR))

    assert is_mobile(site)


def test_the_defaults_show_the_batteries_and_hide_the_guns() -> None:
    settings = Settings()

    assert campaign_shows(_patriot(), settings)
    assert campaign_shows(_hawk(), settings)
    assert not campaign_shows(_flak(), settings)


def test_a_mobile_site_is_shown_where_the_picture_found_it() -> None:
    settings = Settings()
    settings.mfd_mobile_medium = MfdIntel.LAST_TURN
    site = _buk()

    # Nothing has been photographed yet: a site put up this turn is not on the picture.
    assert not campaign_shows(site, settings)

    remember_positions(iter([site]))
    assert campaign_shows(site, settings)

    site.position = _at(50_000)
    assert not campaign_shows(site, settings)


def test_the_current_setting_does_not_care_where_it_was() -> None:
    settings = Settings()
    settings.mfd_mobile_medium = MfdIntel.CURRENT

    assert campaign_shows(_buk(), settings)


def test_nothing_shows_a_band_that_is_switched_off() -> None:
    settings = Settings()
    settings.mfd_mobile_medium = MfdIntel.NEVER
    site = _buk()
    remember_positions(iter([site]))

    assert not campaign_shows(site, settings)


def test_the_players_own_answer_beats_the_campaign() -> None:
    settings = Settings()

    assert not shows_on_mfd(
        _site(_unit("Patriot ln", 100, UnitClass.LAUNCHER), chosen=True), settings
    )
    assert shows_on_mfd(
        _site(_unit("KS-19", 20, UnitClass.AAA), chosen=False), settings
    )


def test_a_site_nobody_touched_follows_the_campaign() -> None:
    settings = Settings()
    settings.mfd_static_long = False

    assert not shows_on_mfd(_patriot(), settings)


def test_manpads_are_never_shown() -> None:
    """Not by the settings, and not by asking for them either."""
    settings = Settings()
    settings.mfd_mobile_short = MfdIntel.CURRENT
    team = _site(_unit("SA-18 Igla manpad", 5.2, UnitClass.MANPAD))

    assert not shows_on_mfd(team, settings)

    team.hide_on_mfd = False
    assert not shows_on_mfd(team, settings)


def test_a_battery_with_manpads_guarding_it_is_still_a_battery() -> None:
    settings = Settings()
    site = _site(
        _unit("Patriot ln", 100, UnitClass.LAUNCHER),
        _unit("SA-18 Igla manpad", 5.2, UnitClass.MANPAD),
    )

    assert shows_on_mfd(site, settings)


def test_the_armys_tracked_batteries_are_mobile() -> None:
    """High Digit SAMs: the S-300V family shoots and moves; the S-300P does not."""
    tracked = _site(_unit("S-300V 9A83 ln", 75, UnitClass.LAUNCHER))
    trailered = _site(_unit("S-300PMU1 5P85CE ln", 150, UnitClass.LAUNCHER))

    assert is_mobile(tracked)
    assert not is_mobile(trailered)


def test_the_new_launchers_the_mods_bring_land_in_the_right_band() -> None:
    assert band_of(_site(_unit("S-400 51P6A ln", 250, UnitClass.LAUNCHER))) is Band.LONG
    assert (
        band_of(_site(_unit("SA-17 Buk M1-2 LN 9A310M1-2", 50, UnitClass.TELAR)))
        is Band.MEDIUM
    )
    assert band_of(_site(_unit("Pantsir_SM", 30, UnitClass.SHORAD))) is Band.MEDIUM
