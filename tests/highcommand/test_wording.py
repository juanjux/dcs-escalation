"""How the High Command's lines name things."""

from __future__ import annotations

from game.data.units import UnitClass
from game.highcommand.wording import listed, money, system_name
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


def test_lines_name_two_and_count_the_rest() -> None:
    assert listed(["A"]) == "A"
    assert listed(["A", "B"]) == "A and B"
    assert listed(["A", "B", "C", "D"]) == "A, B and 2 more"


def test_money_is_written_the_way_the_game_writes_it() -> None:
    assert money(40.0) == "$40M"
    assert money(2.5) == "$2.5M"
    assert money(1219.6) == "$1220M"
