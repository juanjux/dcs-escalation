"""Execute health tracking in Lua 5.1 with modeled DCS objects and APIs."""

from pathlib import Path
from typing import Any

import pytest


def runtime(bridge_only: bool = False) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now=0; objects={}; warnings={}; messages={}; scheduled={}; calls={}
        env={warning=function(text) warnings[#warnings+1]=text end}
        trigger={action={outText=function(text) messages[#messages+1]=text end}}
        timer={getTime=function() return now end, scheduleFunction=function(fn,arg,t) scheduled[#scheduled+1]=fn end}
        Unit={getByName=function(name) return objects[name] end}
        StaticObject={getByName=function(name) return objects[name] end}
        Object={Category={SCENERY=5}}; world={VolumeType={SPHERE=1}}
        land={getHeight=function() return 0 end}
        world.searchObjects=function(category, volume, visit)
            for _, obj in pairs(objects) do if obj.scenery then visit(obj) end end
        end
        function scenery_zone_for(obj) return {name=obj.zone} end
        function add(name, id, maximum, scenery, zone)
            local obj={life=maximum, max=maximum, id=id, scenery=scenery, zone=zone}
            obj.getLife=function() return obj.life end
            obj.getLife0=function() return obj.max end
            obj.getID=function() return obj.id end
            obj.isExist=function() return true end
            objects[name]=obj; return obj
        end
        function a_unit_set_life_percentage(id, percent)
            calls[#calls+1]={id=id,percent=percent}
            for _, obj in pairs(objects) do if obj.id==id then obj.life=obj.max*percent/100 end end
        end
        net={dostring_in=function(context, code) return assert(loadstring(code))() end}
        ship=add('ship', 1, 1000); building=add('building', 2, 500)
        scenery=add('scenery', 3, 200, true, 'zone')
        neighbour=add('neighbour', 4, 200, true, 'other-zone')
        ESCALATION_PERSISTENT_DAMAGE={{name='ship',health=.65},{name='building',health=.8}, {name='zone',health=.4,x=0,z=0}}
    """)
    if bridge_only:
        lua.execute("""
            local setter=a_unit_set_life_percentage
            a_unit_set_life_percentage=nil
            net.dostring_in=function(context, code)
                assert(context=='mission')
                return setfenv(assert(loadstring(code)),setmetatable({a_unit_set_life_percentage=setter},{__index=_G}))()
            end
        """)
    lua.execute(Path("resources/plugins/base/persistent_damage.lua").read_text())
    lua.execute("scheduled[1](nil,1)")
    return lua


@pytest.mark.parametrize("bridge_only", [False, True])
def test_restores_ship_static_and_scenery_without_damaging_neighbours(
    bridge_only: bool,
) -> None:
    lua = runtime(bridge_only)
    state = lua.eval("escalationPersistentDamage.snapshot()")
    assert state.ship == 0.65
    assert state.building == 0.8
    assert state.zone == 0.4
    assert lua.eval("neighbour.life") == 200
    assert lua.eval("#calls") == 3

    assert lua.eval("calls[1].percent") == 65
    assert lua.eval("calls[2].percent") == 80
    assert lua.eval("calls[3].percent") == 40


def test_burning_damage_updates_state_and_is_never_restored_twice() -> None:
    lua = runtime()
    lua.execute(
        "escalationPersistentDamage.poll(); dirty_state=false; ship.life=400; escalationPersistentDamage.poll()"
    )
    assert lua.globals().dirty_state
    assert lua.eval("escalationPersistentDamage.snapshot().ship") == 0.4
    lua.execute("scheduled[1](nil,2)")
    assert lua.eval("ship.life") == 400
    assert lua.eval("#calls") == 3


def test_dead_objects_report_zero_and_indestructible_scenery_is_ignored() -> None:
    lua = runtime()
    lua.execute("ship.life=0")
    assert lua.eval("escalationPersistentDamage.snapshot().ship") == 0


def test_missing_bridge_reports_failure_instead_of_fake_health() -> None:
    lua = runtime()
    lua.execute(
        "a_unit_set_life_percentage=nil; net=nil; add('late',5,100); ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={name='late',health=.2}; scheduled[1](nil,2)"
    )
    assert lua.eval("#warnings") == 1
    assert lua.eval("#messages") == 1
    assert lua.eval("escalationPersistentDamage.snapshot().late") is None


def test_late_activated_object_is_restored_once_available() -> None:
    lua = runtime()
    lua.execute(
        "ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={name='late',health=.2}; scheduled[1](nil,2)"
    )
    assert lua.eval("escalationPersistentDamage.snapshot().late") is None
    lua.execute("late=add('late',5,100); scheduled[1](nil,3)")
    assert lua.eval("escalationPersistentDamage.snapshot().late") == 0.2


def test_silent_engine_refusal_is_detected_after_the_command() -> None:
    lua = runtime()
    lua.execute(
        "a_unit_set_life_percentage=function() end; add('late',5,100); ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={name='late',health=.2}; scheduled[1](nil,2)"
    )
    assert lua.eval("escalationPersistentDamage.snapshot().late") is None
    assert lua.eval("#warnings") == 1


def test_indestructible_scenery_keeps_the_existing_hit_based_death_rules() -> None:
    lua = runtime()
    lua.execute(
        "add('invincible',6,1e38,true,'invincible-zone'); ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={name='invincible-zone',health=1,x=0,z=0}; scheduled[1](nil,2)"
    )
    assert lua.eval("escalationPersistentDamage.snapshot()['invincible-zone']") is None
    assert lua.eval("#calls") == 3


def test_transient_life_query_failure_does_not_heal_the_object() -> None:
    lua = runtime()
    lua.execute(
        "escalationPersistentDamage.poll(); ship.getLife=function() error('unavailable') end"
    )
    assert lua.eval("escalationPersistentDamage.snapshot().ship") == 0.65
