"""Exercise naval release and accounting with Lua 5.1 and DCS doubles."""

from pathlib import Path
from typing import Any

import pytest

SOURCE = Path("resources/plugins/navalmagazines/navalmagazines-config.lua")


def runtime(
    *,
    stock: int = 20,
    cap: int = 6,
    radius: float = 8.1,
    stagger: bool = True,
    metered: bool = True,
) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        groups={}; scheduled={}; messages={}; logs={}; warnings={}
        coalition={side={RED=1,BLUE=2}}
        env={
            info=function(s) logs[#logs+1]=s end,
            warning=function(s) warnings[#warnings+1]=s end,
            error=function(s) error(s) end
        }
        trigger={action={outTextForCoalition=function(side,s)
            messages[#messages+1]={side=side,text=s}
        end}}
        world={event={S_EVENT_SHOT=1,S_EVENT_HIT=2},
            addEventHandler=function(h) handler=h end}
        timer={getTime=function() return 0 end,
            scheduleFunction=function(fn,arg,t)
                scheduled[#scheduled+1]={fn=fn,arg=arg,time=t}
            end}
        Group={getByName=function(n) return groups[n] end}
        function add(name,side,x)
            local g={name=name,side=side,roe=3,calls=0,x=x,alive=true}
            function g:getName() return self.name end
            function g:isExist() return self.alive end
            function g:getController()
                return {setOption=function(_,id,value)
                    assert(id==0); g.roe=value; g.calls=g.calls+1
                end}
            end
            local u={}
            function u:getGroup() return g end
            function u:getCoalition() return g.side end
            function u:isExist() return g.alive end
            function u:getPoint() return {x=g.x,y=0,z=0} end
            function g:getUnits() return {u} end
            g.unit=u; groups[name]=g
            return g
        end
        add("target",2,0)
        add("escort",2,10000)
        add("chain",2,20000)
        add("remote",2,100000)
        add("enemy",1,1000)
        function shot(shooter,target,kind)
            local weapon={getTypeName=function() return kind or "HARPOON" end,
                getTarget=function() return target end}
            handler:onEvent({id=1,initiator=shooter,weapon=weapon})
        end
        function hit(shooter,target)
            handler:onEvent({id=2,initiator=shooter,target=target})
        end
        function shots(name,count)
            for i=1,count do shot(groups[name].unit,nil) end
        end
        function runStagger()
            for _,s in ipairs(scheduled) do s.fn(s.arg,s.time) end
        end
        function spent(name)
            for _,s in ipairs(naval_magazines_state) do
                if s.group==name then return s.fired end
            end
            return 0
        end
    """)
    lua.globals().dcsRetribution = lua.table_from(
        {
            "navalMagazines": {
                "stagger": stagger,
                "metered": metered,
                "magazines": [
                    {"group": name, "coalition": side, "remaining": stock}
                    for name, side in (
                        ("target", "blue"),
                        ("escort", "blue"),
                        ("chain", "blue"),
                        ("remote", "blue"),
                        ("enemy", "red"),
                    )
                ],
            },
            "plugins": {
                "navalmagazines": {
                    "salvoPerMission": cap,
                    "formationReleaseNm": radius,
                }
            },
        },
        recursive=True,
    )
    if not stagger:
        lua.execute("for _,g in pairs(groups) do g.roe=0 end")
    lua.execute(SOURCE.read_text())
    return lua


def test_targeted_shot_releases_only_one_friendly_formation_hop() -> None:
    lua = runtime()
    lua.execute("shot(groups.enemy.unit,groups.target.unit)")
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval("groups.escort.roe") == 0
    for name in ("chain", "remote", "enemy"):
        assert lua.eval(f"groups.{name}.roe") == 3
    assert lua.eval('spent("enemy")') == 1
    assert lua.eval("dirty_state") is True


@pytest.mark.parametrize("kind", ["AGM_65D", "GBU_12", "GUN"])
def test_any_hostile_targeted_weapon_can_release_defenders(kind: str) -> None:
    lua = runtime()
    lua.globals().kind = kind
    lua.execute("shot(groups.enemy.unit,groups.target.unit,kind)")
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval('spent("enemy")') == 0


def test_unresolved_or_friendly_shot_does_not_free_the_other_fleet() -> None:
    lua = runtime()
    lua.execute("""
        shot(groups.enemy.unit,nil)
        shot(groups.escort.unit,groups.target.unit)
        shot(groups.enemy.unit,{})
    """)
    assert lua.eval("groups.target.roe") == 3
    assert lua.eval("groups.remote.roe") == 3
    assert lua.eval("#warnings") == 0


@pytest.mark.parametrize("shooter", ["groups.enemy.unit", "nil"])
def test_hit_is_a_backstop_for_weapons_without_a_shot_target(shooter: str) -> None:
    lua = runtime()
    lua.execute(f"hit({shooter},groups.target.unit)")
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval("groups.escort.roe") == 0


def test_friendly_hit_does_not_release_and_zero_radius_frees_only_target() -> None:
    lua = runtime(radius=0)
    lua.execute("hit(groups.escort.unit,groups.target.unit)")
    assert lua.eval("groups.target.roe") == 3
    lua.execute("hit(groups.enemy.unit,groups.target.unit)")
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval("groups.escort.roe") == 3


def test_missing_destroyed_groups_and_non_unit_targets_are_safe() -> None:
    lua = runtime()
    lua.execute("""
        groups.escort.alive=false
        groups.chain=nil
        hit(groups.enemy.unit,{getGroup=function() error("not a unit") end})
        shot({},groups.target.unit)
        hit(groups.enemy.unit,groups.target.unit)
    """)
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval("#warnings") == 0


def test_salvo_limit_holds_group_and_is_fresh_in_each_mission() -> None:
    for _ in range(2):
        lua = runtime()
        lua.execute('runStagger(); shots("target",5)')
        assert lua.eval("groups.target.roe") == 0
        lua.execute('shots("target",1)')
        assert lua.eval("groups.target.roe") == 3
        assert lua.eval('spent("target")') == 6
        # Scheduled release cannot reopen a spent salvo.
        lua.execute("runStagger()")
        assert lua.eval("groups.target.roe") == 3


def test_attack_overrides_spent_salvo_and_all_real_shots_are_counted() -> None:
    lua = runtime()
    lua.execute("""
        runStagger(); shots("target",6)
        hit(groups.enemy.unit,groups.target.unit)
        shots("target",3); runStagger()
    """)
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval('spent("target")') == 9


def test_dry_stock_is_held_but_defensive_overshoot_is_bounded_and_counted() -> None:
    lua = runtime(stock=2, cap=3, stagger=False)
    lua.execute('shots("target",2)')
    assert lua.eval("groups.target.roe") == 3
    lua.execute("hit(groups.enemy.unit,groups.target.unit)")
    assert lua.eval("groups.target.roe") == 0
    lua.execute('shots("target",2)')
    assert lua.eval("groups.target.roe") == 0
    lua.execute('shots("target",1)')
    assert lua.eval("groups.target.roe") == 3
    assert lua.eval('spent("target")') == 5
    assert lua.eval("#messages") == 1
    # Duplicate events and the stagger cannot reset the defensive allowance.
    lua.execute("hit(groups.enemy.unit,groups.target.unit); runStagger()")
    assert lua.eval("groups.target.roe") == 3


@pytest.mark.parametrize("stagger", [False, True])
def test_stock_empty_at_start_stays_held_until_attacked(stagger: bool) -> None:
    lua = runtime(stock=0, stagger=stagger)
    lua.execute("runStagger()")
    assert lua.eval("groups.target.roe") == 3
    lua.execute("hit(groups.enemy.unit,groups.target.unit)")
    assert lua.eval("groups.target.roe") == 0


def test_zero_salvo_limit_disables_offensive_and_overshoot_caps() -> None:
    lua = runtime(stock=0, cap=0)
    lua.execute("""
        hit(groups.enemy.unit,groups.target.unit)
        shots("target",30)
    """)
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval('spent("target")') == 30
    assert lua.eval("#messages") == 1


def test_metering_off_keeps_salvo_limit_but_does_not_debit_campaign() -> None:
    lua = runtime(metered=False, cap=2)
    lua.execute('runStagger(); shots("target",2)')
    assert lua.eval("groups.target.roe") == 3
    assert lua.eval('spent("target")') == 0
    lua.execute('hit(groups.enemy.unit,groups.target.unit); shots("target",2)')
    assert lua.eval("groups.target.roe") == 0
    assert lua.eval("#naval_magazines_state") == 0


@pytest.mark.parametrize("kind", ["BGM_109B", "3M14", "SM_2", "R_77"])
def test_land_attack_and_air_defence_shots_never_consume_anti_ship_stock(
    kind: str,
) -> None:
    lua = runtime(cap=1)
    lua.globals().kind = kind
    lua.execute("runStagger(); shot(groups.target.unit,nil,kind)")
    assert lua.eval('spent("target")') == 0
    assert lua.eval("groups.target.roe") == 0


def test_stagger_is_evenly_spaced_and_attack_release_is_idempotent() -> None:
    lua = runtime()
    assert lua.eval("scheduled[1].time") == 120
    assert lua.eval("scheduled[5].time") == 900
    lua.execute("hit(groups.enemy.unit,groups.target.unit)")
    calls = lua.eval("groups.target.calls")
    lua.execute("hit(groups.enemy.unit,groups.target.unit); runStagger()")
    assert lua.eval("groups.target.calls") == calls
    assert lua.eval("#warnings") == 0


def test_plugin_defaults_and_existing_setting_values_are_preserved() -> None:
    from game.plugins import LuaPluginManager
    from game.settings import Settings

    settings = Settings()
    settings.plugins["navalmagazines.releaseStagger"] = True
    LuaPluginManager.load_settings(settings)
    assert settings.plugins["navalmagazines.salvoPerMission"] == 6
    assert settings.plugins["navalmagazines.formationReleaseNm"] == 8.1
    assert settings.plugins["navalmagazines.releaseStagger"] is True
