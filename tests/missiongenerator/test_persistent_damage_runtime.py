"""Execute health tracking in Lua 5.1 with modeled DCS objects and APIs."""

from pathlib import Path
from typing import Any

import pytest


def runtime(bridge_only: bool = False) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now=0; objects={}; warnings={}; messages={}; scheduled={}; calls={}; explosions={}
        env={warning=function(text) warnings[#warnings+1]=text end}
        trigger={action={outText=function(text) messages[#messages+1]=text end}}
        timer={getTime=function() return now end, scheduleFunction=function(fn,arg,t) scheduled[#scheduled+1]=fn end}
        Unit={getByName=function(name) return objects[name] end}
        StaticObject={getByName=function(name) return objects[name] end}
        Object={Category={UNIT=1,STATIC=3,SCENERY=5}}; world={VolumeType={SPHERE=1}}
        land={getHeight=function() return 0 end}
        world.searchObjects=function(category, volume, visit)
            for _, obj in pairs(objects) do
                local p=volume.params.point
                local distance=(obj.x-p.x)^2+(obj.z-p.z)^2
                if obj.category==category and distance<=volume.params.radius^2 then
                    if visit(obj)==false then break end
                end
            end
        end
        function scenery_zone_for(obj) return {name=obj.zone} end
        function add(name, id, maximum, scenery, zone)
            local obj={life=maximum, max=maximum, id=id, scenery=scenery, zone=zone,
                x=scenery and 0 or id*1000,z=0,category=scenery and 5 or 3}
            obj.getLife=function() return obj.life end
            obj.getLife0=function() return obj.max end
            obj.getID=function() return obj.id end
            obj.getPoint=function() return {x=obj.x,y=0,z=obj.z} end
            obj.isExist=function() return true end
            objects[name]=obj; return obj
        end
        function a_unit_set_life_percentage(id, percent)
            calls[#calls+1]={id=id,percent=percent}
            for _, obj in pairs(objects) do if obj.id==id then obj.life=obj.max*percent/100 end end
        end
        net={dostring_in=function(context, code) return assert(loadstring(code))() end}
        trigger.action.explosion=function(p,power)
            explosions[#explosions+1]=power
            for _,obj in pairs(objects) do
                local distance=math.sqrt((obj.x-p.x)^2+(obj.z-p.z)^2)
                local factor=distance==0 and 1 or (distance<=5 and .06 or 0)
                local loss=power*2.5*factor
                if loss>=obj.max*.02 then obj.life=math.max(0,obj.life-loss) end
            end
        end
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


def test_dead_objects_report_zero() -> None:
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


def test_unsupported_building_does_not_attempt_a_setter_or_report_full_health() -> None:
    lua = runtime()
    lua.execute("""
        add('unsupported-building',5,100)
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={
            name='unsupported-building',health=.35,unsupported=true}
        scheduled[1](nil,2)
    """)
    assert lua.eval("#calls") == 3
    assert lua.eval("objects['unsupported-building'].life") == 100
    assert (
        lua.eval("escalationPersistentDamage.snapshot()['unsupported-building']")
        is None
    )
    assert lua.eval("#warnings") == 1
    assert "unsupported" in lua.eval("warnings[1]")
    assert "35" in lua.eval("warnings[1]")


def test_full_health_building_still_tracks_new_damage_without_a_setter() -> None:
    lua = runtime()
    lua.execute("""
        add('full-building',5,100)
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={
            name='full-building',health=1,unsupported=true}
        scheduled[1](nil,2)
        objects['full-building'].life=80
    """)
    assert lua.eval("escalationPersistentDamage.snapshot()['full-building']") == 0.8
    assert lua.eval("#calls") == 3
    assert lua.eval("#warnings") == 0


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


def finish_building_initialization(lua: Any) -> None:
    for now in range(4, 124, 2):
        lua.execute(f"scheduled[1](nil,{now})")


@pytest.mark.parametrize("maximum", [5, 200, 300, 400, 500, 1000, 1600])
@pytest.mark.parametrize(
    "health", [0.01, 0.35, 0.65, 0.95, 0.978, 0.9821209717, 0.995, 1]
)
def test_building_pulses_restore_measured_health_without_native_setter(
    maximum: int, health: float
) -> None:
    lua = runtime()
    lua.execute(f"""
        factory=add('factory',10,{maximum})
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={{
            name='factory',health={health},building=true}}
        scheduled[1](nil,2)
    """)
    if health < 0.98:
        assert lua.eval("escalationPersistentDamage.snapshot().factory") is None
    finish_building_initialization(lua)
    actual = lua.eval("escalationPersistentDamage.snapshot().factory")
    assert actual == pytest.approx(health, abs=0.020001)
    assert lua.eval("#warnings") == 0
    assert lua.eval("#calls") == 3
    count = lua.eval("#explosions")
    lua.execute("factory.life=factory.life*.7; scheduled[1](nil,130)")
    assert lua.eval("escalationPersistentDamage.snapshot().factory") == pytest.approx(
        actual * 0.7
    )
    assert lua.eval("#explosions") == count


@pytest.mark.parametrize("distance,maximum", [(4, 400), (5, 5)])
def test_unsafe_neighbour_prevents_restoration_and_preserves_saved_state(
    distance: int, maximum: int
) -> None:
    lua = runtime()
    lua.execute(f"""
        factory=add('factory',10,400)
        fragile=add('fragile',11,{maximum});fragile.x=factory.x+{distance}
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={{
            name='factory',health=.35,building=true}}
        scheduled[1](nil,2)
    """)
    finish_building_initialization(lua)
    assert lua.eval("#explosions") == 0
    assert lua.eval("fragile.life") == maximum
    assert lua.eval("escalationPersistentDamage.snapshot().factory") is None
    assert lua.eval("#warnings") == 1


def test_small_pulses_leave_a_nearby_building_intact() -> None:
    lua = runtime()
    lua.execute("""
        factory=add('factory',10,400)
        adjacent=add('adjacent',11,400);adjacent.x=factory.x+5
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={
            name='factory',health=.35,building=true}
        scheduled[1](nil,2)
    """)
    finish_building_initialization(lua)
    assert lua.eval("adjacent.life") == 400
    assert lua.eval("escalationPersistentDamage.snapshot().factory") == pytest.approx(
        0.35
    )


def test_silent_refusal_of_building_damage_does_not_overwrite_saved_health() -> None:
    lua = runtime()
    lua.execute("""
        trigger.action.explosion=function()end
        factory=add('factory',10,400)
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={
            name='factory',health=.35,building=true}
        scheduled[1](nil,2)
    """)
    finish_building_initialization(lua)
    assert lua.eval("escalationPersistentDamage.snapshot().factory") is None
    assert lua.eval("#warnings") == 1


def test_damage_during_initialization_stops_further_pulses() -> None:
    lua = runtime()
    lua.execute("""
        factory=add('factory',10,400)
        ESCALATION_PERSISTENT_DAMAGE[#ESCALATION_PERSISTENT_DAMAGE+1]={
            name='factory',health=.35,building=true}
        scheduled[1](nil,2);factory.life=80
    """)
    finish_building_initialization(lua)
    assert lua.eval("#explosions") == 1
    assert lua.eval("escalationPersistentDamage.snapshot().factory") == 0.2
