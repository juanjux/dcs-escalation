"""Returning combat-capable flights can temporarily reinforce the intercept pool."""

from typing import Any

import pytest

from .test_imac import metadata, runtime


def returning(mode: str = "strike", side: int = 2) -> Any:
    meta = metadata("RETURN", mode, side)
    meta.update(returnInterceptor=True, returnStartIndex=4, approachIndex=5)
    lua = runtime([meta])
    lua.execute("own.CAP.ammo=false; observations[2]={track('bomber',80000)}")
    return lua


@pytest.mark.parametrize("mode", ["strike", "dead", "observe", "support"])
def test_only_finished_missions_can_be_reassigned(mode: str) -> None:
    lua = returning(mode)
    lua.execute("tick(5)")
    assert lua.eval("#sent") == 0
    lua.execute("commander:reached('RETURN',4); tick(15)")
    assert lua.eval("#sent") == 1
    assert lua.eval("sent[1].group") == "RETURN"
    assert lua.eval("sent[1].kind") == "intercept"
    lua.execute("observations[2]={}; tick(25)")
    assert lua.eval("commander.states.RETURN.order==nil") is True
    assert lua.eval("commander.states.RETURN.index") == 4
    assert lua.eval("#recovered") == 0


@pytest.mark.parametrize(
    "change",
    [
        "commander.states.RETURN.meta.returnInterceptor=false",
        "commander.states.RETURN.index=3",
        "commander.states.RETURN.index=5",
        "commander.states.RETURN.finished=true",
        "own.RETURN.ammo=false",
        "own.RETURN.fuel=.4",
        "own.RETURN.player=true",
        "own.RETURN.healthy=false",
        "own.RETURN.refuelling=true",
        "own.RETURN.airborne=false",
        "commander:pauseFlight('RETURN',true)",
        "auth[2]=false",
        "rings[2]={threat(40000,0,10000)}",
        "own.RETURN.point={x=-50000,y=1200,z=0}",
    ],
)
def test_returning_interceptors_keep_native_safety_limits(change: str) -> None:
    lua = returning("observe")
    lua.execute("commander:reached('RETURN',4); " + change + "; tick(5)")
    assert lua.eval("commander.states.RETURN.order==nil") is True


def test_expired_patrol_can_help_while_returning_but_not_before_split() -> None:
    lua = returning("cap")
    lua.execute("commander.states.RETURN.meta.endTime=1; tick(5)")
    assert lua.eval("#sent") == 0
    lua.execute("commander:reached('RETURN',4); tick(15)")
    assert lua.eval("sent[1].group") == "RETURN"


def test_nearest_ready_flight_is_selected_across_patrols_and_returning_fighters() -> (
    None
):
    lua = returning("observe")
    lua.execute("""
        own.CAP.ammo=true; own.CAP.point.x=-30000
        commander:reached('RETURN',4); tick(5)
    """)
    assert lua.eval("#sent") == 1
    assert lua.eval("sent[1].group") == "RETURN"


def test_returning_red_fighters_follow_the_same_rules() -> None:
    meta = metadata("RETURN", "observe", 1)
    meta.update(returnInterceptor=True, returnStartIndex=4, approachIndex=5)
    lua = runtime([meta])
    lua.execute("""
        auth[2]=false; observations[1]={track('bomber',80000)}
        commander:reached('RETURN',4); tick(5)
    """)
    assert lua.eval("sent[1].group") == "RETURN"


def test_missiles_are_independent_targets_without_group_ids() -> None:
    lua = runtime([metadata("SECOND", "cap")])
    lua.execute("""
        local a=track('one',80000,0,-250,'missile'); a.groupId=nil; a.point.y=100
        local b=track('two',90000,0,-250,'missile'); b.groupId=nil; b.point.y=100
        observations[2]={a,b}; tick(5)
    """)
    assert lua.eval("#sent") == 2
    assert lua.eval("sent[1].data.reservation~=sent[2].data.reservation") is True
    assert lua.eval("sent[1].data.missile and sent[2].data.missile") is True


def test_low_flying_missile_does_not_request_a_low_altitude_fighter_transit() -> None:
    lua = returning("observe")
    lua.execute("""
        local m=track('missile',80000,0,-250,'missile'); m.point.y=100
        observations[2]={m}; commander:reached('RETURN',4); tick(5)
    """)
    assert lua.eval("#sent") == 1
    assert lua.eval("sent[1].data.missile") is True
    lua.execute("tick(15)")
    assert lua.eval("commander.states.RETURN.order~=nil") is True
