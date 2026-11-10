"""Independent SAM and fighter-evasion switches retain other safety constraints."""

import pytest

from .test_imac import metadata, runtime


@pytest.mark.parametrize("avoid", [False, True])
def test_strike_sam_holds_and_cancellations_follow_the_switch(avoid: bool) -> None:
    lua = runtime([metadata("STRIKE", "strike")])
    lua.globals().avoid = avoid
    lua.execute("""
        cfg.options.avoidSamThreats=avoid
        rings[2]={threat(40000,0,5000)};tick(5)
    """)
    assert lua.eval("commander.states.STRIKE.finished or false") is avoid
    assert lua.eval("#recovered") == (1 if avoid else 0)


@pytest.mark.parametrize("avoid", [False, True])
def test_cap_intercept_sam_limits_follow_the_switch(avoid: bool) -> None:
    lua = runtime()
    lua.globals().avoid = avoid
    lua.execute("""
        cfg.options.avoidSamThreats=avoid
        rings[2]={threat(60000,0,10000)}
        observations[2]={track('bomber',120000)};tick(5)
    """)
    assert lua.eval("commander.states.CAP.order~=nil") is not avoid


def test_disabling_sam_avoidance_does_not_disable_terrain_limits() -> None:
    lua = runtime()
    lua.execute("""
        cfg.options.avoidSamThreats=false;terrainHeight=5900
        observations[2]={track('bomber',120000)};tick(5)
        assert(commander.states.CAP.order==nil)
    """)


@pytest.mark.parametrize("role", ["DEAD", "SEAD", "SEAD Escort", "SEAD Sweep"])
@pytest.mark.parametrize(
    "avoid,exempt", [(False, False), (False, True), (True, False), (True, True)]
)
def test_returning_sead_fighters_use_the_effective_exemption(
    role: str, avoid: bool, exempt: bool
) -> None:
    meta = metadata("RETURNING", "dead")
    meta.update(
        seadMission=True, returnInterceptor=True, returnStartIndex=2, approachIndex=5
    )
    lua = runtime([meta])
    lua.globals().avoid = avoid
    lua.globals().exempt = exempt
    lua.execute("""
        cfg.options.avoidSamThreats=avoid;cfg.options.neverDivertSead=exempt
        own.CAP=nil
        rings[2]={threat(60000,0,10000)}
        observations[2]={track('bomber',120000)};tick(5)
    """)
    assert lua.eval("commander.states.RETURNING.order~=nil") is (not avoid or exempt)


@pytest.mark.parametrize("exempt", [False, True])
def test_sead_sam_exemption_also_applies_to_its_original_attack_route(
    exempt: bool,
) -> None:
    lua = runtime([metadata("DEAD", "dead")])
    lua.globals().exempt = exempt
    lua.execute("""
        cfg.options.neverDivertSead=exempt
        rings[2]={threat(40000,0,5000)};tick(5)
    """)
    assert lua.eval("commander.states.DEAD.finished or false") is not exempt
    assert lua.eval("commander.states.DEAD.order==nil") is True


@pytest.mark.parametrize(
    "evade,exempt", [(False, False), (False, True), (True, False), (True, True)]
)
@pytest.mark.parametrize("role", ["Escort", "Fighter Sweep"])
def test_escort_and_sweep_evasion_use_their_own_exemption(
    role: str, evade: bool, exempt: bool
) -> None:
    meta = metadata("COMBAT", "combat")
    meta["fighterMission"] = True
    lua = runtime([meta])
    lua.globals().evade = evade
    lua.globals().exempt = exempt
    lua.execute("""
        cfg.options.evadeFighters=evade;cfg.options.neverEvadeFighterMissions=exempt
        own.COMBAT.point.x=-80000
        observations[2]={track('fighter',-110000,0,250,'fighter')};tick(5)
    """)
    assert lua.eval("commander.states.COMBAT.order~=nil") is (evade and not exempt)


@pytest.mark.parametrize("evade", [False, True])
def test_fighter_switch_controls_protective_evasion_not_interception(
    evade: bool,
) -> None:
    lua = runtime([metadata("DEAD", "dead")])
    lua.globals().evade = evade
    lua.execute("""
        cfg.options.evadeFighters=evade
        own.DEAD.point.x=-80000
        observations[2]={track('fighter',-110000,0,250,'fighter')};tick(5)
    """)
    assert lua.eval("commander.states.DEAD.order~=nil") is evade
    lua.execute("observations[2]={track('bomber',120000)};tick(15);tick(50)")
    assert lua.eval("commander.states.CAP.order.kind") == "intercept"


def test_support_aircraft_keep_sam_safe_evasion_when_strike_avoidance_is_off() -> None:
    lua = runtime()
    lua.execute("""
        cfg.options.avoidSamThreats=false
        rings[2]={threat(-130000,0,10000)}
        observations[2]={track('fighter',-70000,0,-250,'fighter')};tick(5)
        local q=commander.states.AWACS.order.data.point
        assert(EscalationIMAC.geometry.leg(own.AWACS.point,q,6000,rings[2],10000,true))
    """)
