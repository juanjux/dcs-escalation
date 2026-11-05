"""IMAC decisions use sensor observations and temporary, fuel-limited task leases."""

from pathlib import Path
from typing import Any

import pytest

from game.missiongenerator.imac import DEFAULTS

ROOT = Path("resources/plugins/imac")


def metadata(name: str, mode: str, side: int = 2) -> dict[str, Any]:
    return {
        "group": name,
        "side": side,
        "mode": mode,
        "awacs": name == "AWACS",
        "stationStart": 2,
        "recoveryIndex": 4,
        "attackIndex": 3,
        "endTime": 4000 if mode == "cap" else None,
        "bingo": 0.25,
        "burnPerMeter": 0.000001,
        "package": "package",
        "route": [
            {"x": -50000, "y": 0, "alt": 6000, "speed": 220},
            {"x": 0, "y": 0, "alt": 6000, "speed": 220},
            {"x": 60000, "y": 0, "alt": 6000, "speed": 220},
            {"x": 10000, "y": 0, "alt": 6000, "speed": 220},
            {
                "x": -50000,
                "y": 0,
                "alt": 0,
                "speed": 100,
                "type": "Land",
                "airdromeId": 1,
            },
        ],
    }


def config() -> dict[str, Any]:
    return {
        "options": dict(DEFAULTS),
        "flights": [metadata("CAP", "cap"), metadata("AWACS", "support")],
        "sensors": [],
        "commandCenters": [],
        "threats": [],
    }


def runtime(extra: list[dict[str, Any]] | None = None) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    for name in ("geometry.lua", "commander.lua"):
        lua.execute((ROOT / name).read_text(encoding="utf-8"))
    cfg = config()
    cfg["flights"].extend(extra or [])
    lua.globals().cfg = lua.table_from(cfg, recursive=True)
    lua.execute("""
        now=0; auth={[1]=true,[2]=true}; observations={[1]={},[2]={}}
        rings={[1]={},[2]={}}; own={}; sent={}; recovered={}; reports={}
        for _,m in ipairs(cfg.flights) do
          own[m.group]={point={x=0,y=6000,z=0},velocity={x=0,y=0,z=0},
            speed=220,fuel=.95,airborne=true,healthy=true,ammo=true}
        end
        own.AWACS.point.x=-100000
        function track(key,x,z,vx,kind)
          return {key=key,groupId=key,point={x=x,y=6000,z=z or 0},
            velocity={x=vx or -250,y=0,z=0},kind=kind or 'bomber'}
        end
        function threat(x,z,radius,ceiling,ground)
          return {point={x=x,y=ground or 0,z=z},radius=radius,ceiling=ceiling}
        end
        adapter={
          time=function()return now end,
          authority=function(side)return auth[side] end,
          contacts=function(side)return observations[side] end,
          threats=function(side)return rings[side] end,
          sample=function(meta)return own[meta.group] end,
          height=function(p)return terrainHeight or 0 end,
          altitude=function(p)return p.alt+(p.alt_type=='RADIO' and (terrainHeight or 0) or 0) end,
          order=function(state,order)
            sent[#sent+1]={group=state.meta.group,kind=order.kind,data=order.data,revision=order.revision}
            if rejectOrder then return false,'native failure' end
            return true
          end,
          recover=function(state,p,threats)
            recovered[#recovered+1]=state.meta.group
            return not rejectRecovery,'blocked'
          end,
          report=function(event)reports[#reports+1]=event end
        }
        commander=EscalationIMAC.newCommander(cfg,adapter)
        for _,m in ipairs(cfg.flights)do commander:reached(m.group,2)end
        function tick(t) now=t;commander:tick()end
    """)
    return lua


def test_redirects_nearest_patrol_beyond_fifty_nm_and_reserves_target() -> None:
    lua = runtime([metadata("FAR_CAP", "cap")])
    lua.execute(
        "own.FAR_CAP.point.x=-20000; observations[2]={track('bandit',120000)}; tick(5)"
    )
    assert lua.eval("#sent") == 1
    assert lua.eval("sent[1].group") == "CAP"
    assert lua.eval("sent[1].kind") == "intercept"
    assert lua.eval("120000/1852 > 50") is True


def test_mirrors_decisions_for_red_without_blue_authority() -> None:
    lua = runtime([metadata("RED_CAP", "cap", 1)])
    lua.execute("auth[2]=false;observations[1]={track('blue',120000)};tick(5)")
    assert lua.eval("sent[1].group") == "RED_CAP"


@pytest.mark.parametrize(
    "change",
    [
        "auth[2]=false",
        "own.CAP.player=true",
        "own.CAP.airborne=false",
        "own.CAP.healthy=false",
        "own.CAP.ammo=false",
        "own.CAP.fuel=.4",
        "own.CAP.refuelling=true",
        "commander.states.CAP.meta.endTime=600",
        "commander.states.CAP.index=1",
        "commander.states.CAP.index=4",
        "EscalationBARCAP={states={CAP={refuelling=true}}}",
        "EscalationBARCAP={states={CAP={finished=true}}}",
        "commander:pause(2,true)",
        "commander:pauseFlight('CAP',true)",
        "commander.states.CAP.meta.burnPerMeter=nil",
        "rings[2]={threat(60000,0,10000)}",
        "terrainHeight=5900",
    ],
)
def test_declines_unavailable_or_unsafe_intercept(change: str) -> None:
    lua = runtime()
    lua.execute(change + ";observations[2]={track('bandit',120000)};tick(5)")
    assert lua.eval("commander.states.CAP.order==nil") is True


@pytest.mark.parametrize(
    "change",
    [
        "observations[2]={}",
        "auth[2]=false",
        "own.CAP.player=true",
        "own.CAP.fuel=.2",
        "own.CAP.healthy=false",
        "own.CAP.ammo=false",
        "own.CAP.point.x=160000",
        "rings[2]={threat(60000,0,15000)}",
        "EscalationBARCAP={states={CAP={refuelling=true}}}",
    ],
)
def test_intercept_releases_without_rebuilding_original_route(change: str) -> None:
    lua = runtime()
    lua.execute("observations[2]={track('bandit',120000)};tick(5)")
    lua.execute(change + ";tick(15)")
    assert lua.eval("commander.states.CAP.order==nil") is True
    assert lua.eval("#recovered") == 0


def test_native_stop_condition_immediately_yields_to_player_or_bingo() -> None:
    lua = runtime()
    lua.execute("observations[2]={track('bandit',120000)};tick(5)")
    token = lua.eval("sent[1].revision")
    assert lua.eval(f"commander:shouldStop('CAP',{token})") is False
    lua.execute("own.CAP.fuel=.1")
    assert lua.eval(f"commander:shouldStop('CAP',{token})") is True
    assert lua.eval("#recovered") == 0


def test_withdrawing_enemy_is_not_pursued_indefinitely() -> None:
    lua = runtime()
    lua.execute("""
        observations[2]={track('bandit',120000)};tick(5)
        observations[2]={track('bandit',135000,0,250)};tick(15);tick(200)
    """)
    assert lua.eval("commander.states.CAP.order==nil") is True


def test_no_detection_means_no_orders_or_invented_bomber_positions() -> None:
    lua = runtime()
    lua.execute("tick(5);tick(15);tick(100)")
    assert lua.eval("#sent") == 0


def test_receding_bomber_is_not_dispatched_against() -> None:
    lua = runtime()
    lua.execute("observations[2]={track('bandit',120000,0,250)};tick(5)")
    assert lua.eval("#sent") == 0


def test_vulnerable_aircraft_evades_closing_fighter_then_resumes() -> None:
    lua = runtime()
    lua.execute("""
        observations[2]={track('fighter',-70000,0,-250,'fighter')};tick(5)
    """)
    assert lua.eval("commander.states.AWACS.order.kind") == "evade"
    assert (
        lua.eval("commander.states.AWACS.order.data.point.x < own.AWACS.point.x")
        is True
    )
    lua.execute("observations[2]={};tick(15);tick(45)")
    assert lua.eval("commander.states.AWACS.order==nil") is True
    assert lua.eval("#recovered") == 0


def test_evasion_does_not_choose_sam_side_or_cut_across_enemy() -> None:
    lua = runtime()
    lua.execute("""
        rings[2]={threat(-130000,0,10000)}
        observations[2]={track('fighter',-70000,0,-250,'fighter')};tick(5)
        escape=commander.states.AWACS.order.data.point
    """)
    assert abs(lua.eval("escape.z")) > 20000
    assert (
        lua.eval(
            "EscalationIMAC.geometry.leg(own.AWACS.point,escape,6000,rings[2],10000,true)"
        )
        is True
    )


def test_sam_ceiling_is_above_launcher_msl_not_above_sea_level() -> None:
    lua = runtime()
    lua.execute(
        "a={x=0,y=6000,z=0};b={x=100000,y=6000,z=0};t={threat(50000,0,10000,4000,2200)}"
    )
    assert lua.eval("EscalationIMAC.geometry.leg(a,b,6000,t)")[0] is False
    assert lua.eval("EscalationIMAC.geometry.leg(a,b,8000,t)") is True


def test_waits_for_dead_and_rechecks_original_blocked_corridor() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("rings[2]={threat(40000,0,5000)};tick(5)")
    assert lua.eval("commander.states.STRIKE.order.kind") == "hold"
    lua.execute("own.STRIKE.point.x=-60000;tick(15)")
    assert lua.eval("commander.states.STRIKE.order.kind") == "hold"
    lua.execute("rings[2]={};tick(25)")
    assert lua.eval("commander.states.STRIKE.order==nil") is True
    assert lua.eval("#recovered") == 0


def test_human_dead_can_support_an_ai_attack_without_receiving_orders() -> None:
    dead = metadata("HUMAN_DEAD", "observe")
    dead["deadSupport"] = True
    lua = runtime([metadata("STRIKE", "strike"), dead])
    lua.execute("own.HUMAN_DEAD.player=true;rings[2]={threat(40000,0,5000)};tick(5)")
    assert lua.eval("commander.states.STRIKE.order.kind") == "hold"
    assert lua.eval("commander.states.HUMAN_DEAD.order==nil") is True


def test_holding_strike_evades_fighters_then_resumes_remaining_dead_wait() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("""
        own.DEAD.point.x=-110000
        rings[2]={threat(40000,0,5000)};tick(5)
        observations[2]={track('fighter',30000,0,-250,'fighter')};tick(15)
    """)
    assert lua.eval("commander.states.STRIKE.order.kind") == "evade"
    assert lua.eval("commander.states.STRIKE.pendingHold.deadline") == 605
    lua.execute("observations[2]={};tick(25);tick(60)")
    assert lua.eval("commander.states.STRIKE.order.kind") == "hold"
    assert lua.eval("commander.states.STRIKE.order.deadline") == 605


def test_fighter_evasion_does_not_restart_dead_wait_timeout() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("""
        own.DEAD.point.x=-110000
        rings[2]={threat(40000,0,5000)};tick(5)
        observations[2]={track('fighter',30000,0,-250,'fighter')};tick(15);tick(610)
    """)
    assert lua.eval("commander.states.STRIKE.finished") is True


@pytest.mark.parametrize(
    "change", ["own.DEAD=nil", "own.DEAD.fuel=.1", "commander.states.DEAD.index=4"]
)
def test_cancels_attack_if_dead_is_unavailable(change: str) -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("rings[2]={threat(40000,0,5000)};" + change + ";tick(5)")
    assert lua.eval("recovered[1]") == "STRIKE"
    assert lua.eval("commander.states.STRIKE.finished") is True


def test_hold_expires_and_does_not_disable_native_bingo() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("rings[2]={threat(40000,0,5000)};tick(5);tick(610)")
    assert lua.eval("recovered[1]") == "STRIKE"


def test_native_hold_expiry_keeps_a_lease_until_recovery_is_installed() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("rings[2]={threat(40000,0,5000)};tick(5);now=610")
    token = lua.eval("commander.states.STRIKE.order.revision")
    assert lua.eval(f"commander:shouldStop('STRIKE',{token})") is False
    assert lua.eval("commander.states.STRIKE.abortReason") == "DEAD wait expired"
    lua.execute("tick(615)")
    assert lua.eval("recovered[1]") == "STRIKE"


def test_failed_recovery_does_not_ignore_manual_pause() -> None:
    lua = runtime([metadata("STRIKE", "strike")])
    lua.execute("rejectRecovery=true;rings[2]={threat(40000,0,5000)};tick(5)")
    assert lua.eval("#recovered") == 1
    assert lua.eval("commander.states.STRIKE.order.kind") == "recoveryHold"
    lua.execute("commander:pause(2,true);tick(50)")
    assert lua.eval("#recovered") == 1


def test_failed_recovery_retains_an_existing_safe_hold() -> None:
    lua = runtime([metadata("STRIKE", "strike"), metadata("DEAD", "dead")])
    lua.execute("rings[2]={threat(40000,0,5000)};tick(5)")
    token = lua.eval("commander.states.STRIKE.order.revision")
    lua.execute("rejectRecovery=true;own.DEAD=nil;tick(15)")
    assert lua.eval("commander.states.STRIKE.order.kind") == "hold"
    assert lua.eval(f"commander:shouldStop('STRIKE',{token})") is False
    lua.execute("rejectRecovery=false;tick(50)")
    assert lua.eval("commander.states.STRIKE.finished") is True


def test_already_ingressing_strike_is_not_restarted_or_retargeted() -> None:
    lua = runtime([metadata("STRIKE", "strike")])
    lua.execute("commander:reached('STRIKE',3);rings[2]={threat(40000,0,5000)};tick(5)")
    assert lua.eval("#sent") == 0
    assert lua.eval("#recovered") == 0


def test_order_errors_back_off_and_history_is_bounded() -> None:
    lua = runtime()
    lua.execute("""
        rejectOrder=true;observations[2]={track('bandit',120000)};tick(5);tick(10)
    """)
    assert lua.eval("#sent") == 1
    lua.execute("for t=100,20000,100 do tick(t)end")
    assert lua.eval("#commander.history") <= 128


def test_single_bend_recovery_never_falls_back_through_a_sam() -> None:
    lua = runtime()
    lua.execute("""
        a={x=0,y=6000,z=0};b={x=100000,y=6000,z=0}
        r={threat(50000,0,10000)}
        path=EscalationIMAC.geometry.detour(a,b,6000,r,adapter.height)
    """)
    assert lua.eval("#path") == 1
    assert lua.eval("EscalationIMAC.geometry.leg(a,path[1],6000,r,10000,true)") is True
    assert lua.eval("EscalationIMAC.geometry.leg(path[1],b,6000,r,10000)") is True
