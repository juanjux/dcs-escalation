"""How the High Command's lines name things."""

from __future__ import annotations

from typing import Any

from game.data.units import UnitClass
from game.highcommand.wording import listed, money, site_name, system_name
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroup import IadsGroundGroup
from tests.highcommand.stubs import launcher, sam, unit


def test_a_site_is_named_after_its_system() -> None:
    def named(label: str, unit_class: UnitClass = UnitClass.LAUNCHER) -> str:
        shooter = unit(label, unit_class=unit_class, reach_nm=5, anti_air=True)
        return system_name(sam("SITE", 0, [shooter]))

    assert named('SAM SA-10 S-300 "Grumble" LN') == "SA-10"
    assert named("HQ-7 Launcher") == "HQ-7"
    assert named("Patriot ln") == "Patriot"
    assert named("AAA KS-19", UnitClass.AAA) == "guns"
    assert system_name(sam("EMPTY", 0, [])) == "site"


def test_a_coastal_battery_is_named_after_its_launchers() -> None:
    radar = launcher("AShM Silkworm SR", 0)
    missiles = unit(
        "AShM SS-N-2 Silkworm", unit_class=UnitClass.ANTISHIP_MISSILE, reach_nm=0
    )

    assert system_name(sam("OPOSSUM", 0, [radar, missiles])) == "SS-N-2"


def _vulcan() -> Any:
    return unit(
        "SPAAA Vulcan M163", unit_class=UnitClass.AAA, reach_nm=1, anti_air=True
    )


def test_a_site_is_named_after_what_it_is_for_not_the_guns_guarding_it() -> None:
    jammer = unit("GPS Jammer", unit_class=None)
    jammer.unit_type.gps_jamming = object()
    jamming = sam("BEETLE", 0, [jammer, _vulcan()])
    radar = unit("EWR 55G6", unit_class=UnitClass.EARLY_WARNING_RADAR, sees_nm=200)
    warning = sam("WOLF", 0, [radar, _vulcan()])
    silkworm = unit("AShM SS-N-2 Silkworm", unit_class=UnitClass.ANTISHIP_MISSILE)
    gopher = unit(
        "SA-13 Gopher", unit_class=UnitClass.SHORAD, reach_nm=3, anti_air=True
    )
    coastal = sam("OPOSSUM", 0, [silkworm, gopher])

    assert [site_name(s) for s in (jamming, warning, coastal)] == [
        "GPS jammer",
        "EWR 55G6",
        "SS-N-2",
    ]
    # What threatens a route through them is still what shoots.
    assert [system_name(s) for s in (jamming, warning, coastal)] == [
        "Vulcan",
        "Vulcan",
        "SA-13",
    ]

    jammer.alive = False
    assert site_name(jamming) == "Vulcan"


def test_a_battery_keeps_its_name_when_only_its_point_defence_is_left() -> None:
    radar = unit(
        'SAM SA-10 S-300 "Grumble" Clam Shell SR',
        unit_class=UnitClass.SEARCH_RADAR,
        sees_nm=60,
    )
    missiles = launcher('SAM SA-10 S-300 "Grumble" LN', 40)
    battery = sam("GRUMBLE", 0, [radar, missiles])
    strela = unit("SA-9 Strela", unit_class=UnitClass.SHORAD, reach_nm=2, anti_air=True)
    guard = IadsGroundGroup(2, "PD", battery.groups[0].position, [strela], battery)
    guard.iads_role = IadsRole.POINT_DEFENSE
    battery.groups.append(guard)

    assert site_name(battery) == system_name(battery) == "SA-10"

    missiles.alive = False
    assert system_name(battery) == "SA-9"
    assert site_name(battery) == "SA-10"


def test_lines_name_two_and_count_the_rest() -> None:
    assert listed(["A"]) == "A"
    assert listed(["A", "B"]) == "A and B"
    assert listed(["A", "B", "C", "D"]) == "A, B and 2 more"


def test_money_is_written_the_way_the_game_writes_it() -> None:
    assert money(40.0) == "$40M"
    assert money(2.5) == "$2.5M"
    assert money(1219.6) == "$1220M"
