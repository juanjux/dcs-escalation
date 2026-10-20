"""Exercise the production observer in Lua 5.1 without inventing DCS physics."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest

from game.aircraftmaintenance import parse_reports

SCRIPT = Path("resources/plugins/base/aircraft_maintenance.lua")


@pytest.fixture
def vm() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now = 0
        dirty_state = false
        timer = {getTime=function() return now end,
            scheduleFunction=function(fn, arg, at) tick=fn end}
        world = {event={},addEventHandler=function(handler) observer=handler end}
        for id,name in ipairs({'HIT','KILL','LAND','EJECTION','CRASH','DEAD',
            'UNIT_LOST','PLAYER_LEAVE_UNIT','TAKEOFF'}) do
            world.event['S_EVENT_' .. name] = id
        end
        plane = {life=100,maximum=100,airborne=true,exists=true,velocity=50}
        function plane:getName() return 'tracked' end
        function plane:getLife() return self.life end
        function plane:getLife0() return self.maximum end
        function plane:isExist() return self.exists end
        function plane:inAir() return self.airborne end
        function plane:getPoint() return {x=30,y=10,z=40} end
        function plane:getVelocity() return {x=self.velocity,y=0,z=0} end
        Unit = {getByName=function(name)
            if name == 'tracked' and plane.exists then return plane end
        end}
        ESCALATION_AIRCRAFT_MAINTENANCE = {mission_id='test-mission',units={'tracked'}}
        function emit(name)
            observer:onEvent({id=world.event['S_EVENT_' .. name],time=now,initiator=plane})
        end
        function step(time) now=time; tick(nil,now) end
    """)
    lua.execute(SCRIPT.read_text(encoding="utf-8"))
    return lua


def state(vm: Any) -> Any:
    return vm.globals().aircraft_damage_state[1]


def test_scripted_damage_updates_state_without_hit_and_marks_writer_dirty(
    vm: Any,
) -> None:
    vm.execute("dirty_state=false; plane.life=45; step(5)")
    assert state(vm)["health"] == 0.45
    assert state(vm)["first_damage_time"] == 5
    assert vm.globals().dirty_state is True
    assert vm.globals().aircraft_damage_mission_id == "test-mission"


def test_off_field_native_landing_needs_alive_stationary_thirty_seconds(
    vm: Any,
) -> None:
    vm.execute("plane.airborne=false; plane.velocity=25; step(10); emit('LAND')")
    vm.execute("plane.velocity=0; step(20); step(49)")
    assert not state(vm)["recovered"]
    vm.execute("dirty_state=false; step(50)")
    assert state(vm)["recovered"] is True
    assert state(vm)["landing_place"] is None
    assert (state(vm)["x"], state(vm)["z"]) == (30, 40)
    assert vm.globals().dirty_state is True


def test_ground_state_without_landing_event_is_not_recovery(vm: Any) -> None:
    vm.execute("plane.airborne=false; plane.velocity=0; step(10); step(50)")
    assert not state(vm)["recovered"]


def test_aircraft_starting_parked_has_not_returned_from_a_sortie(vm: Any) -> None:
    vm.execute("plane.airborne=false; plane.velocity=0")
    vm.execute(SCRIPT.read_text(encoding="utf-8"))
    vm.execute("step(10); emit('LAND'); step(50)")
    assert state(vm)["was_airborne"] is False
    assert not state(vm)["recovered"]


def test_alive_damaged_return_preserves_health_through_player_despawn(vm: Any) -> None:
    vm.execute(
        "plane.life=40; plane.airborne=false; plane.velocity=0; step(10); emit('LAND'); step(40)"
    )
    assert state(vm)["recovered"] is True
    vm.execute(
        "emit('PLAYER_LEAVE_UNIT'); plane.life=0; emit('DEAD'); plane.exists=false; step(45)"
    )
    assert state(vm)["health"] == 0.4
    assert state(vm)["recovered"] is True
    assert state(vm)["crash_time"] is None


@pytest.mark.parametrize("terminal", ["EJECTION", "CRASH", "DEAD", "UNIT_LOST"])
def test_terminal_events_override_prior_return_without_slot_leave(
    vm: Any, terminal: str
) -> None:
    vm.execute(
        "plane.airborne=false; plane.velocity=0; step(10); emit('LAND'); step(40)"
    )
    vm.execute(f"emit('{terminal}')")
    assert state(vm)["recovered"] is False


def test_preimpact_damage_survives_final_zero_but_new_impact_is_not_preexisting(
    vm: Any,
) -> None:
    vm.execute("plane.life=40; step(10); step(15); now=20; plane.life=0; emit('CRASH')")
    report = parse_reports([dict(state(vm))])["tracked"]
    assert report.crashed and report.pre_crash_health == 0.4
    vm.execute("plane.life=100; plane.airborne=true; now=0")
    vm.execute(SCRIPT.read_text(encoding="utf-8"))
    vm.execute("plane.life=40; step(20); emit('CRASH')")
    report = parse_reports([dict(state(vm))])["tracked"]
    assert report.pre_crash_health is None


def test_takeoff_revokes_previous_landing_evidence(vm: Any) -> None:
    vm.execute(
        "plane.airborne=false; plane.velocity=0; step(10); emit('LAND'); step(40)"
    )
    vm.execute(
        "plane.airborne=true; step(41); plane.airborne=false; step(42); step(80)"
    )
    assert state(vm)["landing_time"] is None
    assert state(vm)["recovered"] is False


def test_target_event_never_uses_shooter_when_target_is_absent(vm: Any) -> None:
    vm.execute("emit('HIT')")
    assert state(vm)["hit"] is None
    vm.execute("observer:onEvent({id=world.event.S_EVENT_KILL,target=plane,time=2})")
    assert state(vm)["killed"] is True


def test_missing_life_denominator_allows_confirmed_binary_damage(vm: Any) -> None:
    vm.execute("""
        plane.maximum=0
        plane.airborne=false; plane.velocity=0; step(10); emit('LAND')
        observer:onEvent({id=world.event.S_EVENT_HIT,target=plane,time=15})
        step(40)
    """)
    assert state(vm)["health"] is None
    assert state(vm)["recovered"] is True
    assert state(vm)["hit"] is True


def test_stationary_on_a_moving_carrier_uses_relative_motion(vm: Any) -> None:
    vm.execute("""
        local deck = {getID=function() return 777 end,
            getPoint=function() return {x=now*15,y=0,z=0} end}
        plane.airborne=false; plane.velocity=15; step(10)
        observer:onEvent({id=world.event.S_EVENT_LAND,initiator=plane,place=deck,time=now})
        step(11); step(40); step(41)
    """)
    assert state(vm)["recovered"] is True
    assert state(vm)["landing_place"] == 777


def test_carrier_airbase_name_survives_string_runtime_ids_and_resets_on_takeoff(
    vm: Any,
) -> None:
    vm.execute("""
        local deck = {getID=function() return '501' end,
            getName=function() return 'CVN native name' end,
            getPoint=function() return {x=now*15,y=0,z=0} end}
        plane.life=65; plane.airborne=false; plane.velocity=15; step(10)
        observer:onEvent({id=world.event.S_EVENT_LAND,initiator=plane,place=deck,time=now})
        step(11); step(41)
    """)
    report = parse_reports([dict(state(vm))])["tracked"]
    assert report.recovered and report.health == 0.65
    assert report.landing_place == 501 and report.landing_name == "CVN native name"
    vm.execute("plane.airborne=true; step(42)")
    assert state(vm)["landing_name"] is None


def test_unrelated_weapon_events_do_not_sample_aircraft(vm: Any) -> None:
    vm.execute("""
        plane.life=40; now=5
        observer:onEvent({id=9999,initiator=plane,time=now})
    """)
    assert state(vm)["health"] == 1


def test_collision_is_not_misclassified_as_a_weapon_kill(vm: Any) -> None:
    vm.execute("""
        plane.life=45; step(5); step(10); now=20
        local attacker = {getTypeName=function() return 'Aircraft' end}
        observer:onEvent({id=world.event.S_EVENT_KILL,initiator=attacker,
            weapon=attacker,target=plane,time=now})
    """)
    report = parse_reports([dict(state(vm))])["tracked"]
    assert not report.killed
    assert report.crashed and report.pre_crash_health == 0.45


@pytest.mark.parametrize("enabled", [False, True])
def test_generated_mission_embeds_observer_only_when_enabled(
    tmp_path: Path, enabled: bool
) -> None:
    from dcs import Mission
    from dcs.terrain import Caucasus
    from game.missiongenerator.luagenerator import LuaGenerator
    from game.settings import Settings

    settings = Settings()
    settings.aircraft_maintenance_enabled = enabled
    game: Any = SimpleNamespace(settings=settings)
    data: Any = SimpleNamespace()
    mapping: Any = SimpleNamespace(aircraft={"Campaign plane": object()})
    mission = Mission(Caucasus())
    generator = LuaGenerator(game, mission, data, mapping)
    generator._inject_aircraft_maintenance()
    assert len(mission.triggerrules.triggers) == int(enabled)
    target = tmp_path / "maintenance.miz"
    mission.save(str(target))
    with ZipFile(target) as archive:
        scripts = [
            archive.read(name) for name in archive.namelist() if name.endswith(".lua")
        ]
        assert (SCRIPT.read_bytes() in scripts) == enabled
        assert (
            b"ESCALATION_AIRCRAFT_MAINTENANCE" in archive.read("mission")
        ) == enabled
