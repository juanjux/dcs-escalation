"""Native CAP pursuit is guarded even without an IMAC intercept lease."""

import pytest
from typing import Any

from .test_imac import metadata, runtime
from .test_imac_dcs import runtime as native_runtime, start


def exposed_cap() -> Any:
    lua = runtime()
    lua.execute("""
        own.CAP.velocity={x=220,y=0,z=0}
        rings[2]={threat(28000,0,5000,20000)}
    """)
    return lua


def test_native_heading_gets_an_escape_before_entering_a_known_sam() -> None:
    lua = exposed_cap()
    lua.execute("tick(5)")
    assert lua.eval("commander.states.CAP.order.kind") == "samAvoid"
    assert lua.eval("#sent") == 1
    assert lua.eval("#recovered") == 0
    lua.execute("""
        local q=sent[1].data.point
        assert(EscalationIMAC.geometry.safe(own.CAP.point,q,6000,rings[2],adapter.height,12000,true))
    """)


@pytest.mark.parametrize(
    "change",
    [
        "cfg.options.avoidSamThreats=false",
        "own.CAP.player=true",
        "auth[2]=false",
        "commander:pauseFlight('CAP',true)",
        "own.CAP.refuelling=true",
        "own.CAP.airborne=false",
        "commander.states.CAP.index=1",
        "rings[2]={}",
        "own.CAP.point.y=30000",
    ],
)
def test_guard_respects_settings_ownership_and_operational_envelopes(
    change: str,
) -> None:
    lua = exposed_cap()
    lua.execute(change + ";tick(5)")
    assert lua.eval("#sent") == 0


def test_guard_is_not_suppressed_by_intercept_cooldown() -> None:
    lua = exposed_cap()
    lua.execute("commander.states.CAP.cooldown=100;tick(5)")
    assert lua.eval("commander.states.CAP.order.kind") == "samAvoid"


def test_wingman_heading_is_checked_even_if_the_leader_is_safe() -> None:
    lua = exposed_cap()
    lua.execute("""
        own.CAP.velocity.x=-220
        own.CAP.members={
          {point=own.CAP.point,velocity=own.CAP.velocity},
          {point={x=0,y=6000,z=1000},velocity={x=300,y=0,z=0}}}
        tick(5)
        assert(commander.states.CAP.order.kind=='samAvoid')
        local q=commander.states.CAP.order.data.point
        for _,member in ipairs(own.CAP.members)do
          assert(EscalationIMAC.geometry.safe(member.point,q,6000,rings[2],adapter.height,12000,true))
        end
    """)


def test_departing_an_exposed_ring_does_not_start_a_new_orbit() -> None:
    lua = exposed_cap()
    lua.execute("""
        own.CAP.point.x=20000;own.CAP.velocity.x=-300;tick(5)
        assert(commander.states.CAP.order==nil)
    """)


def test_safe_resume_waits_for_clearance_and_does_not_expire_after_ten_minutes() -> (
    None
):
    lua = exposed_cap()
    lua.execute("""
        tick(5);tick(615)
        assert(commander.states.CAP.order.kind=='samAvoid' and #resumed==0)
        rings[2]={};tick(625);tick(675)
        assert(commander.states.CAP.order.kind=='samAvoid')
        tick(685)
        assert(commander.states.CAP.order==nil and #resumed==1)
    """)


def test_visible_enemy_inside_a_sam_does_not_restart_native_pursuit() -> None:
    lua = exposed_cap()
    lua.execute("""
        tick(5)
        own.CAP.point={x=-40000,y=6000,z=0};own.CAP.velocity.x=0
        rings[2]={threat(28000,20000,5000,20000)}
        observations[2]={track('fighter',28000,20000,0,'fighter')}
        tick(65);tick(125)
        assert(commander.states.CAP.order.kind=='samAvoid' and #resumed==0)
        observations[2]={};tick(135);tick(195)
        assert(commander.states.CAP.order==nil and #resumed==1)
    """)


def test_safe_intercept_can_interrupt_avoidance_and_return_to_the_same_orbit() -> None:
    lua = exposed_cap()
    lua.execute("""
        tick(5)
        local orbit=commander.states.CAP.order
        own.CAP.velocity.x=0
        observations[2]={track('fighter',-18000,0,220,'fighter')}
        tick(15)
        local intercept=commander.states.CAP.order
        assert(intercept.kind=='intercept' and intercept.data.key=='fighter')
        assert(#sent==2 and #resumed==0)
        observations[2]={};tick(25)
        assert(commander.states.CAP.order==orbit and #resumed==0)
        assert(commander:shouldStop('CAP',intercept.revision))
        rings[2]={};tick(35);tick(95)
        assert(commander.states.CAP.order==nil and #resumed==1)
    """)


def test_rejected_native_intercept_keeps_avoidance_and_applies_cooldown() -> None:
    lua = exposed_cap()
    lua.execute("""
        tick(5)
        local orbit=commander.states.CAP.order
        own.CAP.velocity.x=0
        observations[2]={track('fighter',-18000,0,220,'fighter')}
        rejectOrder=true;tick(15);tick(25)
        assert(commander.states.CAP.order==orbit and #sent==2)
        rejectOrder=false;tick(75)
        assert(commander.states.CAP.order.kind=='intercept')
    """)


def test_manual_pause_releases_both_intercept_and_the_underlying_sam_orbit() -> None:
    lua = exposed_cap()
    lua.execute("""
        tick(5)
        own.CAP.velocity.x=0
        observations[2]={track('fighter',-18000,0,220,'fighter')}
        tick(15)
        assert(commander.states.CAP.order.kind=='intercept')
        commander:pauseFlight('CAP',true)
        assert(commander.states.CAP.order==nil and #resumed==1)
    """)


def test_bingo_during_avoidance_requests_safe_recovery_not_a_return_to_patrol() -> None:
    lua = exposed_cap()
    lua.execute("tick(5);own.CAP.fuel=.26;tick(15)")
    assert lua.eval("#recovered") == 1
    assert lua.eval("#resumed") == 0
    assert lua.eval("commander.states.CAP.finished") is True


def test_red_native_patrol_has_the_same_guard() -> None:
    lua = runtime([metadata("RED", "cap", 1)])
    lua.execute("""
        rings[1]={threat(28000,0,5000,20000)}
        own.RED.velocity.x=220;tick(5)
        assert(commander.states.RED.order.kind=='samAvoid')
        assert(commander.states.CAP.order==nil)
    """)


def test_safety_route_replaces_native_enroute_tasks_and_restores_them_once() -> None:
    lua = native_runtime()
    lua.execute("""
        cap.velocity.x=300
        sam=add('SAM',1,28000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000,ceiling=20000}}
        cfg.flights[1].route[2].task={id='ComboTask',params={tasks={
          {id='EngageTargets',params={maxDistEnabled=true,maxDist=92600,targetTypes={'Air'}}}
        }}}
    """)
    start(lua)
    lua.execute("""
        tick(5)
        assert(EscalationIMAC.instance.states.CAP.order.kind=='samAvoid')
        assert(#groups.CAP.pushes==0 and #groups.CAP.rtbs==1)
        local safe=groups.CAP.rtbs[1].params.route.points
        assert(#safe[1].task.params.tasks==0)
        assert(safe[2].task.params.tasks[1].id=='Orbit')
        sam.life=0;cap.velocity.x=0;tick(15);tick(75)
        assert(EscalationIMAC.instance.states.CAP.order==nil)
        assert(#groups.CAP.rtbs==2)
        local restored=groups.CAP.rtbs[2].params.route.points
        assert(restored[2].task.params.tasks[1].id=='EngageTargets')
        tick(85);assert(#groups.CAP.rtbs==2)
    """)


def test_intercept_uses_a_temporary_task_above_the_native_avoidance_route() -> None:
    lua = native_runtime()
    lua.execute("""
        cap.velocity.x=300
        sam=add('SAM',1,28000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000,ceiling=20000}}
        fighter=add('FIGHTER',1,-35000,true,{Fighters=true})
        fighter.observedVelocity={x=0,y=0,z=0}
    """)
    start(lua)
    lua.execute("""
        tick(5)
        local state=EscalationIMAC.instance.states.CAP
        assert(state.order.kind=='samAvoid' and #groups.CAP.rtbs==1)
        cap.velocity.x=0;awacs.detections={fighter};tick(15)
        assert(state.order.kind=='intercept' and #groups.CAP.rtbs==1)
        local lease=groups.CAP.pushes[1].params
        assert(lease.task.id=='AttackGroup' and lease.task.params.groupId=='FIGHTER')
        fighter.life=0;tick(75)
        assert(state.order.kind=='samAvoid' and #groups.CAP.rtbs==1)
        assert(loadstring(lease.stopCondition.condition)())
    """)


def test_authority_remains_in_log_and_on_demand_but_not_periodic_screen_messages() -> (
    None
):
    lua = native_runtime()
    lua.execute("cfg.options.debug=true;cfg.options.reports=false")
    start(lua)
    lua.execute("""
        tick(5);tick(65);tick(125)
        assert(table.concat(logs,';'):find('|authority|AWACS AWACS',1,true))
        for _,message in ipairs(messages)do
          assert(not message.text:find(': authority - ',1,true))
        end
        local before=#messages
        for _,entry in ipairs(menus)do
          if entry.side==2 and entry.name=='Commander status' then entry.fn()end
        end
        assert(#messages==before+1 and messages[#messages].text:find('source: AWACS AWACS',1,true))
    """)


def test_stale_static_contact_does_not_drop_other_observed_aircraft() -> None:
    lua = native_runtime()
    lua.execute("""
        stale={isExist=function()error("Static doesn't exist")end}
        awacs.detections={stale,bandit}
    """)
    start(lua)
    lua.execute("""
        tick(5)
        assert(EscalationIMAC.instance.active)
        assert(EscalationIMAC.instance.states.CAP.order.kind=='intercept')
        assert(not table.concat(logs,';'):find("Static doesn't exist",1,true))
        assert(bandit.positionReads==0)
    """)


@pytest.mark.parametrize(
    "change", ["cap.player='Human'", "EscalationIMAC.pauseFlight('CAP',true)"]
)
def test_release_never_replaces_a_human_task_and_pause_restores_native_patrol(
    change: str,
) -> None:
    lua = native_runtime()
    lua.execute("""
        cap.velocity.x=300;sam=add('SAM',1,28000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000,ceiling=20000}}
    """)
    start(lua)
    lua.execute("tick(5);" + change + ";tick(15)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True
    assert lua.eval("#groups.CAP.rtbs") == (1 if change.startswith("cap.player") else 2)


@pytest.mark.parametrize(
    "disabled",
    [
        "sam.life=0",
        "cfg.threats[1].iadsDisabled=true;sam.positionError=true",
        "dcsRetribution={iadsCanEngage=function()return false end}",
        "cfg.threats[1].needsRadar=true;cfg.threats[1].radars={}",
    ],
)
def test_inoperative_batteries_do_not_divert_native_patrols(disabled: str) -> None:
    lua = native_runtime()
    lua.execute("""
        cap.velocity.x=300;sam=add('SAM',1,28000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000,ceiling=20000}}
    """ + disabled)
    start(lua)
    lua.execute("""
        tick(5);tick(65)
        assert(EscalationIMAC.instance.states.CAP.order==nil)
        assert(#groups.CAP.rtbs==0)
    """)
