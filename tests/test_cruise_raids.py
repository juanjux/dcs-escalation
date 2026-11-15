"""Ship-launched cruise missile raids: planner, magazines, reconciliation.

Locks the campaign contract. The magazine is finite and one-way: only the debrief
report ever moves it, so a mission the player regenerates five times still costs one
salvo; it never grows back; and it survives a save/load. The auto raid is at most one
per side, prefers command and control over a closer cheap target, respects the range
gate, never shoots at ships, and does nothing at all with the settings off.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game.cruise_raids import (
    DEFAULT_MAGAZINE_PER_SHIP,
    LACM_MAGAZINE_BY_TYPE,
    MAX_RAID_RANGE_M,
    RAID_SALVO,
    debrief_expenditures,
    lacm_ships,
    magazines,
    plan_cruise_raids,
    player_briefing_info,
    reconcile_cruise_missiles,
    remaining_missiles,
    tgo_magazines,
)
from game.theater import Player

BURKE = "USS_Arleigh_Burke_IIa"
KARAKURT = "CH_Karakurt_LACM"


class _Pos:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def distance_to_point(self, other: "_Pos") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


def _unit(type_id: str, alive: bool = True) -> Any:
    return SimpleNamespace(alive=alive, type=SimpleNamespace(id=type_id))


def _ship_tgo(
    name: str, owner_cp: Any, pos: _Pos, units: list[Any], group_name: str
) -> Any:
    return SimpleNamespace(
        category="ship",
        name=name,
        position=pos,
        control_point=owner_cp,
        groups=[SimpleNamespace(group_name=group_name, units=units)],
        units=units,
        is_control_point=False,
    )


def _carrier_tgo(
    name: str, owner_cp: Any, pos: _Pos, units: list[Any], group_name: str
) -> Any:
    # A CVN/LHA task force: category CARRIER (upper case, unlike "ship") and
    # is_control_point True. This is where a vanilla Burke usually lives, as an escort.
    return SimpleNamespace(
        category="CARRIER",
        name=name,
        position=pos,
        control_point=owner_cp,
        groups=[SimpleNamespace(group_name=group_name, units=units)],
        units=units,
        is_control_point=True,
    )


def _target_tgo(name: str, category: str, pos: _Pos, *, alive: bool = True) -> Any:
    units = [SimpleNamespace(alive=alive, type=SimpleNamespace(id="Generator"))]
    return SimpleNamespace(
        category=category,
        name=name,
        position=pos,
        groups=[SimpleNamespace(group_name=name, units=units)],
        units=units,
        is_control_point=False,
    )


def _settings(options: dict[str, Any]) -> Any:
    """A settings stub that answers plugin_option_or and nothing else."""
    return SimpleNamespace(
        plugin_option_or=lambda identifier, default=None: options.get(
            identifier, default
        )
    )


def _cp(owner: Player) -> Any:
    return SimpleNamespace(captured=owner, ground_objects=[])


def _game(cps: list[Any], *, master: bool = True, auto: bool = True) -> Any:
    return SimpleNamespace(
        theater=SimpleNamespace(controlpoints=cps),
        # Both switches live on the cruisemissiles plugin now.
        settings=_settings(
            {"cruisemissiles": master, "cruisemissiles.autoRaids": auto}
        ),
        cruise_missile_magazines={},
    )


def _blue_burke(
    pos: _Pos = _Pos(0.0, 0.0), group: str = "0001 | CVBG Burke"
) -> tuple[Any, Any]:
    cp = _cp(Player.BLUE)
    tgo = _ship_tgo("Burke DDG", cp, pos, [_unit(BURKE)], group)
    cp.ground_objects.append(tgo)
    return cp, tgo


def _fired(*rows: tuple[str, int]) -> Any:
    return SimpleNamespace(state_data=SimpleNamespace(cruise_missiles_state=list(rows)))


BURKE_GROUP = "0001 | CVBG Burke"


def test_an_untouched_group_reports_the_stock_its_living_hulls_carry() -> None:
    cp, tgo = _blue_burke()
    game = _game([cp])
    group = tgo.groups[0]
    assert remaining_missiles(cast(Any, game), group) == LACM_MAGAZINE_BY_TYPE[BURKE]
    # Reading it does not persist anything: nothing has been spent yet.
    assert magazines(cast(Any, game)) == {}


def test_an_unknown_hull_in_the_curated_set_still_gets_a_magazine() -> None:
    # Defensive: an id added to LACM_SHIP_DCS_IDS without a table row must not seed a
    # launcher with nothing to launch.
    cp = _cp(Player.BLUE)
    tgo = _ship_tgo(
        "Fleet",
        cp,
        _Pos(0, 0),
        [_unit(BURKE), _unit("PERRY")],  # the non-launching escort contributes nothing
        "0002 | Fleet",
    )
    cp.ground_objects.append(tgo)
    game = _game([cp])
    assert (
        remaining_missiles(cast(Any, game), tgo.groups[0])
        == LACM_MAGAZINE_BY_TYPE[BURKE]
    )
    assert DEFAULT_MAGAZINE_PER_SHIP > 0


def test_expenditure_depletes_the_magazine_and_floors_at_zero() -> None:
    cp, _ = _blue_burke()
    game = _game([cp])

    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, 5)))
    mags = magazines(cast(Any, game))
    assert mags[BURKE_GROUP] == LACM_MAGAZINE_BY_TYPE[BURKE] - 5

    # A second mission spends more from the same, already reduced, stock.
    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, 4)))
    assert mags[BURKE_GROUP] == LACM_MAGAZINE_BY_TYPE[BURKE] - 9

    # An over-report (or simply firing everything) floors at zero, never negative.
    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, 999)))
    assert mags[BURKE_GROUP] == 0

    # And a dry group drops off the shooter list entirely.
    assert lacm_ships(cast(Any, game)) == []


def test_the_magazine_never_grows_back() -> None:
    cp, tgo = _blue_burke()
    game = _game([cp])
    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, 10)))
    spent = LACM_MAGAZINE_BY_TYPE[BURKE] - 10

    # No turn boundary, no repair and no re-read tops it back up: a mission that fires
    # nothing reports nothing, and reads are pure.
    for _ in range(3):
        lacm_ships(cast(Any, game))
        plan_cruise_raids(cast(Any, game))
        reconcile_cruise_missiles(cast(Any, game), _fired())
    assert magazines(cast(Any, game))[BURKE_GROUP] == spent
    assert remaining_missiles(cast(Any, game), tgo.groups[0]) == spent


def test_regenerating_a_mission_never_double_debits() -> None:
    from game.missiongenerator.cruisemissileluadata import populate_cruise_missiles_lua
    from game.missiongenerator.luagenerator import LuaData

    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _target_tgo("Division HQ", "commandcenter", _Pos(100_000.0, 0.0))
    )
    game = _game([blue_cp, red_cp])

    # Everything the player triggers by hitting "generate mission" again and again:
    # the planner, the Lua emitter, the briefing. None of it may touch the magazine.
    for _ in range(5):
        plans = plan_cruise_raids(cast(Any, game))
        populate_cruise_missiles_lua(LuaData("dcsRetribution"), cast(Any, game))
        player_briefing_info(cast(Any, game))
        assert [(r.group_name, r.missiles) for r in plans] == [
            (BURKE_GROUP, RAID_SALVO)
        ]
        assert magazines(cast(Any, game)) == {}

    # Only the debrief charges, and it charges once for the salvo that actually flew.
    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, RAID_SALVO)))
    assert magazines(cast(Any, game)) == {
        BURKE_GROUP: LACM_MAGAZINE_BY_TYPE[BURKE] - RAID_SALVO
    }

    # Regenerating the NEXT mission is free too, and plans off the reduced stock.
    for _ in range(3):
        plan_cruise_raids(cast(Any, game))
        populate_cruise_missiles_lua(LuaData("dcsRetribution"), cast(Any, game))
        assert magazines(cast(Any, game)) == {
            BURKE_GROUP: LACM_MAGAZINE_BY_TYPE[BURKE] - RAID_SALVO
        }


def test_magazines_survive_a_save_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    from game.game import Game

    # __setstate__ is the load half of the pickle round trip; on_load rebuilds derived
    # state we do not need here.
    monkeypatch.setattr(Game, "on_load", lambda self: None)
    base_state = {
        "theater": SimpleNamespace(conflicts=lambda: []),
        "laser_code_registry": object(),
        "stored_context": {},
        "debrief_history": [],
        "client_map_layers": None,
        "opfor_ai_token": "token",
    }

    loaded = cast(Any, object.__new__(Game))
    loaded.__setstate__(dict(base_state, cruise_missile_magazines={BURKE_GROUP: 7}))
    assert loaded.cruise_missile_magazines == {BURKE_GROUP: 7}

    # A campaign saved before the feature existed loads with an empty magazine store
    # rather than an AttributeError, and its ships start with full tubes.
    legacy = cast(Any, object.__new__(Game))
    legacy.__setstate__(dict(base_state))
    assert legacy.cruise_missile_magazines == {}


def test_lacm_ships_lists_both_sides_and_skips_sunk_hulls() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _ship_tgo(
            "Karakurt", red_cp, _Pos(10.0, 10.0), [_unit(KARAKURT)], "0003 | Corvette"
        )
    )
    sunk_cp = _cp(Player.RED)
    sunk_cp.ground_objects.append(
        _ship_tgo(
            "Sunk",
            sunk_cp,
            _Pos(0, 0),
            [_unit(KARAKURT, alive=False)],
            "0004 | Sunk Corvette",
        )
    )
    game = _game([blue_cp, red_cp, sunk_cp])
    assert {(s.group_name, s.coalition) for s in lacm_ships(cast(Any, game))} == {
        (BURKE_GROUP, "blue"),
        ("0003 | Corvette", "red"),
    }


def test_a_launcher_sunk_before_it_fires_takes_its_missiles_down_with_it() -> None:
    cp = _cp(Player.BLUE)
    tgo = _ship_tgo("Pair", cp, _Pos(0, 0), [_unit(BURKE), _unit(BURKE)], "0005 | Pair")
    cp.ground_objects.append(tgo)
    game = _game([cp])
    assert (
        remaining_missiles(cast(Any, game), tgo.groups[0])
        == 2 * LACM_MAGAZINE_BY_TYPE[BURKE]
    )

    tgo.groups[0].units[1].alive = False
    assert (
        remaining_missiles(cast(Any, game), tgo.groups[0])
        == LACM_MAGAZINE_BY_TYPE[BURKE]
    )


def test_raid_prefers_c2_over_a_closer_low_value_target() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(_target_tgo("Cache", "ammo", _Pos(10_000.0, 0.0)))
    red_cp.ground_objects.append(
        _target_tgo("Division HQ", "commandcenter", _Pos(200_000.0, 0.0))
    )
    raids = plan_cruise_raids(cast(Any, _game([blue_cp, red_cp])))

    assert len(raids) == 1
    raid = raids[0]
    assert (raid.target_name, raid.group_name, raid.coalition) == (
        "Division HQ",
        BURKE_GROUP,
        "blue",
    )
    assert raid.missiles == RAID_SALVO
    assert (raid.target_x, raid.target_y) == (200_000.0, 0.0)


def test_raid_salvo_is_capped_by_the_remaining_magazine() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(_target_tgo("Depot", "ware", _Pos(10_000.0, 0.0)))
    game = _game([blue_cp, red_cp])
    reconcile_cruise_missiles(
        cast(Any, game), _fired((BURKE_GROUP, LACM_MAGAZINE_BY_TYPE[BURKE] - 2))
    )
    assert [r.missiles for r in plan_cruise_raids(cast(Any, game))] == [2]


def test_raid_honors_the_range_gate() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _target_tgo("Too far", "commandcenter", _Pos(MAX_RAID_RANGE_M + 1_000.0, 0.0))
    )
    assert plan_cruise_raids(cast(Any, _game([blue_cp, red_cp]))) == []


def test_raid_never_targets_ships_control_points_or_dead_objects() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _ship_tgo(
            "Red fleet", red_cp, _Pos(5_000.0, 0.0), [_unit(KARAKURT)], "0006 | Fleet"
        )
    )
    red_cp.ground_objects.append(
        _target_tgo("Rubble", "factory", _Pos(7_000.0, 0.0), alive=False)
    )
    fob = _target_tgo("FOB", "fob", _Pos(8_000.0, 0.0))
    fob.is_control_point = True
    red_cp.ground_objects.append(fob)
    game = _game([blue_cp, red_cp])
    # The red corvette has nothing legal to shoot at either (blue owns only a ship), so
    # neither side raids.
    assert plan_cruise_raids(cast(Any, game)) == []


def test_red_raids_blue_symmetrically() -> None:
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _ship_tgo(
            "Karakurt", red_cp, _Pos(0.0, 0.0), [_unit(KARAKURT)], "0007 | Corvette"
        )
    )
    blue_cp = _cp(Player.BLUE)
    blue_cp.ground_objects.append(
        _target_tgo("Power plant", "power", _Pos(50_000.0, 0.0))
    )
    raids = plan_cruise_raids(cast(Any, _game([red_cp, blue_cp])))
    assert [(r.coalition, r.target_name) for r in raids] == [("red", "Power plant")]


def test_fully_gated_by_the_two_settings() -> None:
    blue_cp, tgo = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _target_tgo("HQ", "commandcenter", _Pos(10_000.0, 0.0))
    )
    assert plan_cruise_raids(cast(Any, _game([blue_cp, red_cp], master=False))) == []
    assert plan_cruise_raids(cast(Any, _game([blue_cp, red_cp], auto=False))) == []
    assert (
        tgo_magazines(cast(Any, _game([blue_cp], master=False)), cast(Any, tgo)) == []
    )


def test_reconcile_ignores_stale_and_empty_reports() -> None:
    cp, _ = _blue_burke()
    game = _game([cp])
    reconcile_cruise_missiles(
        cast(Any, game), _fired(("Ghost ship", 3), (BURKE_GROUP, 0))
    )
    assert magazines(cast(Any, game)) == {}

    # A state file written before the feature carries no such attribute at all.
    reconcile_cruise_missiles(
        cast(Any, game), cast(Any, SimpleNamespace(state_data=SimpleNamespace()))
    )
    assert magazines(cast(Any, game)) == {}


def test_carrier_escort_burkes_are_launching_groups() -> None:
    # The walk must not gate on category == "ship": Burkes escorting a CVN live in a
    # "CARRIER" TGO, which is the vanilla Burke's usual home.
    cp = _cp(Player.BLUE)
    cp.ground_objects.append(
        _carrier_tgo(
            "CVN-73 Washington",
            cp,
            _Pos(0.0, 0.0),
            [_unit("CVN_73"), _unit(BURKE), _unit(BURKE)],
            "0008 | CVN-73 Washington",
        )
    )
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _target_tgo("Division HQ", "commandcenter", _Pos(100_000.0, 0.0))
    )
    game = _game([cp, red_cp])

    ships = lacm_ships(cast(Any, game))
    # The magazine counts the two escorts and never the carrier itself.
    assert [(s.group_name, s.remaining) for s in ships] == [
        ("0008 | CVN-73 Washington", 2 * LACM_MAGAZINE_BY_TYPE[BURKE])
    ]
    assert [r.group_name for r in plan_cruise_raids(cast(Any, game))] == [
        "0008 | CVN-73 Washington"
    ]


def test_carrier_task_forces_are_never_raid_targets() -> None:
    # A moving naval group is a FireAtPoint's blind spot; ANTISHIP owns it.
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _carrier_tgo(
            "Kuznetsov Group",
            red_cp,
            _Pos(50_000.0, 0.0),
            [_unit("KUZNECOW"), _unit(KARAKURT)],
            "0009 | Kuznetsov Group",
        )
    )
    game = _game([blue_cp, red_cp])
    assert plan_cruise_raids(cast(Any, game)) == []
    assert {s.coalition for s in lacm_ships(cast(Any, game))} == {"blue", "red"}


def test_player_briefing_info_is_blue_side_and_gated() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _ship_tgo(
            "Karakurt", red_cp, _Pos(0.0, 0.0), [_unit(KARAKURT)], "0010 | Corvette"
        )
    )
    red_cp.ground_objects.append(
        _target_tgo("HQ", "commandcenter", _Pos(10_000.0, 0.0))
    )

    ships, raids = player_briefing_info(cast(Any, _game([blue_cp, red_cp])))
    assert [s.group_name for s in ships] == [
        BURKE_GROUP
    ]  # the red corvette is not ours
    assert [(r.group_name, r.target_name) for r in raids] == [(BURKE_GROUP, "HQ")]

    # Auto-raids off: the magazine still briefs (the F10 call-for-fire needs it), the
    # raid does not. Master off: the briefing section renders nothing at all.
    ships, raids = player_briefing_info(cast(Any, _game([blue_cp, red_cp], auto=False)))
    assert ships and raids == []
    assert player_briefing_info(cast(Any, _game([blue_cp, red_cp], master=False))) == (
        [],
        [],
    )


def test_tgo_magazines_rows_for_the_ground_object_dialog() -> None:
    blue_cp, tgo = _blue_burke()
    game = _game([blue_cp])
    assert tgo_magazines(cast(Any, game), cast(Any, tgo)) == [
        (BURKE_GROUP, LACM_MAGAZINE_BY_TYPE[BURKE])
    ]

    # The dialog reads the live campaign magazine, so expenditure shows through.
    reconcile_cruise_missiles(cast(Any, game), _fired((BURKE_GROUP, 21)))
    assert tgo_magazines(cast(Any, game), cast(Any, tgo)) == [(BURKE_GROUP, 3)]

    # A target ashore contributes no rows.
    target = _target_tgo("HQ", "commandcenter", _Pos(0.0, 0.0))
    assert tgo_magazines(cast(Any, game), cast(Any, target)) == []


def test_debrief_expenditures_hides_enemy_remainders() -> None:
    blue_cp, _ = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _ship_tgo(
            "Karakurt", red_cp, _Pos(0.0, 0.0), [_unit(KARAKURT)], "0011 | Corvette"
        )
    )
    game = _game([blue_cp, red_cp])
    debriefing = _fired(
        (BURKE_GROUP, 6),
        ("0011 | Corvette", 4),
        ("0012 | Silent ship", 0),  # never fired: not a debrief row
    )
    # The debrief window opens after the turn-boundary debit.
    reconcile_cruise_missiles(cast(Any, game), debriefing)
    assert debrief_expenditures(cast(Any, game), debriefing) == [
        (BURKE_GROUP, 6, LACM_MAGAZINE_BY_TYPE[BURKE] - 6),
        ("0011 | Corvette", 4, None),  # what the enemy has left stays hidden
    ]


def test_raid_targets_and_shooters_get_culling_exclusions() -> None:
    # The auto raid usually hits a rear-area TGO no package is fragged against. Culled,
    # the target is never generated and the salvo demolishes bare map scenery while the
    # campaign records nothing, so the zone pass must un-cull raid targets and shooters.
    from game.game import Game

    blue_cp, ship_tgo = _blue_burke()
    red_cp = _cp(Player.RED)
    red_cp.ground_objects.append(
        _target_tgo("Refinery", "factory", _Pos(100_000.0, 0.0))
    )
    game = _game([blue_cp, red_cp])
    game.theater.conflicts = lambda: []
    game.theater.player_points = lambda: []
    game.theater.enemy_points = lambda: []
    game.theater.terrain = None
    game.settings.perf_do_not_cull_carrier = False
    game.blue = SimpleNamespace(ato=SimpleNamespace(packages=[]))
    game.red = SimpleNamespace(ato=SimpleNamespace(packages=[]))
    captured: list[Any] = []
    events = SimpleNamespace(update_unculled_zones=captured.append)

    Game.compute_unculled_zones(cast(Any, game), cast(Any, events))

    zones = captured[0]
    assert any(
        getattr(z, "x", None) == 100_000.0 and getattr(z, "y", None) == 0.0
        for z in zones
    ), "the planned raid target must be un-culled"
    assert ship_tgo.position in zones, "the launching ship must be un-culled"

    # Feature off: the zone pass contributes nothing.
    game.settings = _settings({"cruisemissiles": False})
    game.settings.perf_do_not_cull_carrier = False
    captured.clear()
    Game.compute_unculled_zones(cast(Any, game), cast(Any, events))
    assert captured[0] == []
