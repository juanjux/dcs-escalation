"""Pure threat routing geometry; native task acceptance uses standalone probes."""

from pathlib import Path
from typing import Any

import pytest

from game.missiongenerator.afacthreats import envelope


@pytest.fixture
def lua() -> Any:
    vm = pytest.importorskip("lupa.lua51").LuaRuntime()
    for name in ("core.lua", "afac-search.lua", "afac-safety.lua"):
        vm.execute((Path("resources/plugins/realisticcas") / name).read_text("utf-8"))
    vm.execute("""
    A=RealisticCAS.AFACSafety
    t={point={x=0,y=0,z=0},radius=7000,ceiling=4000,typeName='ZSU_57_2'}
    input={source={x=-15000,y=2000,z=0},points={{x=-2000,z=0},{x=2000,z=0}},
      altitude=2000,maxAltitude=9000,zone={radius=20000,points={{x=0,z=0}}},
      footprint=1200,threats={t},clearance=150,height=function()return 0 end}
    """)
    return vm


def test_verified_ceilings_and_unknown_air_defence_are_conservative() -> None:
    assert envelope("ZSU_57_2") == {"radius": 7000, "ceiling": 4000}
    stinger = envelope("Soldier stinger")
    assert stinger is not None and stinger["radius"] == 4500
    assert stinger["ceiling"] is None
    assert envelope("M-1 Abrams") is None
    assert envelope("unknown mod") is None


def test_clearance_and_route_segments_check_the_entire_ring(lua: Any) -> None:
    lua.execute("""
    assert(not A.clear({x=0,y=4200,z=0},{t}))
    assert(A.clear({x=0,y=4500,z=0},{t}))
    assert(not A.leg({x=-10000,z=0},{x=10000,z=0},2000,{t}))
    assert(A.leg({x=-10000,z=10000},{x=10000,z=10000},2000,{t}))
    assert(A.leg({x=1000,z=0},{x=10000,z=0},2000,{t},true))
    assert(not A.leg({x=1000,z=0},{x=-10000,z=0},2000,{t},true))
    """)


def test_climb_stays_outside_threat_until_actual_altitude_is_safe(lua: Any) -> None:
    lua.execute("""
    local p=A.plan(input)
    assert(p.mode=='avoid' and p.altitude==4500)
    assert(A.orbit(p.point,input.source.y,input.zone,{t},input.footprint))
    input.source.y=4500;input.holdPoint=p.point
    p=A.plan(input)
    assert(p.mode=='avoid' and p.point.x==0 and p.point.z==0)
    """)


@pytest.mark.parametrize("change", ["input.maxAltitude=2500", "t.ceiling=nil"])
def test_cloud_or_unknown_ceiling_forces_horizontal_standoff(
    lua: Any, change: str
) -> None:
    lua.execute(change + """
    local p=A.plan(input)
    assert(p.mode=='avoid' and p.altitude==2000)
    assert(A.orbit(p.point,2000,input.zone,{t},input.footprint))
    """)


def test_whole_zone_blocked_aborts_instead_of_leaving_it(lua: Any) -> None:
    lua.execute("""
    input.zone.radius=6000;input.maxAltitude=2500
    input.source={x=1000,y=2000,z=0}
    assert(A.plan(input).mode=='abort')
    """)


def test_inbound_climb_is_allowed_before_station_but_not_after(lua: Any) -> None:
    lua.execute("""
    input.zone.radius=6000;input.approach=true
    local p=A.plan(input)
    assert(p.mode=='avoid' and p.approach and p.altitude==4500)
    input.approach=false
    assert(A.plan(input).mode=='abort')
    """)


def test_terrain_on_the_approach_is_checked_not_just_the_orbit(lua: Any) -> None:
    lua.execute("""
    input.height=function()return 10000 end
    assert(A.plan(input).mode=='abort')
    """)


def test_original_route_resumes_when_threats_are_removed(lua: Any) -> None:
    lua.execute("input.threats={};assert(A.plan(input).mode=='original')")


def test_threat_on_inbound_leg_is_not_ignored(lua: Any) -> None:
    lua.execute("""
    t.point.x=-11000;t.radius=2000;t.ceiling=nil
    assert(A.plan(input).mode~='original')
    """)


def test_saved_hold_point_prevents_chasing_the_aircraft_each_tick(lua: Any) -> None:
    lua.execute("""
    input.maxAltitude=2500
    local p=A.plan(input);input.holdPoint=p.point
    input.source.x=input.source.x+200
    local next=A.plan(input)
    assert(next.mode=='avoid' and next.point.x==p.point.x and next.point.z==p.point.z)
    """)


def test_active_climb_route_is_revalidated_against_new_threats_and_caps(
    lua: Any,
) -> None:
    lua.execute("""
    local p=A.plan(input)
    assert(A.safePlan(input,p))
    input.source.x=input.source.x+100
    assert(A.safePlan(input,p))
    input.maxAltitude=4000
    assert(not A.safePlan(input,p))
    input.maxAltitude=9000
    input.threats[2]={point={x=p.point.x,y=0,z=p.point.z},radius=2000}
    assert(not A.safePlan(input,p))
    """)


def test_completed_corners_are_not_revisited_while_climbing(lua: Any) -> None:
    lua.execute("""
    input.threats={};input.source={x=5000,y=3000,z=0}
    local p={point={x=6000,z=0},altitude=4500,
      path={{x=-5000,z=0},{x=6000,z=0}}}
    input.threats={{point={x=-5000,y=0,z=0},radius=1000}}
    assert(not A.safePlan(input,p,1))
    assert(A.safePlan(input,p,2))
    """)


def test_inbound_detour_can_pass_outside_the_station_zone(lua: Any) -> None:
    lua.execute("""
    input.source={x=-50000,y=2000,z=0}
    input.points={{x=48000,z=0},{x=52000,z=0}}
    input.zone={radius=10000,points={{x=50000,z=0}}}
    input.approach=true;t.ceiling=nil
    local plan=A.plan(input)
    assert(plan.mode=='avoid' and #plan.path==2)
    assert(not RealisticCAS.AFACSearch.inside(plan.path[1],input.zone))
    assert(RealisticCAS.AFACSearch.inside(plan.point,input.zone))
    assert(A.safePlan(input,plan,1))
    input.approach=false
    assert(not A.safePlan(input,plan,1))
    assert(A.plan(input).mode=='abort')
    """)
