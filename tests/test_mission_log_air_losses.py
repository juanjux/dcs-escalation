"""One aircraft loss is reported once despite native CRASH/KILL ordering."""

from typing import Any

import pytest

from tests.test_mission_log_pilot_names import mission_log


@pytest.fixture
def log() -> Any:
    lua = mission_log(True)
    lua.execute("""
        now=10
        timer.getTime=function()return now end
        world.event.S_EVENT_CRASH=6
        dcsRetribution={plugins={missionlog={maxmessages=60}}}
        function crash(unit)
            handler:onEvent({id=world.event.S_EVENT_CRASH,initiator=unit})
        end
        function advance(stop)
            local calls=0
            while true do
                local first=nil
                for i,task in ipairs(scheduled) do
                    if task.at<=stop and (first==nil or task.at<scheduled[first].at) then first=i end
                end
                if first==nil then break end
                calls=calls+1;assert(calls<1000,'scheduler did not settle')
                local task=table.remove(scheduled,first)
                now=task.at
                local again=task.f(task.arg,task.at)
                if again then scheduled[#scheduled+1]={f=task.f,arg=task.arg,at=again} end
            end
            now=stop
        end
        """)
    return lua


@pytest.mark.parametrize("victim", [1, 2])
@pytest.mark.parametrize("order", ["kill_crash", "crash_kill", "crash_late_kill"])
def test_combat_loss_is_not_also_a_crash(log: Any, victim: int, order: str) -> None:
    log.globals().victim_side = victim
    log.execute(
        "blue.getCoalition=function()return victim_side end;red.getCoalition=function()return 3-victim_side end"
    )
    if order == "kill_crash":
        log.execute("kill(red,blue);crash(blue)")
    elif order == "crash_kill":
        log.execute("crash(blue);kill(red,blue)")
    else:
        log.execute("crash(blue);advance(12);kill(red,blue)")
    log.execute("advance(20)")
    messages = list(log.globals().messages.values())
    losses = [m.text for m in messages if m.side == victim]
    assert len(losses) == 1 and "was SHOT DOWN" in losses[0]
    assert "CRASHED" not in losses[0]
    assert len([m for m in messages if m.side == 3 - victim]) == 1
    events = list(log.globals().mission_log_events.values())
    assert len([e for e in events if e.kind == "airkill"]) == 1
    assert not any(e.kind == "crash" for e in events)


def test_real_crash_is_confirmed_and_keeps_pilot_details(log: Any) -> None:
    log.execute("crash(blue)")
    assert not list(log.globals().messages.values())
    assert not list(log.globals().mission_log_events.values())
    log.execute("advance(14)")
    messages = list(log.globals().messages.values())
    assert len(messages) == 1 and messages[0].side == 2
    assert (
        messages[0].text == "OH NO! F/A-18E flown by Capt. Alex 'Viper' Smith CRASHED"
    )
    events = list(log.globals().mission_log_events.values())
    assert len(events) == 1 and events[0].kind == "crash"
    assert events[0].t == 10
    assert events[0].actor_pilot == "Capt. Alex 'Viper' Smith"


def test_duplicate_crashes_and_kills_are_deduplicated(log: Any) -> None:
    log.execute(
        "crash(blue);crash(blue);kill(red,blue);kill(red,blue);crash(blue);advance(20)"
    )
    assert len(list(log.globals().messages.values())) == 2
    assert len(list(log.globals().mission_log_events.values())) == 1


def test_repeated_noncombat_crash_is_only_announced_once(log: Any) -> None:
    log.execute("crash(blue);crash(blue);advance(14);crash(blue);advance(20)")
    assert len(list(log.globals().messages.values())) == 1
    assert len(list(log.globals().mission_log_events.values())) == 1


def test_crash_uses_snapshot_when_native_object_is_unavailable(log: Any) -> None:
    log.execute("""
        crash(blue)
        blue.getName=function()error('native object removed')end
        blue.getTypeName=function()error('native object removed')end
        blue.getCoalition=function()error('native object removed')end
        advance(14)
        """)
    text = list(log.globals().messages.values())[0].text
    assert "Capt. Alex 'Viper' Smith CRASHED" in text


def test_unrelated_crash_is_not_suppressed_by_another_aircraft_kill(log: Any) -> None:
    log.execute("crash(blue);kill(blue,red);advance(14)")
    messages = list(log.globals().messages.values())
    assert sum("CRASHED" in m.text for m in messages) == 1
    assert sum("SHOT DOWN" in m.text for m in messages) == 2


def test_crash_setting_hides_message_but_keeps_the_fact(log: Any) -> None:
    log.execute(
        "dcsRetribution.plugins.missionlog.crashes=false;crash(blue);advance(14)"
    )
    assert not list(log.globals().messages.values())
    assert list(log.globals().mission_log_events.values())[0].kind == "crash"


def test_disabled_loss_messages_still_suppress_the_provisional_crash(log: Any) -> None:
    log.execute(
        "dcsRetribution.plugins.missionlog.losses=false;crash(blue);kill(red,blue);advance(14)"
    )
    assert all(m.side != 2 for m in log.globals().messages.values())
    assert all(e.kind != "crash" for e in log.globals().mission_log_events.values())
