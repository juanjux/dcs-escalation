"""Exercise the real base event handler when DCS omits a kill's missile object."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def vm() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now = 0
        timer = {getTime=function() return now end}
        world = {event={}}
        for id, name in ipairs({'HIT','KILL','TAKEOFF','CRASH','DEAD','UNIT_LOST',
                'EJECTION','PLAYER_LEAVE_UNIT','MISSION_END'}) do
            world.event['S_EVENT_' .. name] = id
        end
        Unit = {Category={AIRPLANE=0,HELICOPTER=1,GROUND_UNIT=2}}
        death_time, took_off, ejected_units, player_left_units = {}, {}, {}, {}
        kill_events, kill_details, hit_details, hit_seen = {}, {}, {}, {}
        HIT_DETAIL_LIMIT = 2000
        PLAYER_LEAVE_GRACE_S = 5
        function unit(name, category)
            return {getName=function() return name end,
                    getTypeName=function() return 'F15EX' end,
                    getPlayerName=function() return nil end,
                    getDesc=function() return {category=category or 0} end}
        end
        function missile(name)
            return {getTypeName=function() return name end}
        end
        blue = unit('blue'); red = unit('red'); other = unit('other')
        sam = unit('sam', 2)
        function emit(kind, at, shooter, target, weapon)
            now = at
            handle({id=world.event['S_EVENT_' .. kind],time=at,
                    initiator=shooter,target=target,weapon=weapon})
        end
    """)
    source = Path("resources/plugins/base/dcs_retribution.lua").read_text(
        encoding="utf-8"
    )
    start = source.index("local function is_player_despawn(name)")
    end = source.index("\nif DIAG_ENABLED then", start)
    lua.execute(source[start:end] + "\nhandle = onEvent")
    return lua


def kills(vm: Any) -> list[dict[str, Any]]:
    return [dict(detail.items()) for detail in vm.globals().kill_details.values()]


@pytest.mark.parametrize(
    "missing",
    [
        "nil",
        "{}",
        "missile('')",
        "missile(nil)",
        "{getTypeName=function() error('weapon no longer exists') end}",
    ],
)
def test_missing_or_destroyed_weapon_uses_recent_impact(vm: Any, missing: str) -> None:
    vm.execute(f"""
        emit('HIT',2336.375,blue,red,missile('SP_AIM_260A'))
        emit('KILL',2338.381,blue,red,{missing})
    """)
    assert kills(vm)[0]["weapon"] == "SP_AIM_260A"


def test_ground_shooters_are_not_limited_to_aircraft_xp_hits(vm: Any) -> None:
    vm.execute("""
        emit('HIT',10,sam,red,missile('NASAMS3_AMRAAM_ER'))
        emit('KILL',11,sam,red,nil)
    """)
    assert list(vm.globals().hit_details.values()) == []
    assert kills(vm)[0]["weapon"] == "NASAMS3_AMRAAM_ER"


def test_latest_impact_wins_even_when_xp_records_only_the_first(vm: Any) -> None:
    vm.execute("""
        emit('HIT',10,blue,red,missile('SP_AIM_260A'))
        emit('HIT',20,blue,red,missile('SP_AIM_120D3'))
        emit('KILL',21,blue,red,nil)
    """)
    assert vm.globals().hit_details[1]["weapon"] == "SP_AIM_260A"
    assert kills(vm)[0]["weapon"] == "SP_AIM_120D3"


@pytest.mark.parametrize(
    "hit",
    [
        "emit('HIT',10,other,red,missile('wrong shooter'))",
        "emit('HIT',10,blue,other,missile('wrong victim'))",
        "emit('HIT',10,blue,red,missile('stale'))",
        "emit('HIT',50,blue,red,missile('future'))",
    ],
)
def test_unrelated_or_stale_hits_never_invent_a_weapon(vm: Any, hit: str) -> None:
    vm.execute(hit + "; emit('KILL',41,blue,red,nil)")
    assert "weapon" not in kills(vm)[0]


def test_explicit_kill_weapon_takes_precedence(vm: Any) -> None:
    vm.execute("""
        emit('HIT',10,blue,red,missile('old'))
        emit('KILL',11,blue,red,missile('actual'))
    """)
    assert kills(vm)[0]["weapon"] == "actual"


@pytest.mark.parametrize("at, attributed", [(40, True), (40.001, False)])
def test_hit_memory_has_a_strict_thirty_second_limit(
    vm: Any, at: float, attributed: bool
) -> None:
    vm.execute(
        "emit('HIT',10,blue,red,missile('SP_AIM_260A'));"
        f"emit('KILL',{at},blue,red,nil)"
    )
    assert (kills(vm)[0].get("weapon") == "SP_AIM_260A") is attributed


def test_friendly_fire_preserves_the_actual_shooter_and_weapon(vm: Any) -> None:
    vm.execute("""
        emit('HIT',2954.305,blue,other,missile('SP_AIM_260A'))
        emit('KILL',2955.321,blue,other,nil)
    """)
    assert kills(vm) == [
        {
            "target": "other",
            "initiator": "blue",
            "initiator_type": "F15EX",
            "weapon": "SP_AIM_260A",
        }
    ]


def test_unknown_newer_impact_invalidates_cached_weapon(vm: Any) -> None:
    vm.execute("""
        emit('HIT',10,blue,red,missile('old'))
        emit('HIT',11,blue,red,nil)
        emit('KILL',12,blue,red,nil)
    """)
    assert "weapon" not in kills(vm)[0]


def test_hits_do_not_create_kills_or_reuse_a_consumed_impact(vm: Any) -> None:
    vm.execute("emit('HIT',10,blue,red,missile('SP_AIM_260A'))")
    assert kills(vm) == []
    vm.execute("emit('KILL',11,blue,red,nil); emit('KILL',12,blue,red,nil)")
    assert kills(vm)[0]["weapon"] == "SP_AIM_260A"
    assert "weapon" not in kills(vm)[1]


def test_real_lua_export_reaches_api_weapon_summary(vm: Any) -> None:
    """The Vegas loss pattern: one intact kill weapon, one missing, then AMRAAM."""
    from game.debriefing import Debriefing
    from game.game import Game

    vm.execute("""
        emit('HIT',2119.565,blue,red,missile('SP_AIM_260A'))
        emit('KILL',2119.565,blue,red,missile('SP_AIM_260A'))
        emit('HIT',2336.375,blue,other,missile('SP_AIM_260A'))
        emit('KILL',2338.381,blue,other,nil)
        third = unit('third')
        emit('HIT',2364,blue,third,missile('SP_AIM_120D3'))
        emit('KILL',2365,blue,third,missile('SP_AIM_120D3'))
    """)
    losses = {
        name: SimpleNamespace(
            flight=SimpleNamespace(unit_type=SimpleNamespace(name=kind))
        )
        for name, kind in [("red", "FC-1"), ("other", "J-11A"), ("third", "J-11A")]
    }
    debrief = object.__new__(Debriefing)
    debrief.state_data = SimpleNamespace(kill_details=kills(vm))
    debrief.unit_map = SimpleNamespace(flight=losses.get)
    index = debrief._index_kill_details()
    summary_input = SimpleNamespace(
        air_losses=SimpleNamespace(
            enemy=list(losses.values()), player=[], by_type=lambda _: {}
        ),
        kill_info_by_unit_id=index,
        is_non_combat_loss=lambda _: False,
        front_line_losses_by_type=lambda _: {},
        ground_object_losses_by_type=lambda _: {},
    )
    game = SimpleNamespace(turn=1, debrief_history=[])
    Game.record_debrief(game, summary_input)
    assert game.debrief_history[-1]["blue_air_kills_by_weapon"] == {
        "SP_AIM_260A": 2,
        "SP_AIM_120D3": 1,
    }
