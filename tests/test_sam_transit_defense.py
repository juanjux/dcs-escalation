"""Transit defense stays opt-in and preserves the remaining native route."""

from pathlib import Path
from types import SimpleNamespace as NS
from typing import AbstractSet, Any, cast
from zipfile import ZipFile

from dcs.lua import dumps, loads
from dcs.action import DoScript
from dcs.task import OptAlarmState, OptROE
from dcs.vehicles import vehicle_map
import pytest

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.samdefense import (
    PROFILES,
    transit_defense,
    transit_defense_warning,
)
from game.groundmovement.planning import armor_movement_options, preview_armor_movement
from game.groundmovement.settings import set_enabled
from game.missiongenerator.luagenerator import LuaGenerator
from game.missiongenerator.samtransitdefense import configure
from game.missiongenerator.realisticcasluadata import collect_registry
from game.theater.player import Player
from tests.test_sam_movement import generate_site, make_site, move
from tests.test_armor_movement_planning import world  # noqa: F401


def variants(ids: AbstractSet[str]) -> tuple[str, ...]:
    return tuple(
        next(GroundUnitType.for_dcs_type(vehicle_map[i])).variant_id for i in ids
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_reviewed_profiles_and_mixed_batteries(profile: Any) -> None:
    assert transit_defense(profile.types) is profile
    assert transit_defense([*profile.types, "CH_S350_50N6"]) is None
    assert transit_defense(["CH_SkySabre"]) is None
    assert transit_defense([]) is None


@pytest.mark.parametrize(
    "unit_type",
    [
        "CH_RBS-98",
        "HQ17A",
        "CH_S350_50N6",
        "CH_SkySabre",
        "SA-11 Buk LN 9A310M1",
        "S-300PS 5P85C ln",
    ],
)
def test_unvalidated_systems_are_not_enabled(unit_type: str) -> None:
    assert transit_defense([unit_type]) is None


@pytest.mark.parametrize(
    "types",
    [
        frozenset({"CH_RBS-98"}),
        frozenset({"CH_RBS-98", "CH_UndE23"}),
        frozenset({"CH_RBS-98", "CH_UndE23", "Osa 9A33 ln"}),
    ],
)
def test_rbs98_has_an_explicit_no_transit_defense_restriction(
    types: frozenset[str],
) -> None:
    assert transit_defense(types) is None
    assert "no self-defense during relocation" in (transit_defense_warning(types) or "")


@pytest.mark.parametrize("profile", PROFILES)
def test_validated_profiles_do_not_get_the_rbs98_warning(profile: Any) -> None:
    assert transit_defense_warning(iter(profile.types)) is None


@pytest.mark.parametrize(
    "types", [frozenset({"CH_RBS-98"}), frozenset({"CH_RBS-98", "CH_UndE23"})]
)
def test_rbs98_relocates_packed_with_a_nonblocking_warning(
    world: Any, types: frozenset[str]
) -> None:
    site = make_site(world, variants(types))
    options = armor_movement_options(world.game, site.id, Player.BLUE)
    assert options.enabled and all(unit.selectable for unit in options.units)
    warning = transit_defense_warning(types)
    assert warning is not None and warning in options.warnings
    preview = preview_armor_movement(
        world.game,
        site.id,
        Player.BLUE,
        [unit.id for unit in site.units],
        world.destination,
    )
    assert warning in preview.warnings
    move(world)
    mission, mapping = generate_site(world)
    assert configure(mission, mapping) == []
    group = mission.country("USA").vehicle_group[0]
    assert {unit.type for unit in group.units} == types
    assert len(group.points) >= 2
    assert any(
        isinstance(task, OptAlarmState) and task.value == 1  # GREEN
        for task in group.points[0].tasks
    )
    assert any(
        isinstance(task, OptROE) and task.value == OptROE.Values.WeaponHold
        for task in group.points[0].tasks
    )
    registry = collect_registry(
        mission, cast(Any, NS(flights=[])), enabled=True, unit_map=mapping
    )
    assert registry is not None and registry["airDefenseThreats"] == []


@pytest.mark.parametrize(
    "unit_type,range_m,ceiling_m,min_range_m",
    [
        ("ZSU_57_2", 7000, 4000, 0),
        ("ZSU-23-4 Shilka", 2500, None, 0),
        ("CHAP_PantsirS1", 12000, 10000, 0),
        ("CHAP_TorM2", 12000, 12000, 1500),
        ("Tor 9A331", 12000, 6000, 1500),
        ("Vulcan", 2000, None, 0),
        ("Roland ADS", 8000, 6000, 500),
        ("Ural-375 ZU-23", 2500, None, 0),
        ("CH_Centurion_C_RAM", 2000, None, 0),
        ("CH_PantsirS2", 12000, 18000, 0),
        ("CH_StormerHVM", 7000, 7000, 300),
        ("CH_FlaRakRad", 8000, 6000, 500),
        ("CH_LvKv9040", 4000, 2500, 0),
        ("PGL_625", 8000, 5000, 0),
        ("M1097 Avenger", 4500, 3500, 0),
        ("M6 Linebacker", 4500, 3500, 0),
        ("Strela-10M3", 5000, 3500, 800),
        ("Strela-1 9P31", 4200, 3500, 800),
        ("CH_LAVAD", 8000, 4800, 0),
        ("CH_BoxerSkyranger", 8000, 4800, 0),
        ("CH_Wiesel2Ozelot", 8000, 4800, 0),
    ],
)
def test_additional_reviewed_profiles_preserve_weapon_bounds(
    unit_type: str, range_m: int, ceiling_m: int | None, min_range_m: int
) -> None:
    profile = transit_defense([unit_type])
    assert profile is not None
    assert profile.range_m == range_m
    assert profile.ceiling_m == ceiling_m
    assert profile.min_range_m == min_range_m


@pytest.mark.parametrize("profile", PROFILES)
def test_exported_registry_and_trigger_preserve_route(
    world: Any, tmp_path: Path, profile: Any
) -> None:
    make_site(world, variants(profile.types))
    move(world)
    mission, mapping = generate_site(world)
    registry = collect_registry(
        mission, cast(Any, NS(flights=[])), enabled=True, unit_map=mapping
    )
    assert registry is not None and registry["airDefenseThreats"]
    for threat in registry["airDefenseThreats"]:
        assert threat["transitDefense"] is True and "initialPoint" not in threat
    generator = LuaGenerator(world.game, mission, cast(Any, NS()), mapping)
    generator._inject_sam_transit_defense()
    trigger = mission.triggerrules.triggers[-1]
    path = tmp_path / "transit-defense.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        data = loads(archive.read("mission").decode())["mission"]
        assert any(n.endswith("sam_transit_defense.lua") for n in archive.namelist())
    preamble = cast(DoScript, trigger.actions[0]).text.id
    rows = loads(preamble)["ESCALATION_SAM_TRANSIT_CONFIG"]
    row = rows[1]
    assert row["range"] == profile.range_m
    assert row.get("ceiling") == profile.ceiling_m
    assert row["minRange"] == profile.min_range_m
    assert len(row["units"]) == len(profile.types)
    assert len(row["route"]) >= 2
    for index, point in row["route"].items():
        scripts = [
            t["params"]["action"]
            for t in point["task"]["params"]["tasks"].values()
            if t["id"] == "WrappedAction"
        ]
        assert any(
            a["id"] == "Script" and f",{index})" in a["params"]["command"]
            for a in scripts
        )
    assert data["trigrules"]
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    lua.execute(preamble)
    assert lua.eval("#ESCALATION_SAM_TRANSIT_CONFIG") == 1
    for point in row["route"].values():
        for task in point["task"]["params"]["tasks"].values():
            action = task.get("params", {}).get("action", {})
            if action.get("id") == "Script":
                lua.compile(action["params"]["command"])


def test_no_runtime_for_paused_unknown_or_loaded_batteries(world: Any) -> None:
    make_site(world)
    move(world)
    mission, mapping = generate_site(world)
    assert configure(mission, mapping) == []
    assert configure(mission, None) == []


def test_eligible_paused_site_stays_packed(world: Any) -> None:
    make_site(world, variants(PROFILES[0].types))
    move(world)
    set_enabled(world.game.settings, False)
    mission, mapping = generate_site(world)
    assert configure(mission, mapping) == []


@pytest.fixture
def runtime() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    lua.execute("""
    NOW=0;LOGS={};TASKS={};COMMANDS={};OPTIONS={};CONTACTS={}
    env={info=function(s)LOGS[#LOGS+1]=s end}
    timer={getTime=function()return NOW end,scheduleFunction=function(fn)TICK=fn end}
    world={event={S_EVENT_HIT=2,S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=3},addEventHandler=function(h)HANDLER=h end}
    Object={Category={UNIT=1,WEAPON=2}};Unit={Category={AIRPLANE=0,HELICOPTER=1}}
    function Object.getCategory(u)return u:getCategory()end
    own={alive=true,player=nil,p={x=230,y=0,z=100}}
    function own:getName()return 'own' end
    function own:isExist()return self.alive end
    function own:getLife()return self.alive and 100 or 0 end
    function own:getPoint()return self.p end
    function own:getPlayerName()return self.player end
    function own:getCoalition()return 2 end
    ctrl={}
    function ctrl:setOption(id,value)OPTIONS[id]=value end
    function ctrl:setCommand(c)COMMANDS[#COMMANDS+1]=c end
    function ctrl:setTask(t)TASKS[#TASKS+1]=t end
    function ctrl:resetTask()error('must not reset native reloading')end
    function ctrl:getDetectedTargets()
      if NATIVE_ALARM_GATING and OPTIONS[9]==1 then return{}end
      return CONTACTS
    end
    function ctrl:isTargetDetected()return true end
    g={}
    function g:getUnits()return own.alive and {own}or{}end
    function g:getUnit()return own end
    function g:getController()return ctrl end
    Group={getByName=function(n)return n=='battery' and g or nil end}
    function step(t)NOW=t;TICK(nil,NOW)end
    function hit()HANDLER:onEvent({id=2,target=own})end
    function fire()HANDLER:onEvent({id=1,initiator=own})end
    function aircraft(side,x,y)
      local u={}
      function u:isExist()return true end
      function u:getLife()return 100 end
      function u:getCategory()return 1 end
      function u:getCoalition()return side end
      function u:getDesc()return {category=0}end
      function u:getPoint()return {x=x,y=y or 100,z=100}end
      return {object=u}
    end
    """)
    points = [
        dict(
            x=i * 100,
            y=100,
            alt=0,
            alt_type="BARO",
            speed=11 if i == 4 else 5,
            action="On Road" if i == 4 else "Off Road",
            type="Turning Point",
            ETA_locked=False,
            task=dict(id="ComboTask", params=dict(tasks=[])),
        )
        for i in range(1, 5)
    ]
    lua.execute(
        "ESCALATION_SAM_TRANSIT_CONFIG="
        + dumps(
            [
                dict(
                    name="battery",
                    units=["own"],
                    range=10000,
                    ceiling=5000,
                    minRange=500,
                    route=points,
                )
            ]
        )
    )
    lua.execute(
        Path("resources/plugins/base/sam_transit_defense.lua").read_text("utf-8")
    )
    return lua


def test_hit_quiet_pack_and_resume_without_skipping_or_restarting_route(
    runtime: Any,
) -> None:
    runtime.execute("""
    step(5);assert(#TASKS==1 and not ESCALATION_SAM_TRANSIT.active.battery)
    ESCALATION_SAM_TRANSIT.reached('battery',2)
    hit();assert(ESCALATION_SAM_TRANSIT.active.battery and OPTIONS[9]==2 and OPTIONS[0]==0)
    step(94);assert(#TASKS==1)
    step(95);assert(not ESCALATION_SAM_TRANSIT.active.battery and OPTIONS[9]==1 and OPTIONS[0]==4)
    step(214);assert(#TASKS==1)
    step(215);assert(#TASKS==2)
    local route=TASKS[2].params.route.points
    assert(#route==3 and route[1].x==230 and route[1].y==100)
    assert(route[2].x==300 and route[3].x==400 and route[3].action=='On Road' and route[3].speed==11)
    assert(COMMANDS[#COMMANDS].params.value==false)
    step(1000);step(3000);assert(#TASKS==2,'must leave native reloading alone')
    """)


def test_native_detection_is_available_on_initial_march_and_after_recovery(
    runtime: Any,
) -> None:
    runtime.execute("""
    -- Model the native GREEN blindness observed in the sensor posture probe.
    NATIVE_ALARM_GATING=true
    step(5)
    assert(OPTIONS[9]==0 and OPTIONS[0]==4 and #TASKS==1)
    assert(not ESCALATION_SAM_TRANSIT.active.battery)
    CONTACTS={aircraft(2,2000),aircraft(1,999999)};step(10)
    assert(not ESCALATION_SAM_TRANSIT.active.battery and OPTIONS[0]==4)
    CONTACTS={aircraft(1,2000)};step(15)
    assert(ESCALATION_SAM_TRANSIT.active.battery and OPTIONS[9]==2 and OPTIONS[0]==0)
    fire();CONTACTS={};step(105)
    assert(OPTIONS[9]==1 and OPTIONS[0]==4)
    step(225)
    assert(OPTIONS[9]==0 and OPTIONS[0]==4 and #TASKS==2)
    assert(ESCALATION_SAM_TRANSIT.groups.battery.phase=='MARCH')
    CONTACTS={aircraft(1,2000)};step(230)
    assert(ESCALATION_SAM_TRANSIT.active.battery and #TASKS==2)
    fire();CONTACTS={};step(320);step(440)
    assert(OPTIONS[9]==0 and OPTIONS[0]==4 and #TASKS==3)
    assert(not ESCALATION_SAM_TRANSIT.active.battery)
    """)


def test_contacts_and_shots_extend_defense_but_friendly_or_far_contacts_do_not(
    runtime: Any,
) -> None:
    runtime.execute("""
    hit();CONTACTS={aircraft(1,1000)};step(100)
    assert(ESCALATION_SAM_TRANSIT.active.battery)
    CONTACTS={aircraft(2,1000),aircraft(1,999999)}
    step(180);fire();step(260);assert(ESCALATION_SAM_TRANSIT.active.battery)
    step(270);assert(not ESCALATION_SAM_TRANSIT.active.battery)
    """)


def test_detection_in_range_starts_defense_without_a_hit(runtime: Any) -> None:
    runtime.execute("""
    CONTACTS={aircraft(1,2000)};step(5)
    assert(ESCALATION_SAM_TRANSIT.active.battery and OPTIONS[9]==2 and OPTIONS[0]==0)
    assert(COMMANDS[#COMMANDS].params.value==true and #TASKS==1)
    CONTACTS={};step(95);assert(not ESCALATION_SAM_TRANSIT.active.battery)
    CONTACTS={aircraft(1,2000)};step(100)
    assert(ESCALATION_SAM_TRANSIT.active.battery and #TASKS==1)
    """)


def test_detection_envelope_uses_slant_range_and_launcher_relative_height(
    runtime: Any,
) -> None:
    runtime.execute("""
    CONTACTS={aircraft(0,2000),aircraft(2,2000),aircraft(1,200),aircraft(1,11000),aircraft(1,2000,5001)}
    step(5);assert(not ESCALATION_SAM_TRANSIT.active.battery)
    -- Horizontal range alone would admit this target, but slant range does not.
    CONTACTS={aircraft(1,10000,4000)};step(10)
    assert(not ESCALATION_SAM_TRANSIT.active.battery)
    -- A high-altitude plateau must not be mistaken for target height above the site.
    own.p.y=6000;CONTACTS={aircraft(1,2000,6500)};step(15)
    assert(ESCALATION_SAM_TRANSIT.active.battery)
    """)


def test_arrival_does_not_restart_transit_defense_from_detections(runtime: Any) -> None:
    runtime.execute("""
    ESCALATION_SAM_TRANSIT.reached('battery',4);step(5)
    CONTACTS={aircraft(1,2000)};step(10)
    assert(ESCALATION_SAM_TRANSIT.groups.battery.phase=='ARRIVED' and #TASKS==0)
    assert(not ESCALATION_SAM_TRANSIT.active.battery)
    """)


def test_new_hit_during_packing_redeploys_and_manual_control_is_not_overridden(
    runtime: Any,
) -> None:
    runtime.execute("""
    hit();step(90);assert(not ESCALATION_SAM_TRANSIT.active.battery)
    step(100);hit();assert(ESCALATION_SAM_TRANSIT.active.battery)
    own.player='commander';step(105)
    local count=#COMMANDS;step(1000);hit();assert(#COMMANDS==count and #TASKS==0)
    """)


def test_stale_contacts_do_not_read_enemy_positions_and_arrival_stays_at_destination(
    runtime: Any,
) -> None:
    runtime.execute("""
    local stale=aircraft(1,1000)
    function stale.object:getPoint()error('must not read a stale contact position')end
    CONTACTS={stale};function ctrl:isTargetDetected()return false end
    ESCALATION_SAM_TRANSIT.reached('battery',4)
    hit();step(90);step(210)
    assert(#TASKS==0 and not ESCALATION_SAM_TRANSIT.active.battery)
    assert(ESCALATION_SAM_TRANSIT.groups.battery.phase=='ARRIVED')
    for _,s in ipairs(LOGS)do assert(not string.find(s,'ERROR',1,true))end
    """)


def test_weapon_contacts_and_destroyed_groups_do_not_crash_or_reset(
    runtime: Any,
) -> None:
    runtime.execute("""
    local w={}
    function w:isExist()return true end
    function w:getCategory()return 2 end
    function w:getLife()error('weapons have no life getter')end
    CONTACTS={{object=w}};hit();step(90)
    own.alive=false;step(100);step(1000)
    assert(#TASKS==0 and not ESCALATION_SAM_TRANSIT.active.battery)
    for _,s in ipairs(LOGS)do assert(not string.find(s,'ERROR',1,true))end
    """)
