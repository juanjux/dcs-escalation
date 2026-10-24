"""Deterministic Lua 5.1 contracts; these do not claim DCS flight acceptance."""

from pathlib import Path
from typing import Any

import pytest

PLUGIN = Path("resources/plugins/realisticcas")

FIXTURE = """
time=0; starts={}; stops={}; smokeAttempts={}; events={}; updates={}
startOK=true; stopOK=true; smokeOK=true; updateOK=true
function options()
  return {enabled=true,clock=function() return time end,
    startMark=function(id,t,r)
      starts[#starts+1]={id=id,target=t,request=r};return startOK
    end,
    stopMark=function(id,t) stops[#stops+1]={id=id,target=t};return stopOK end,
    updateMark=function(id,t) updates[#updates+1]=t;return updateOK end,
    smoke=function(id,t) smokeAttempts[#smokeAttempts+1]=t;return smokeOK end,
    emit=function(side,id,kind,detail,duration)
      events[#events+1]={side=side,id=id,kind=kind,detail=detail,duration=duration}
    end}
end
function observer(id,side,rounds,laser,pointer)
  return {id=id,side=side or 2,smokeRounds=rounds or 0,
    capabilities={laser=laser~=false,irPointer=pointer~=false}}
end
function contact(group,id,side)
  return {group=group or 'tanks',id=id or 'tank1',side=side or 1,
    point={x=1000,y=0,z=0},alive=true,revealed=true,observed=true,safe=true,inZone=true}
end
function report(contacts)
  return {alive=true,fuel=0.8,onStation=true,night=false,contacts=contacts or {contact()}}
end
api=RealisticCAS.newAFAC(options())
assert(api:register(observer('Chevy1')))
"""


@pytest.fixture
def lua() -> Any:
    vm = pytest.importorskip("lupa.lua51").LuaRuntime()
    vm.execute((PLUGIN / "core.lua").read_text(encoding="utf-8"))
    vm.execute((PLUGIN / "afac.lua").read_text(encoding="utf-8"))
    vm.execute(FIXTURE)
    return vm


def test_loading_and_disabled_coordinator_are_inert(lua: Any) -> None:
    lua.execute("""
      local inert=RealisticCAS.newAFAC()
      assert(not inert:register(observer('off')))
      assert(not inert:step('off',report()))
      assert(inert:stop())
      assert(#starts==0 and #stops==0 and #events==0)
    """)


@pytest.mark.parametrize("side", [1, 2])
def test_common_code_group_reservation_and_coalition_messages(
    lua: Any, side: int
) -> None:
    lua.execute(f"""
      local a=RealisticCAS.newAFAC(options())
      a:register(observer('first',{side}));a:register(observer('second',{side}))
      local t=contact('armour','tank1',{3 - side})
      local other=contact('armour','tank2',{3 - side})
      assert(a:step('first',report({{t}})).state=='mark')
      assert(a:step('second',report({{other}})).state=='search')
      assert(#starts==1 and starts[1].request.laserCode==1688)
      assert(events[1].side=={side} and events[1].duration==15)
      assert(a:stop())
      assert(a:get('first').state=='stopped')
    """)


def test_different_groups_can_be_marked_simultaneously(lua: Any) -> None:
    lua.execute("""
      api:register(observer('Chevy2'))
      api:step('Chevy1',report())
      api:step('Chevy2',report({contact('other group')}))
      assert(#starts==2)
      assert(starts[1].request.laserCode==starts[2].request.laserCode)
    """)


@pytest.mark.parametrize(
    "assignment",
    [
        "t.side=2",
        "t.side=0",
        "t.alive=false",
        "t.revealed=false",
        "t.observed=false",
        "t.safe=false",
        "t.inZone=false",
        "t.point.x=0/0",
        "t.group=''",
        "t.id=''",
    ],
)
def test_unobserved_unsafe_and_invalid_contacts_cannot_be_marked(
    lua: Any, assignment: str
) -> None:
    lua.execute(f"""
      local t=contact();{assignment}
      assert(api:step('Chevy1',report({{t}})).state=='search')
      assert(#starts==0)
    """)


def test_moving_spots_use_only_fresh_observations(lua: Any) -> None:
    lua.execute("""
      api:step('Chevy1',report())
      local t=contact();t.point.x=1200
      api:step('Chevy1',report({t}))
      assert(updates[1].point.x==1200)
      t.observed=false
      assert(api:step('Chevy1',report({t})).state=='search')
      assert(#updates==1 and #stops==1)
    """)


def test_configurable_mark_duration_rotates_to_another_group(lua: Any) -> None:
    lua.execute("""
      local o=options();o.markSeconds=30;o.laserCode=1677;o.messageSeconds=25
      local a=RealisticCAS.newAFAC(o);a:register(observer('first'))
      a:step('first',report());time=30
      assert(a:step('first',report()).state=='search')
      assert(a:step('first',report()).state=='search')
      assert(a:step('first',report({contact(),contact('next group')})).state=='mark')
      assert(starts[2].target.group=='next group')
      assert(starts[2].request.laserCode==1677 and events[1].duration==25)
    """)


@pytest.mark.parametrize("exit_kind", ["bingo", "station", "lost"])
def test_terminal_exit_cleans_up_and_cannot_be_reversed(
    lua: Any, exit_kind: str
) -> None:
    change = {
        "bingo": "r.fuel=0.2",
        "station": "time=3600",
        "lost": "r.alive=false",
    }[exit_kind]
    expected = "lost" if exit_kind == "lost" else "rtb"
    lua.execute(f"""
      api:step('Chevy1',report());local r=report();{change}
      assert(api:step('Chevy1',r).state=='{expected}')
      assert(#stops==1)
      assert(api:step('Chevy1',report()).state=='{expected}')
      assert(#starts==1)
    """)


def test_station_time_starts_at_arrival_and_survives_zone_reentry(lua: Any) -> None:
    lua.execute("""
      local r=report();r.onStation=false;time=1000
      assert(api:step('Chevy1',r).state=='transit')
      assert(api:get('Chevy1').stationEnds==nil)
      time=2000;api:step('Chevy1',report())
      assert(api:get('Chevy1').stationEnds==5600)
      time=2100;api:step('Chevy1',r)
      time=2200;api:step('Chevy1',report())
      assert(api:get('Chevy1').stationEnds==5600)
    """)


def test_cleanup_failure_keeps_group_reserved_until_acknowledged(lua: Any) -> None:
    lua.execute("""
      api:register(observer('Chevy2'));api:step('Chevy1',report())
      stopOK=false;local dead=report();dead.alive=false
      assert(api:step('Chevy1',dead).state=='stopping')
      assert(api:step('Chevy2',report()).state=='search')
      stopOK=true
      assert(api:step('Chevy1',dead).state=='lost')
      assert(api:step('Chevy2',report()).state=='mark')
    """)


def test_failed_start_is_cleaned_before_reservation_is_released(lua: Any) -> None:
    lua.execute("""
      startOK=false;stopOK=false;api:register(observer('Chevy2'))
      assert(api:step('Chevy1',report()).state=='stopping')
      startOK=true
      assert(api:step('Chevy2',report()).state=='search')
      stopOK=true;api:step('Chevy1',report({}))
      assert(api:step('Chevy2',report()).state=='mark')
    """)


@pytest.mark.parametrize("failure", ["false", "throw"])
def test_failed_smoke_attempts_do_not_create_free_ammunition(
    lua: Any, failure: str
) -> None:
    lua.execute("""
      api=RealisticCAS.newAFAC(options());api:register(observer('Chevy1',2,1))
    """)
    lua.execute(
        "smokeOK=false"
        if failure == "false"
        else """
      local o=options();o.smoke=function() error('engine failure') end
      api=RealisticCAS.newAFAC(o);api:register(observer('Chevy1',2,1))
    """
    )
    lua.execute("""
      assert(api:step('Chevy1',report()).smokeRounds==0)
      api:step('Chevy1',report({}));api:step('Chevy1',report())
      assert(api:get('Chevy1').smokeRounds==0)
      assert(events[#events].detail.smoke==false)
    """)


def test_finite_smoke_and_night_pointer(lua: Any) -> None:
    lua.execute("""
      api=RealisticCAS.newAFAC(options());api:register(observer('Chevy1',2,1))
      local r=report();r.night=true
      api:step('Chevy1',r)
      assert(starts[1].request.infrared and #smokeAttempts==1)
      api:step('Chevy1',report({}));api:step('Chevy1',r)
      assert(#smokeAttempts==1 and api:get('Chevy1').smokeRounds==0)
    """)


def test_visual_observer_does_not_receive_a_free_designator_or_pointer(
    lua: Any,
) -> None:
    lua.execute("""
      api:register(observer('visual',2,0,false,false))
      local r=report();r.night=true
      assert(api:step('visual',r).state=='search' and #starts==0)
      api:register(observer('smoke only',2,1,false,false))
      assert(api:step('smoke only',r).state=='mark')
      assert(not starts[1].request.laser and not starts[1].request.infrared)
    """)


def test_work_is_bounded_and_callbacks_cannot_mutate_live_state(lua: Any) -> None:
    lua.execute("""
      local o=options();o.contactBudget=1
      o.startMark=function(id,t,r) t.group='corrupt';t.point.x=0;return true end
      local a=RealisticCAS.newAFAC(o);a:register(observer('first'))
      local t=contact();t.safe=false
      assert(a:step('first',report({t,contact('beyond budget')})).state=='search')
      assert(a:step('first',report()).group=='tanks')
      local state=a:get('first');state.state='rtb'
      assert(a:get('first').state=='mark')
    """)


@pytest.mark.parametrize(
    "setting",
    [
        "markSeconds=0",
        "markSeconds=0/0",
        "stationSeconds=-1",
        "laserCode=1689",
        "laserCode=1488",
        "laserCode=1698",
        "messageSeconds=false",
        "contactBudget=0",
        "bingo=2",
    ],
)
def test_invalid_configuration_is_rejected(lua: Any, setting: str) -> None:
    lua.execute(f"assert(not pcall(RealisticCAS.newAFAC,{{{setting}}}))")


def test_stop_retries_failed_cleanup_and_then_disables(lua: Any) -> None:
    lua.execute("""
      api:step('Chevy1',report());stopOK=false
      assert(not api:stop());stopOK=true;assert(api:stop())
      assert(not api:step('Chevy1',report()))
    """)


def test_invalid_observer_report_stops_existing_mark(lua: Any) -> None:
    lua.execute("""
      api:step('Chevy1',report());local r=report();r.fuel=0/0
      assert(api:step('Chevy1',r).state=='search')
      assert(#stops==1)
    """)


def test_destroyed_source_does_not_require_fuel_or_position(lua: Any) -> None:
    lua.execute("""
      api:step('Chevy1',report())
      assert(api:step('Chevy1',{alive=false}).state=='lost')
      assert(#stops==1)
    """)


def test_exit_intent_is_visible_even_when_cleanup_keeps_failing(lua: Any) -> None:
    lua.execute("""
      api:step('Chevy1',report());stopOK=false
      local state=api:step('Chevy1',report({}))
      assert(state.state=='stopping' and state.pendingState=='search')
      local r=report();r.fuel=0.1
      state=api:step('Chevy1',r)
      assert(state.state=='stopping' and state.pendingState=='rtb')
      state=api:step('Chevy1',{alive=false})
      assert(state.pendingState=='lost')
      time=4000;state=api:step('Chevy1',report())
      assert(state.pendingState=='lost')
    """)


@pytest.mark.parametrize("callback", ["startMark", "updateMark", "stopMark", "emit"])
def test_adapter_exceptions_are_contained(lua: Any, callback: str) -> None:
    expected = {
        "startMark": "search",
        "updateMark": "search",
        "stopMark": "stopping",
        "emit": "search",
    }[callback]
    lua.execute(f"""
      local o=options();o.{callback}=function() error('engine failure') end
      local a=RealisticCAS.newAFAC(o);a:register(observer('first'))
      a:step('first',report());a:step('first',report())
      a:step('first',report({{alive=false}}))
      assert(a:get('first').state=='{expected}')
    """)


def test_custom_station_duration_is_respected(lua: Any) -> None:
    lua.execute("""
      local o=options();o.stationSeconds=60
      local a=RealisticCAS.newAFAC(o);a:register(observer('first'))
      a:step('first',report());time=60
      assert(a:step('first',report()).state=='rtb')
    """)
