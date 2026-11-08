"""Selective missile tracking against the shipped Lua script, with DCS doubles."""

from pathlib import Path
from typing import Any

import pytest

SOURCE = Path("resources/plugins/ai_reaction/ai_reaction.lua")


def runtime(debug: bool = False) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now=0; scheduled={}; logs={}; messages={}; groups={}; weapons={}; writes={}
        AI={Option={Air={id={REACTION_ON_THREAT=1}}}}
        Weapon={Category={MISSILE=1,BOMB=3,SHELL=0,ROCKET=2}}
        Object={Category={UNIT=1,WEAPON=2,STATIC=3},getCategory=function(object)
            return object.objectCategory or 1
        end}
        Group={Category={AIRPLANE=0,HELICOPTER=1,GROUND=2,SHIP=3}}
        coalition={side={RED=1,BLUE=2}}
        function coalition.getGroups(side,category)
            local result={}
            for _,group in pairs(groups) do
                if group.side==side and group.category==category and group.alive then
                    result[#result+1]=group
                end
            end
            return result
        end
        env={info=function(s) logs[#logs+1]=s end,
             warning=function(s) logs[#logs+1]=s end}
        trigger={action={outText=function(s) messages[#messages+1]=s end}}
        world={event={S_EVENT_SHOT=1},addEventHandler=function(h) handler=h end}
        timer={getTime=function() return now end,scheduleFunction=function(fn,arg,t)
            scheduled[#scheduled+1]={fn=fn,arg=arg,t=t}
        end}
        function run(t)
            local iterations=0
            while true do
                local best,index
                for i,item in ipairs(scheduled) do
                    if item.t<=t and (not best or item.t<best.t) then best=item;index=i end
                end
                if not best then break end
                iterations=iterations+1;assert(iterations<10000,'timer loop')
                table.remove(scheduled,index);now=best.t
                local nextTime=best.fn(best.arg,now)
                if nextTime then scheduled[#scheduled+1]={fn=best.fn,arg=best.arg,t=nextTime} end
            end
            now=t
        end
        function add(name,side,category)
            local g={name=name,side=side or 2,category=category or 0,
                alive=true,option=2,failures=0,lookups=0}
            function g:getName() return self.name end
            function g:getCategory() return self.category end
            function g:isExist() return self.alive end
            function g:getController()
                self.lookups=self.lookups+1
                if self.missingController then return nil end
                return {setOption=function(_,key,value)
                    assert(key==1)
                    if g.failures>0 then
                        g.failures=g.failures-1
                        error('controller rejected option')
                    end
                    if g.reject then return false end
                    g.option=value
                    writes[#writes+1]={group=g.name,value=value,t=now}
                end}
            end
            g.unit={getGroup=function() return g end}
            groups[name]=g;return g
        end
        function shot(target,category,badDesc)
            local w={target=target,category=category or 1,alive=true,reads=0,badDesc=badDesc}
            function w:getDesc()
                if self.badDesc then error('descriptor unavailable') end
                return {category=self.category}
            end
            function w:getTypeName() return 'SD-10' end
            function w:isExist()
                if self.badExist then error('existence query unavailable') end
                return self.alive
            end
            function w:getTarget()
                self.reads=self.reads+1
                if self.badTarget then error('target unavailable') end
                if type(self.target)=='function' then return self.target(now) end
                return self.target
            end
            weapons[#weapons+1]=w
            handler:onEvent({id=1,weapon=w})
            return w
        end
        function countLog(pattern)
            local count=0
            for _,line in ipairs(logs) do if line:find(pattern,1,true) then count=count+1 end end
            return count
        end
        function totalReads()
            local count=0;for _,w in ipairs(weapons) do count=count+w.reads end;return count
        end
        add('target');add('innocent');add('enemy',1)
    """)
    lua.globals().dcsRetribution = lua.table_from(
        {"plugins": {"ai_reaction": {"DEBUG": debug}}}, recursive=True
    )
    lua.execute(SOURCE.read_text("utf-8"))
    lua.globals().run(2)
    return lua


def test_only_the_reported_target_group_gets_evade_fire() -> None:
    lua = runtime()
    lua.execute("w=shot(groups.target.unit)")
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("groups.innocent.option") == 1
    assert lua.eval("groups.enemy.option") == 1
    assert lua.eval("countLog('option=EVADE')") == 1
    assert lua.eval("#messages") == 0


@pytest.mark.parametrize("delay", [2, 10, 130])
def test_late_target_is_followed_beyond_the_original_one_second_window(
    delay: int,
) -> None:
    lua = runtime()
    lua.globals().available = 2 + delay
    lua.execute(
        "w=shot(function(t) if t>=available then return groups.target.unit end end)"
    )
    lua.globals().run(2 + delay - 0.25)
    assert lua.eval("groups.target.option") == 1
    lua.globals().run(2 + delay + 1)
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("groups.innocent.option") == 1


def test_missile_retargeting_moves_defence_instead_of_keeping_the_old_flight() -> None:
    lua = runtime()
    lua.execute("""
        w=shot(groups.target.unit)
        w.target=groups.innocent.unit
        run(3)
    """)
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("groups.innocent.option") == 2
    assert lua.eval("groups.enemy.option") == 1
    assert lua.eval("countLog('RETARGET')") == 1


def test_other_live_missiles_keep_old_target_defensive_after_retargeting() -> None:
    lua = runtime()
    lua.execute("""
        first=shot(groups.target.unit);second=shot(groups.target.unit)
        second.target=groups.innocent.unit;run(3)
    """)
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("groups.innocent.option") == 2
    lua.execute("first.alive=false;run(4)")
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("groups.innocent.option") == 2
    lua.execute("second.alive=false;run(5)")
    assert lua.eval("groups.innocent.option") == 1


def test_duplicate_shot_event_does_not_double_count_a_missile() -> None:
    lua = runtime()
    lua.execute("""
        w=shot(groups.target.unit)
        handler:onEvent({id=1,weapon=w})
        w.alive=false;run(3)
    """)
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("countLog('option=EVADE')") == 1


def test_temporary_target_gap_keeps_last_known_target_protected_until_missile_gone() -> (
    None
):
    lua = runtime()
    lua.execute("w=shot(groups.target.unit);w.target=nil;run(20)")
    assert lua.eval("groups.target.option") == 2
    lua.execute("w.alive=false;run(21)")
    assert lua.eval("groups.target.option") == 1


def test_target_query_failure_is_logged_without_losing_the_tracked_missile() -> None:
    lua = runtime()
    lua.execute("w=shot(groups.target.unit);w.badTarget=true;run(6)")
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("countLog('TARGET_QUERY_FAILED')") == 1
    lua.execute("w.badTarget=false;w.target=groups.innocent.unit;run(7)")
    assert lua.eval("groups.innocent.option") == 2
    assert lua.eval("groups.target.option") == 1


@pytest.mark.parametrize(
    "failure",
    [
        "groups.target.failures=1",
        "groups.target.reject=true",
        "groups.target.missingController=true",
    ],
)
def test_failed_evade_order_is_not_reported_as_accepted_and_is_retried(
    failure: str,
) -> None:
    lua = runtime()
    lua.execute(failure)
    lua.execute("w=shot(groups.target.unit)")
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("countLog('OPTION_FAILED')") == 1
    assert lua.eval("countLog('option=EVADE')") == 0
    lua.execute(
        "groups.target.reject=false;groups.target.missingController=false;run(3.5)"
    )
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("countLog('option=EVADE')") == 1
    assert lua.eval("groups.innocent.option") == 1


def test_passive_restore_failure_is_retried_after_last_missile_disappears() -> None:
    lua = runtime()
    lua.execute(
        "w=shot(groups.target.unit);groups.target.failures=1;w.alive=false;run(2.25)"
    )
    assert lua.eval("groups.target.option") == 2
    lua.globals().run(4)
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("countLog('option=PASSIVE')") == 1


def test_failed_initial_baseline_does_not_cache_false_success() -> None:
    lua = runtime()
    lua.execute("g=add('late');g.missingController=true;run(12)")
    assert lua.eval("groups.late.option") == 2
    lua.execute("g.missingController=false;run(13.5)")
    assert lua.eval("groups.late.option") == 1


def test_active_target_is_never_overwritten_by_baseline_and_is_periodically_reasserted() -> (
    None
):
    lua = runtime()
    lua.execute("w=shot(groups.target.unit);groups.target.option=1;run(8)")
    assert lua.eval("groups.target.option") == 2
    lua.globals().run(65)
    writes = [dict(write) for _, write in lua.globals().writes.items()]
    assert not any(
        w["group"] == "target" and w["value"] == 1 and w["t"] > 2 for w in writes
    )
    assert lua.eval("countLog('STATS')") == 1


@pytest.mark.parametrize("category", [0, 2, 3])
def test_shells_rockets_and_bombs_do_not_poll_targets(category: int) -> None:
    lua = runtime()
    lua.globals().category = category
    lua.execute("w=shot(nil,category);run(30)")
    assert lua.eval("w.reads") == 0
    assert lua.eval("#scheduled") == 2


@pytest.mark.parametrize("category", [1, 2, 3])
def test_helicopter_ground_and_ship_targets_are_not_managed(category: int) -> None:
    lua = runtime()
    lua.globals().category = category
    lua.execute("other=add('other',1,category);w=shot(other.unit);run(30)")
    assert lua.eval("w.reads") == 1
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("groups.other.option") == 2


def test_large_ship_salvo_has_no_per_weapon_timers_or_polling() -> None:
    lua = runtime()
    lua.execute("ship=add('ship',1,3);for i=1,1000 do shot(ship.unit) end")
    assert lua.eval("totalReads()") == 1000
    assert lua.eval("#scheduled") == 2
    lua.globals().run(61)
    assert lua.eval("totalReads()") == 1000
    assert lua.eval("countLog('tracked=0 unresolved=0')") == 1


def test_one_tick_bounds_polling_and_round_robin_reaches_all_missiles() -> None:
    lua = runtime()
    lua.execute("for i=1,200 do shot(nil) end")
    before = lua.eval("totalReads()")
    lua.globals().run(2.25)
    assert lua.eval("totalReads()") - before == 64
    lua.globals().run(3)
    assert all(w.reads >= 2 for _, w in lua.globals().weapons.items())
    assert lua.eval("#scheduled") == 2


def test_deleting_missiles_during_bounded_polling_does_not_skip_remaining_entries() -> (
    None
):
    lua = runtime()
    lua.execute("""
        for i=1,200 do shot(groups.target.unit) end
        for i,w in ipairs(weapons) do if i%2==0 then w.alive=false end end
        run(5)
        for _,w in ipairs(weapons) do w.alive=false end
        run(8)
    """)
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("groups.innocent.option") == 1


def test_unknown_descriptor_does_not_discard_a_confirmed_air_target() -> None:
    lua = runtime()
    lua.execute("""
        w=shot(groups.target.unit,1,true);run(3)
    """)
    assert lua.eval("groups.target.option") == 2


def test_transition_logging_is_bounded_and_debug_screen_messages_are_throttled() -> (
    None
):
    lua = runtime(debug=True)
    lua.execute("for i=1,200 do shot(add('extra'..i).unit) end")
    assert lua.eval("#logs") <= 31
    assert lua.eval("#messages") == 1
    lua.globals().run(61)
    assert lua.eval("countLog('STATS')") == 1


def test_unrelated_events_and_missing_weapons_do_not_break_the_scheduler() -> None:
    lua = runtime()
    lua.execute(
        "handler:onEvent(nil);handler:onEvent({id=99});handler:onEvent({id=1});run(20)"
    )
    assert lua.eval("#scheduled") == 2
    assert lua.eval("groups.target.option") == 1


@pytest.mark.parametrize("category", [2, 3])
def test_non_unit_targets_are_not_treated_as_unresolved_aircraft(category: int) -> None:
    lua = runtime()
    lua.globals().category = category
    lua.execute("w=shot({objectCategory=category});run(30)")
    assert lua.eval("w.reads") == 1
    assert lua.eval("countLog('TARGET_QUERY_FAILED')") == 0


def test_target_group_category_unavailable_is_retried_instead_of_discarded() -> None:
    lua = runtime()
    lua.execute("""
        groups.target.category=nil
        w=shot(groups.target.unit);run(4)
        groups.target.category=0;run(5)
    """)
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("groups.innocent.option") == 1


@pytest.mark.parametrize("method", ["getGroup", "getCategory", "getName"])
def test_target_adapter_errors_are_logged_and_recovered(method: str) -> None:
    lua = runtime()
    lua.globals().method = method
    lua.execute("""
        holder=method=='getGroup' and groups.target.unit or groups.target
        original=holder[method]
        holder[method]=function() error('adapter temporarily unavailable') end
        w=shot(groups.target.unit)
    """)
    assert lua.eval("countLog('TARGET_QUERY_FAILED')") == 1
    lua.execute("holder[method]=original;run(4)")
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("groups.innocent.option") == 1


def test_error_diagnostics_have_budget_separate_from_salvo_transition_logs() -> None:
    lua = runtime()
    lua.execute("""
        for i=1,40 do shot(add('extra'..i).unit) end
        groups.target.failures=1
        shot(groups.target.unit)
    """)
    assert lua.eval("countLog('OPTION_FAILED')") == 1
    assert lua.eval("#logs") <= 41


def test_temporary_weapon_existence_error_does_not_cancel_evasion() -> None:
    lua = runtime()
    lua.execute("w=shot(groups.target.unit);w.badExist=true;run(2.5)")
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("countLog('MISSILE_QUERY_FAILED')") == 1
    lua.execute("w.badExist=false;run(3)")
    assert lua.eval("groups.target.option") == 2
    assert lua.eval("countLog('TRACKING_LOST')") == 0
    lua.execute("w.alive=false;run(4)")
    assert lua.eval("groups.target.option") == 1


def test_permanently_invalid_weapon_does_not_leave_flight_defensive_forever() -> None:
    lua = runtime()
    lua.execute("w=shot(groups.target.unit);w.badExist=true;run(5)")
    assert lua.eval("groups.target.option") == 1
    assert lua.eval("countLog('TRACKING_LOST')") == 1
    assert lua.eval("groups.innocent.option") == 1
