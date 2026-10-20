"""Standalone probe packaging and raw telemetry, without simulating DCS damage."""

import json
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from dcs.lua import loads
from dcs.unit import Skill

from tools.aircraft_maintenance_probe import SCRIPT, build_mission


@pytest.mark.parametrize("player", ["a10", "hornet"])
def test_probe_mission_contains_isolated_targets_and_embedded_script(
    tmp_path: Path,
    player: str,
) -> None:
    mission = build_mission(player)
    countries = mission.coalition["blue"].countries.values()
    groups = [
        group
        for country in countries
        for group in country.plane_group + country.helicopter_group
    ]
    assert len(groups) == 6
    player_unit = next(u for g in groups for u in g.units if u.name == "PROBE_PLAYER")
    assert player_unit.skill is Skill.Player
    assert "DIAGNOSTIC ONLY" in mission.description_text()
    assert "player is NOT automatically damaged" in mission.description_text()
    targets = [g for g in groups if g.units[0].name.startswith("PROBE_TARGET_")]
    assert len(targets) == 4 and all(g.uncontrolled for g in targets)
    positions = [g.units[0].position for g in targets]
    assert all(
        p.distance_to_point(q) > 100
        for i, p in enumerate(positions)
        for q in positions[i + 1 :]
    )
    assert all(p.distance_to_point(player_unit.position) > 30000 for p in positions)
    output = tmp_path / "probe.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        scripts = [
            archive.read(name) for name in archive.namelist() if name.endswith(".lua")
        ]
        assert SCRIPT.read_bytes() in scripts
        data = loads(archive.read("mission").decode("utf-8"))["mission"]
        assert len(data["trigrules"]) == 1
    arrival = next(g for g in groups if g.units[0].name == "PROBE_RETURNING_A10")
    assert arrival.points[-1].airdrome_id == mission.terrain.airports["Batumi"].id
    approach = mission.terrain.airports["Batumi"].position.point_from_heading(
        mission.terrain.airports["Batumi"].runways[0].heading, 12000
    )
    assert arrival.units[0].position.distance_to_point(approach) < 1
    first_leg = arrival.points[0].position.distance_to_point(arrival.points[1].position)
    assert first_leg == pytest.approx(6000)


@pytest.fixture
def runtime() -> Any:
    lua51 = pytest.importorskip("lupa.lua51")
    vm = lua51.LuaRuntime(unpack_returned_tuples=True)
    vm.execute(r"""
        now = 0
        messages, logs, commands, blasts, units = {}, {}, {}, {}, {}
        env = {info = function(text) logs[#logs + 1] = text end}
        timer = {getTime = function() return now end,
            scheduleFunction = function(fn, arg, at) tick = fn; return 1 end}
        trigger = {action = {
            outText = function(text) messages[#messages + 1] = text end,
            explosion = function(point, power) blasts[#blasts + 1] = {point=point,power=power} end}}
        missionCommands = {
            addSubMenu = function() return 1 end,
            addCommand = function(name, parent, fn) commands[name] = fn end}
        world = {event = {}, addEventHandler = function(handler) eventHandler = handler end}
        for id, name in ipairs({'BIRTH','TAKEOFF','LAND','HIT','KILL','CRASH',
            'DEAD','UNIT_LOST','EJECTION','PILOT_DEAD','PLAYER_LEAVE_UNIT','ENGINE_SHUTDOWN'}) do
            world.event['S_EVENT_' .. name] = id
        end
        Unit = {getByName = function(name) return units[name] end}
        function unit(name, life, life0)
            local obj = {name=name,life=life,life0=life0,exists=true,airborne=true,
                point={x=20,y=100,z=0},side=2}
            function obj:getName() return self.name end
            function obj:getLife() return self.life end
            function obj:getLife0() return self.life0 end
            function obj:isExist() return self.exists end
            function obj:inAir() return self.airborne end
            function obj:getPoint() return self.point end
            function obj:getCoalition() return self.side end
            function obj:getTypeName() return 'Test aircraft' end
            units[name] = obj
            return obj
        end
        ESCALATION_AIRCRAFT_PROBE = {units={'PLAYER','TARGET'},targets={'TARGET'},player='PLAYER',
            bases={{name='Friendly',x=0,z=0,coalition=2},
                   {name='Enemy',x=10000,z=0,coalition=1}}}
        unit('PLAYER', 100, 100)
        unit('TARGET', 100, 100)
        -- Model a normal sanitized mission: the probe must not require file IO.
        lfs, io, os = nil, nil, nil
    """)
    vm.execute(SCRIPT.read_text(encoding="utf-8"))
    return vm


def test_numeric_damage_and_live_reading_before_crash(runtime: Any) -> None:
    runtime.execute("""
        now = 1; tick(nil, now)
        now = 2; units.PLAYER.life = 45; tick(nil, now)
        now = 3; tick(nil, now)
        now = 4; units.PLAYER.life = 0; units.PLAYER.exists = false
        eventHandler:onEvent({id=world.event.S_EVENT_CRASH, initiator=units.PLAYER,time=now})
    """)
    records = runtime.globals().EscalationAircraftProbe.records
    events = [r for r in records.values() if r["kind"] == "event"]
    assert len(events) == 1
    assert events[0]["event"] == "CRASH"
    assert events[0]["prior_life_ratio"] == 0.45
    assert events[0]["prior_time"] == 3
    assert (
        runtime.globals().EscalationAircraftProbe.samples["PLAYER"]["life_ratio"] == 0
    )


def test_landing_has_position_and_place_without_inventing_emergency_status(
    runtime: Any,
) -> None:
    runtime.execute("""
        now = 4
        units.PLAYER.airborne = false
        local place = {getName=function() return 'Batumi' end,
            getCoalition=function() return 2 end,getID=function() return 16 end}
        eventHandler:onEvent({id=world.event.S_EVENT_LAND, initiator=units.PLAYER,place=place,time=now})
        eventHandler:onEvent({id=world.event.S_EVENT_LAND, initiator=units.TARGET,time=now})
    """)
    events = [
        r
        for r in runtime.globals().EscalationAircraftProbe.records.values()
        if r["kind"] == "event"
    ]
    assert events[0]["place_name"] == "Batumi" and events[0]["place_known"]
    assert events[0]["friendly_distance_m"] == 20
    assert events[0]["enemy_distance_m"] == 9980
    assert not events[1]["place_known"]
    assert events[1]["emergency_landing"] is None


def test_ground_attacker_hit_and_confirmed_kill_target_are_logged(runtime: Any) -> None:
    runtime.execute("""
        local attacker = unit('SAM', 10, 10)
        attacker.side = 1
        eventHandler:onEvent({id=world.event.S_EVENT_HIT,initiator=attacker,target=units.PLAYER,time=1})
        eventHandler:onEvent({id=world.event.S_EVENT_KILL,initiator=attacker,target=units.PLAYER,time=2})
        eventHandler:onEvent({id=world.event.S_EVENT_HIT,initiator=units.PLAYER,time=3})
    """)
    events = [
        r
        for r in runtime.globals().EscalationAircraftProbe.records.values()
        if r["kind"] == "event"
    ]
    assert [r["event"] for r in events] == ["HIT", "KILL"]
    assert all(r["name"] == "PLAYER" and r["attacker"] == "SAM" for r in events)


@pytest.mark.parametrize("life,life0", [(None, 100), (20, 0), (-1, 100)])
def test_missing_or_invalid_health_is_unknown(
    runtime: Any, life: Any, life0: int
) -> None:
    runtime.globals().units["PLAYER"]["life"] = life
    runtime.globals().units["PLAYER"]["life0"] = life0
    sample = runtime.globals().EscalationAircraftProbe.sample("PLAYER", "check")
    assert sample["life_ratio"] is None


def test_automatic_blasts_never_target_the_player(runtime: Any) -> None:
    for time in (1, 20, 40, 60, 80, 100):
        runtime.execute(f"now={time}; tick(nil,now)")
    records = runtime.globals().EscalationAircraftProbe.records
    blast_records = [r for r in records.values() if r["kind"] == "blast"]
    assert [r["power_kg_tnt"] for r in blast_records] == [0.1, 1, 5, 20]
    assert all(r["name"] == "TARGET" for r in blast_records)
    assert runtime.globals().units["PLAYER"]["life"] == 100


def test_json_lines_are_valid_and_canopy_marker_does_not_invent_damage(
    runtime: Any,
) -> None:
    runtime.globals().commands["Mark canopy change for comparison"]()
    prefix = "ESCALATION_AIRCRAFT_PROBE "
    lines = [
        json.loads(text[len(prefix) :]) for text in runtime.globals().logs.values()
    ]
    assert any(line.get("reason") == "CANOPY_VISUAL_CHANGED" for line in lines)
    assert (
        runtime.globals().EscalationAircraftProbe.samples["PLAYER"]["life_ratio"] == 1
    )
    assert not lines[0]["separate_log"]


def test_ejection_and_player_departure_are_independent_events(runtime: Any) -> None:
    runtime.execute("""
        now = 1; units.PLAYER.life = 30; tick(nil, now)
        now = 2
        eventHandler:onEvent({id=world.event.S_EVENT_EJECTION,initiator=units.PLAYER,time=now})
        now = 3
        eventHandler:onEvent({id=world.event.S_EVENT_PLAYER_LEAVE_UNIT,initiator=units.PLAYER,time=now})
    """)
    events = [
        r
        for r in runtime.globals().EscalationAircraftProbe.records.values()
        if r["kind"] == "event"
    ]
    assert [r["event"] for r in events] == ["EJECTION", "PLAYER_LEAVE_UNIT"]
    assert events[0]["prior_life_ratio"] == 0.3


def test_automatic_blasts_can_be_cancelled(runtime: Any) -> None:
    runtime.globals().commands["Stop automatic target blasts"]()
    runtime.execute("now=40; tick(nil, now)")
    assert len(runtime.globals().blasts) == 0


def test_initial_sample_and_optional_terrain_height(runtime: Any) -> None:
    assert runtime.globals().EscalationAircraftProbe.samples["PLAYER"]["time"] == 0
    runtime.execute("land = { getHeight = function(point) return 25 end }")
    sample = runtime.globals().EscalationAircraftProbe.sample("PLAYER", "check_agl")
    assert sample["ground_height_m"] == 25
    assert sample["agl_m"] == 75


def test_off_field_variant_disables_automatic_damage(tmp_path: Path) -> None:
    mission = build_mission("a10", "off-field")
    assert "OFF-FIELD LANDING TELEMETRY" in mission.description_text()
    assert "no automatic damage" in mission.description_text()
    assert "at least 30 seconds" in mission.description_text()
    output = tmp_path / "off-field.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        assert b"automatic_damage=false" in archive.read("mission")


def test_off_field_runtime_never_runs_automatic_blasts(runtime: Any) -> None:
    runtime.execute("ESCALATION_AIRCRAFT_PROBE.automatic_damage = false")
    runtime.execute(SCRIPT.read_text(encoding="utf-8"))
    for time in (20, 40, 60, 80, 100):
        runtime.execute(f"now={time}; tick(nil,now)")
    assert len(runtime.globals().blasts) == 0


def test_off_field_transition_and_speed_without_synthetic_landing(runtime: Any) -> None:
    runtime.execute("""
        now = 4
        units.PLAYER.airborne = false
        function units.PLAYER:getVelocity() return {x=3,y=-1,z=4} end
        tick(nil, now)
        now = 5; tick(nil, now)
    """)
    records = list(runtime.globals().EscalationAircraftProbe.records.values())
    transitions = [r for r in records if r["kind"] == "airborne_transition"]
    assert len(transitions) == 1
    assert transitions[0]["from_in_air"] is True
    assert transitions[0]["to_in_air"] is False
    assert transitions[0]["speed_m_s"] == pytest.approx(26**0.5)
    assert transitions[0]["friendly_distance_m"] == 20
    assert not any(r["kind"] == "event" for r in records)
    runtime.globals().commands["Mark off-field landing attempt"]()
    records = list(runtime.globals().EscalationAircraftProbe.records.values())
    assert any(r["reason"] == "OFF_FIELD_LANDING_OBSERVED" for r in records)
    assert not any(r["kind"] == "event" for r in records)


def test_missing_unit_does_not_create_touchdown_or_stationary_evidence(
    runtime: Any,
) -> None:
    runtime.execute("now=1; units.PLAYER=nil; tick(nil,now)")
    records = list(runtime.globals().EscalationAircraftProbe.records.values())
    assert not any(r["kind"] == "airborne_transition" for r in records)
    sample = runtime.globals().EscalationAircraftProbe.samples["PLAYER"]
    assert sample["in_air"] is None
    assert sample["speed_m_s"] is None
