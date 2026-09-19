"""cross-turn naval magazines — the campaign side.

Pins the contract that makes the magazine safe to ship: capacity is seeded once
per group and never re-upped (so expenditure persists), the ONLY debit site is
the plugin's debrief report (so re-generating a mission is free), and the
anti-ship weapon patterns never overlap 's land-attack families (so a shot is
never charged to both magazines).
"""

from __future__ import annotations

from typing import Any

import pytest

from game.cruise_raids import LACM_MAGAZINE_BY_TYPE
from game.naval_magazines import (
    ASHM_MAGAZINE_BY_TYPE,
    ASHM_WEAPON_PATTERNS,
    DEFAULT_MAGAZINE_PER_SHIP,
    ensure_magazines,
    magazines,
    naval_group_magazines,
    reconcile_naval_magazines,
    tgo_magazines,
    winchester_lines,
)


class _Type:
    def __init__(self, dcs_id: str) -> None:
        self.id = dcs_id


class _Unit:
    def __init__(self, dcs_id: str, alive: bool = True) -> None:
        self.type = _Type(dcs_id)
        self.alive = alive


class _Group:
    def __init__(self, group_name: str, units: list[_Unit]) -> None:
        self.group_name = group_name
        self.units = units


class _Captured:
    def __init__(self, blue: bool) -> None:
        self.is_blue = blue
        self.is_red = not blue


class _ControlPointRef:
    def __init__(self, blue: bool) -> None:
        self.captured = _Captured(blue)


class _Tgo:
    def __init__(
        self, category: str, groups: list[_Group], blue: bool = True, name: str = "tgo"
    ) -> None:
        self.category = category
        self.groups = groups
        self.name = name
        self.control_point = _ControlPointRef(blue)


class _ControlPoint:
    def __init__(self, ground_objects: list[_Tgo]) -> None:
        self.ground_objects = ground_objects


class _Theater:
    def __init__(self, controlpoints: list[_ControlPoint]) -> None:
        self.controlpoints = controlpoints


class _Settings:
    def __init__(self, **kwargs: Any) -> None:
        # Both switches are navalmagazines plugin options now.
        self._options = {
            "navalmagazines": kwargs.get("naval_magazines", True),
            "navalmagazines.releaseStagger": kwargs.get("stagger", False),
        }

    def plugin_option_or(self, identifier: str, default: Any = None) -> Any:
        return self._options.get(identifier, default)

    def set_naval_magazines(self, value: bool) -> None:
        self._options["navalmagazines"] = value


class _Game:
    def __init__(self, tgos: list[_Tgo], **settings: Any) -> None:
        self.theater = _Theater([_ControlPoint(tgos)])
        self.settings = _Settings(**settings)
        self.naval_magazines: dict[str, int] = {}


class _StateData:
    def __init__(self, reports: list[tuple[str, int]]) -> None:
        self.naval_magazines_state = reports


class _Debriefing:
    def __init__(self, reports: list[tuple[str, int]]) -> None:
        self.state_data = _StateData(reports)


def _burke_group(name: str = "0001 | CSG", count: int = 1) -> _Group:
    return _Group(name, [_Unit("USS_Arleigh_Burke_IIa") for _ in range(count)])


def test_capacity_sums_the_groups_alive_hulls_from_the_table() -> None:
    game = _Game([_Tgo("ship", [_burke_group(count=3)])])
    ensure_magazines(game)  # type: ignore[arg-type]
    seeded = magazines(game)["0001 | CSG"]  # type: ignore[arg-type]
    assert seeded == 3 * ASHM_MAGAZINE_BY_TYPE["USS_Arleigh_Burke_IIa"]


def test_an_unlisted_hull_uses_the_default_and_a_dead_one_is_not_counted() -> None:
    group = _Group(
        "0002 | Screen",
        [_Unit("SOME_MOD_FRIGATE"), _Unit("USS_Arleigh_Burke_IIa", alive=False)],
    )
    game = _Game([_Tgo("ship", [group])])
    ensure_magazines(game)  # type: ignore[arg-type]
    assert magazines(game)["0002 | Screen"] == DEFAULT_MAGAZINE_PER_SHIP  # type: ignore[arg-type]


def test_seeding_is_idempotent_so_expenditure_persists() -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    magazines(game)["0001 | CSG"] = 2  # type: ignore[arg-type]
    ensure_magazines(game)  # type: ignore[arg-type]
    assert magazines(game)["0001 | CSG"] == 2  # type: ignore[arg-type]


def test_carrier_and_lha_task_forces_carry_magazines_too() -> None:
    game = _Game(
        [
            _Tgo("CARRIER", [_burke_group("0003 | CVN escort")]),
            _Tgo("LHA", [_burke_group("0004 | ARG escort")]),
            _Tgo("aa", [_burke_group("0005 | not naval")]),
        ]
    )
    names = {m.group_name for m in naval_group_magazines(game)}  # type: ignore[arg-type]
    assert names == {"0003 | CVN escort", "0004 | ARG escort"}


def test_a_dry_group_is_still_emitted_so_the_plugin_can_hold_it() -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    magazines(game)["0001 | CSG"] = 0  # type: ignore[arg-type]
    emitted = naval_group_magazines(game)  # type: ignore[arg-type]
    assert [(m.group_name, m.remaining) for m in emitted] == [("0001 | CSG", 0)]


def test_coalition_key_follows_the_owning_control_point() -> None:
    game = _Game(
        [
            _Tgo("ship", [_burke_group("0001 | Blue")], blue=True),
            _Tgo("ship", [_burke_group("0002 | Red")], blue=False),
        ]
    )
    sides = {m.group_name: m.coalition for m in naval_group_magazines(game)}  # type: ignore[arg-type]
    assert sides == {"0001 | Blue": "blue", "0002 | Red": "red"}


def test_the_debrief_report_is_the_only_debit_site() -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    before = magazines(game)["0001 | CSG"]  # type: ignore[arg-type]
    # Emitting (what generation does) must never move the magazine.
    naval_group_magazines(game)  # type: ignore[arg-type]
    naval_group_magazines(game)  # type: ignore[arg-type]
    assert magazines(game)["0001 | CSG"] == before  # type: ignore[arg-type]

    reconcile_naval_magazines(game, _Debriefing([("0001 | CSG", 3)]))  # type: ignore[arg-type]
    assert magazines(game)["0001 | CSG"] == before - 3  # type: ignore[arg-type]


def test_reconcile_clamps_at_zero_and_ignores_unknown_groups() -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    debriefing = _Debriefing([("0001 | CSG", 999), ("ghost from an old save", 4)])
    reconcile_naval_magazines(game, debriefing)  # type: ignore[arg-type]
    assert magazines(game)["0001 | CSG"] == 0  # type: ignore[arg-type]
    assert "ghost from an old save" not in magazines(game)  # type: ignore[arg-type]


@pytest.mark.parametrize("reports", [[], None])
def test_an_unflown_mission_costs_nothing(reports: Any) -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    before = dict(magazines(game))  # type: ignore[arg-type]
    reconcile_naval_magazines(game, _Debriefing(reports))  # type: ignore[arg-type]
    assert magazines(game) == before  # type: ignore[arg-type]


def test_tgo_magazines_is_gated_and_naval_only() -> None:
    tgo = _Tgo("ship", [_burke_group()])
    game = _Game([tgo])
    assert tgo_magazines(game, tgo) == [("0001 | CSG", 8)]  # type: ignore[arg-type]

    game.settings.set_naval_magazines(False)
    assert tgo_magazines(game, tgo) == []  # type: ignore[arg-type]

    game.settings.set_naval_magazines(True)
    assert tgo_magazines(game, _Tgo("aa", [_burke_group()])) == []  # type: ignore[arg-type]


def test_winchester_lines_report_blue_only_and_name_the_dry_group() -> None:
    game = _Game(
        [
            _Tgo("ship", [_burke_group("0001 | Blue")], blue=True),
            _Tgo("ship", [_burke_group("0002 | Red")], blue=False),
        ]
    )
    ensure_magazines(game)  # type: ignore[arg-type]
    debriefing = _Debriefing([("0001 | Blue", 8), ("0002 | Red", 8)])
    reconcile_naval_magazines(game, debriefing)  # type: ignore[arg-type]
    lines = winchester_lines(game, debriefing)  # type: ignore[arg-type]
    assert len(lines) == 1
    assert "0001 | Blue" in lines[0]
    assert "WINCHESTER" in lines[0]


def test_a_partial_expenditure_reports_the_remaining_stock() -> None:
    game = _Game([_Tgo("ship", [_burke_group()])])
    ensure_magazines(game)  # type: ignore[arg-type]
    debriefing = _Debriefing([("0001 | CSG", 3)])
    reconcile_naval_magazines(game, debriefing)  # type: ignore[arg-type]
    (line,) = winchester_lines(game, debriefing)  # type: ignore[arg-type]
    assert "3 anti-ship missile(s) fired, 5 left" in line
    assert "WINCHESTER" not in line


def test_the_antiship_patterns_never_match_a_land_attack_cruise_missile() -> None:
    """The /disjointness guarantee: neither magazine may charge the other's
    shot. The land-attack families are the ones  meters."""
    land_attack = [
        "BGM_109B",
        "BGM_109",
        "weapons.missiles.BGM_109B",
        "3M14",
        "KALIBR_3M14",
    ]
    for weapon in land_attack:
        upper = weapon.upper()
        assert not any(
            pattern in upper for pattern in ASHM_WEAPON_PATTERNS
        ), f"{weapon} would be charged to BOTH magazines"


def test_known_antiship_weapons_do_match() -> None:
    for weapon in [
        "weapons.missiles.AGM_84D",
        "RGM_84F_Harpoon",
        "CH_YJ18",
        "YJ-83",
        "P_700",
        "Kh_35",
        "3M54",
        "MM_40 Exocet",
    ]:
        upper = weapon.upper()
        assert any(pattern in upper for pattern in ASHM_WEAPON_PATTERNS), weapon


def test_the_two_magazines_meter_different_things_on_shared_hulls() -> None:
    """A Burke appears in both hull tables on purpose — it carries Tomahawks AND
    Harpoons. That is fine precisely because the WEAPON sets are disjoint."""
    shared = set(ASHM_MAGAZINE_BY_TYPE) & set(LACM_MAGAZINE_BY_TYPE)
    assert "USS_Arleigh_Burke_IIa" in shared


def test_the_release_order_alternates_the_two_sides() -> None:
    """The stagger spreads releases by position in this list, so a list sorted by
    coalition is a head start rather than a stagger: on Gran Polvorin every red group
    went weapons-free between two and eight minutes and every blue one between ten
    and fifteen, and red opened fire with blue still on ReturnFire."""
    from game.naval_magazines import NavalGroupMagazine, _by_turns

    def group(side: str, number: int) -> NavalGroupMagazine:
        return NavalGroupMagazine(f"{side}{number}", side, 10)

    sorted_by_side = [group("red", n) for n in range(1, 7)] + [
        group("blue", n) for n in range(1, 6)
    ]

    ordered = _by_turns(sorted_by_side)

    assert [one.coalition for one in ordered] == [
        "red",
        "blue",
        "red",
        "blue",
        "red",
        "blue",
        "red",
        "blue",
        "red",
        "blue",
        "red",
    ]


def test_one_side_alone_keeps_every_slot() -> None:
    from game.naval_magazines import NavalGroupMagazine, _by_turns

    only_red = [NavalGroupMagazine(f"red{n}", "red", 10) for n in range(3)]

    assert [one.group_name for one in _by_turns(only_red)] == [
        "red0",
        "red1",
        "red2",
    ]
