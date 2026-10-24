"""Mission selection, patrols and final AFAC sensor metadata."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from dcs import Mission
from dcs.mapping import Point
from dcs.task import AFAC, Nothing, OptROE, RunScript, SetUnlimitedFuelCommand

from game import persistency
from game.ato import Flight, FlightType
from game.ato.afac import enabled, station_minutes
from game.ato.flightplans.afac import AfacFlightPlan
from game.ato.flightplans.flightplanbuildertypes import FlightPlanBuilderTypes
from game.dcs.afaccapabilities import capabilities_for
from game.dcs.aircrafttype import AircraftType
from game.dcs.skills import CADET_SKILL
from game.missiongenerator.aircraft.aircraftbehavior import AircraftBehavior
from game.missiongenerator.aircraft.waypoints.afac import AfacSearchBuilder
from game.missiongenerator.aircraft.waypoints.racetrackend import RaceTrackEndBuilder
from game.missiongenerator.realisticcasluadata import (
    _native_route_value,
    collect_registry,
    lua_literal,
)
from game.settings import Settings
from game.squadrons.squadron import Squadron
from game.utils import feet


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), False, 0)


def scenario(
    task: FlightType = FlightType.AFAC_AREA, variant: str = "MQ-9 Reaper"
) -> Any:
    settings = Settings()
    settings.plugins.update({"realisticcas": True, "realisticcas.afacEnabled": True})
    settings.live_pilots_enabled = False
    settings.ai_unlimited_fuel = True
    mission = Mission()
    aircraft = AircraftType.named(variant)
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "AFAC",
        aircraft.dcs_unit_type,
        Point(0, 0, mission.terrain),
        3000,
        speed=250,
    )
    group.points[0].tasks.clear()
    layout: Any = NS(
        patrol_start=NS(position=Point(-2000, 0, mission.terrain), alt=feet(10000)),
        patrol_end=NS(position=Point(2000, 0, mission.terrain)),
    )
    flight: Any = NS(
        flight_type=task,
        unit_type=aircraft,
        is_helo=aircraft.helicopter,
        client_count=0,
        package=NS(target=NS(position=Point(0, 0, mission.terrain))),
        state=NS(is_at_ip=False, in_combat=False),
        squadron=NS(settings=settings, coalition=NS(game=NS(settings=settings))),
        coalition=NS(game=NS(settings=settings)),
    )
    plan = AfacFlightPlan(flight, layout)
    flight.flight_plan = plan
    return NS(settings=settings, mission=mission, group=group, flight=flight, plan=plan)


@pytest.mark.parametrize(
    "plugin,afac", [(False, False), (False, True), (True, False), (True, True)]
)
def test_two_switches_gate_squadron_availability(plugin: bool, afac: bool) -> None:
    s = scenario()
    s.settings.plugins.update(
        {"realisticcas": plugin, "realisticcas.afacEnabled": afac}
    )
    squadron: Any = NS(aircraft=s.flight.unit_type, settings=s.settings)
    assert enabled(s.settings) == (plugin and afac)
    assert Squadron.capable_of(squadron, FlightType.AFAC_AREA) == (plugin and afac)


def test_catalogue_aircraft_gain_both_tasks_but_other_aircraft_do_not() -> None:
    for aircraft in AircraftType.iter_all():
        compatible = capabilities_for(aircraft.dcs_id) is not None
        assert aircraft.capable_of(FlightType.AFAC_AREA) == compatible
        assert aircraft.capable_of(FlightType.AFAC_FRONTLINE) == compatible


@pytest.mark.parametrize("task", [FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE])
def test_noncombat_task_has_its_own_plan_zone_and_duration(task: FlightType) -> None:
    s = scenario(task)
    assert task.is_afac and not task.is_air_to_ground and not task.is_air_to_air
    assert FlightPlanBuilderTypes.for_flight(s.flight) is AfacFlightPlan.builder_type()
    assert len(s.plan.ui_zone().points) == (1 if task is FlightType.AFAC_AREA else 2)
    assert s.plan.patrol_duration == timedelta(minutes=60)
    s.settings.plugins["realisticcas.afacStationMinutes"] = 12
    assert s.plan.patrol_duration == timedelta(minutes=12)


@pytest.mark.parametrize("value", [True, 0, -1, 241, 1.5, "60"])
def test_station_duration_rejects_invalid_saved_values(value: Any) -> None:
    s = scenario()
    s.settings.plugins["realisticcas.afacStationMinutes"] = value
    with pytest.raises(ValueError):
        station_minutes(s.settings)


def test_disabled_flight_creation_does_not_claim_inventory() -> None:
    s = scenario()
    s.settings.plugins["realisticcas.afacEnabled"] = False
    squadron: Any = MagicMock(settings=s.settings, aircraft=s.flight.unit_type)
    with pytest.raises(ValueError, match="AFAC"):
        Flight(MagicMock(), squadron, 1, FlightType.AFAC_AREA, MagicMock(), None)
    squadron.claim_inventory.assert_not_called()


@pytest.mark.parametrize(
    "variant,night,pod,warning",
    [
        ("Yak-52", True, False, True),
        ("Yak-52", False, False, False),
        ("UH-1H Iroquois", True, False, False),
        ("C-101CC Aviojet", True, True, False),
    ],
)
def test_flight_picker_warns_about_final_night_equipment(
    variant: str, night: bool, pod: bool, warning: bool
) -> None:
    from game.timeofday import TimeOfDay
    from qt_ui.windows.mission.flight.QFlightCreator import QFlightCreator

    selector = lambda value: NS(currentData=lambda: value)
    label = MagicMock()
    dialog: Any = NS(
        task_selector=selector(FlightType.AFAC_AREA),
        aircraft_selector=selector(AircraftType.named(variant)),
        squadron_selector=selector(
            NS(
                primary_task=FlightType.AFAC_AREA,
                location=NS(name="Base"),
                untasked_aircraft=1,
            )
        ),
        loadout_selector=selector(
            NS(pylons={1: NS(clsid="{AN_ASQ_228}")} if pod else {})
        ),
        selection_summary=label,
        game=NS(conditions=NS(time_of_day=TimeOfDay.Night if night else TimeOfDay.Day)),
    )
    QFlightCreator.update_selection_summary(dialog)
    assert ("Warning" in label.setText.call_args.args[0]) == warning


@pytest.mark.parametrize("task", [FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE])
@pytest.mark.parametrize(
    "variant", ["MQ-9 Reaper", "OH-58D(R) Kiowa Warrior", "UH-1H Iroquois"]
)
def test_afac_behavior_labels_the_role_without_native_engagement_or_fac_tasks(
    task: FlightType, variant: str
) -> None:
    s = scenario(task, variant)
    AircraftBehavior(task, MagicMock()).apply_to(s.flight, s.group)
    assert s.group.dict()["task"] == AFAC.name
    tasks = [t.dict() for t in s.group.points[0].tasks]
    assert not any(t["id"].startswith(("Engage", "Attack", "FAC")) for t in tasks)
    options = {
        t["params"]["action"]["params"]["name"]: t["params"]["action"]["params"][
            "value"
        ]
        for t in tasks
        if t["id"] == "WrappedAction" and t["params"]["action"]["id"] == "Option"
    }
    assert options[0] == 4  # Weapon hold.
    assert options[6] is True  # Bingo.
    assert 10 not in options  # No ammo-based RTB.
    assert not any("SetUnlimitedFuel" in str(t) for t in tasks)


@pytest.mark.parametrize(
    "task", [FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE, FlightType.BARCAP]
)
@pytest.mark.parametrize("unlimited", [False, True])
def test_racetrack_end_restores_unlimited_fuel_only_when_configured(
    task: FlightType, unlimited: bool
) -> None:
    s = scenario(task)
    s.settings.ai_unlimited_fuel = unlimited
    point = s.group.points[0]
    original = RunScript("-- Existing arrival task")
    point.add_task(original)
    builder = RaceTrackEndBuilder(
        s.plan.layout.patrol_end,
        s.group,
        s.flight,
        s.mission,
        datetime(2026, 1, 1),
        MagicMock(),
    )
    builder.add_tasks(point)
    if unlimited:
        assert point.tasks[0].dict() == SetUnlimitedFuelCommand(True).dict()
        assert point.tasks[1:] == [original]
    else:
        assert point.tasks == [original]


def test_native_orbit_uses_relative_duration_and_fuel_stop() -> None:
    s = scenario()
    point = s.group.add_waypoint(Point(0, 0, s.mission.terrain), 3000, speed=250)
    builder = AfacSearchBuilder(
        s.plan.layout.patrol_start,
        s.group,
        s.flight,
        s.mission,
        datetime(2026, 1, 1),
        MagicMock(),
    )
    builder.add_tasks(point)
    orbit = point.tasks[-1].dict()
    assert getattr(s.group, "_afac_restore_unlimited_fuel") is True
    assert orbit["id"] == "ControlledTask"
    assert orbit["params"]["task"]["id"] == "Orbit"
    assert orbit["params"]["stopCondition"]["duration"] == 3600
    assert "time" not in orbit["params"]["stopCondition"]
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    lua.execute("timer={getTime=function()return 123 end}")
    script = point.tasks[1].params["action"]["params"]["command"]
    lua.execute(script)
    lua.execute("timer.getTime=function()return 999 end")
    lua.execute(script)
    assert lua.eval("RealisticCAS.afacStations.AFAC") == 123
    lua.execute(
        "fuel=0.5; Group={getByName=function()return {isExist=function()return true end,getUnits=function()return {{isExist=function()return true end,getFuel=function()return fuel end}}end}end}"
    )
    condition = orbit["params"]["stopCondition"]["condition"]
    assert not lua.eval(condition)
    lua.execute("fuel=0.1")
    assert lua.eval(condition)
    lua.execute("fuel=0.5; RealisticCAS.afacReturn={AFAC='station complete'}")
    assert lua.eval(condition)


def test_final_registry_exports_zone_skill_and_thermal_equipment() -> None:
    s = scenario()
    unit = s.group.units[0]
    pilot = object()
    squadron = NS(pilot_skill=lambda _: CADET_SKILL)
    data: Any = NS(
        tic_groups=[],
        jtacs=[],
        flights=[
            NS(
                flight_type=FlightType.AFAC_AREA,
                units=[unit],
                squadron=squadron,
                work_zone=s.plan.ui_zone(),
                group_name="AFAC",
            )
        ],
    )
    mapping: Any = NS(
        theater_objects={}, flight=lambda _: NS(pilot=pilot, flight=s.flight)
    )
    registry = collect_registry(s.mission, data, enabled=True, unit_map=mapping)
    assert registry is not None
    observer = registry["observers"][0]
    assert observer["afac"]["skill"] == 0
    assert observer["afac"]["stationSeconds"] == 3600
    assert observer["afac"]["zone"]["radius"] == s.plan.ui_zone().radius.meters
    assert observer["equipment"]["ir"] is True
    assert observer["equipment"]["remoteOperator"] is True

    unit.pylons = {
        1: {"CLSID": "{M260_M156}"},
        2: {"CLSID": "{M260_M156}"},
        3: {"CLSID": "unknown"},
    }
    registry = collect_registry(s.mission, data, enabled=True, unit_map=mapping)
    assert registry is not None
    assert registry["observers"][0]["afac"]["smokeRounds"] == 14


@pytest.mark.parametrize("night", [False, True])
def test_game_master_probe_serializes_real_orbits_and_plugin_startup(
    tmp_path: Path, night: bool
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(night=night)
    assert mission.groundControl.blue_game_masters == 1
    country = mission.country("USA")
    groups = country.plane_group + country.helicopter_group
    assert len(groups) == 4
    assert all(not u.is_human() for g in groups for u in g.units)
    for group in groups:
        assert group.task == AFAC.name
        serialized = str([p.dict() for p in group.points])
        assert "AttackGroup" not in serialized and "EngageTargets" not in serialized
        assert "duration" in serialized and "120" in serialized
    path = tmp_path / "afac.miz"
    mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name == "mission" or name.endswith(".lua"):
                lua.compile(archive.read(name).decode("utf-8"))
        lua.execute(archive.read("mission").decode("utf-8"))
        for _, action in lua.globals().mission["trig"]["actions"].items():
            lua.compile(action)


@pytest.mark.parametrize("cloudy", [False, True])
def test_safety_probes_export_routes_known_threats_and_cloud_limits(
    tmp_path: Path, cloudy: bool
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(safety=True, cloudy=cloudy)
    config = getattr(mission, "_afac_probe_config")
    observers = [o for o in config["registry"]["observers"] if "afac" in o]
    assert len(observers) == 4
    assert all(o["afac"]["navigation"]["exitWaypoint"] == 4 for o in observers)
    for observer in observers:
        nav = observer["afac"]["navigation"]
        assert nav["searchWaypoint"] == 2
        assert nav["route"][3]["type"] == "Land"
        assert nav["route"][3]["airdromeId"] == mission.terrain.airports["Kobuleti"].id
        assert isinstance(nav["route"][1]["task"]["params"]["tasks"], list)
    assert all(
        o["afac"]["navigation"]["restoreUnlimitedFuel"] is False for o in observers
    )
    threats = config["registry"]["airDefenseThreats"]
    assert len(threats) == 4 and sum(t["known"] for t in threats) == 3
    if cloudy:
        assert config["afacAvoidance"]["clouds"]["base"] == 2000
    path = tmp_path / "safety.miz"
    mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name == "mission" or name.endswith(".lua"):
                lua.compile(archive.read(name).decode("utf-8"))


def test_native_route_tables_keep_numeric_task_indices_and_reject_sparse_keys() -> None:
    assert _native_route_value({"tasks": {1: {"number": 1}, 2: {"number": 2}}}) == {
        "tasks": [{"number": 1}, {"number": 2}]
    }
    with pytest.raises(ValueError, match="non-contiguous"):
        _native_route_value({"tasks": {2: {"number": 2}}})


@pytest.mark.parametrize("cloudy", [False, True])
def test_live_fire_probe_enables_every_defence_without_changing_afac_behaviour(
    tmp_path: Path, cloudy: bool
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(safety=True, cloudy=cloudy, live_fire=True)
    config = getattr(mission, "_afac_probe_config")
    threats = config["registry"]["airDefenseThreats"]
    assert len(threats) == 4 and sum(t["known"] for t in threats) == 3
    baseline = build_mission(safety=True, cloudy=cloudy)
    assert (
        config["registry"]["observers"]
        == getattr(baseline, "_afac_probe_config")["registry"]["observers"]
    )
    friendly = mission.country("USA")
    for aircraft in [*friendly.plane_group, *friendly.helicopter_group]:
        for defence in mission.country("Russia").vehicle_group:
            if defence.name.startswith("AFAC_AA_"):
                threat = next(t for t in threats if t["groupName"] == defence.name)
                assert (
                    aircraft.points[0].position.distance_to_point(
                        defence.points[0].position
                    )
                    > threat["radius"] + 1000
                )
    for group in mission.country("Russia").vehicle_group:
        if group.name.startswith("AFAC_AA_"):
            actions = [t.dict()["params"]["action"] for t in group.points[0].tasks]
            options = {
                a["params"]["name"]: a["params"]["value"]
                for a in actions
                if a["id"] == "Option"
            }
            assert options[0] == OptROE.Values.WeaponFree and options[9] == 2
    path = tmp_path / "live-fire.miz"
    mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode("utf-8"))
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))
    lua.execute("""
getValueDictByKey=function(k)return dictionary[k] or k end
getValueResourceByKey=function(k)return k end
a_do_script_file=function()end
sources={};a_do_script=function(s)assert(loadstring(s));sources[#sources+1]=s end
""")
    for _, action in lua.globals().mission["trig"]["actions"].items():
        lua.execute(action)
    sources = list(lua.globals().sources.values())
    assert any("LIVE FIRE: defences are weapons free" in source for source in sources)
    assert len([s for s in sources if "AFAC_LIVE_FIRE" in s]) == 1


@pytest.mark.parametrize("safety,quick", [(False, False), (True, True)])
def test_live_fire_rejects_cases_without_safe_initial_separation(
    safety: bool, quick: bool
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    with pytest.raises(ValueError, match="Live fire requires full safety cases"):
        build_mission(safety=safety, quick=quick, live_fire=True)


def test_fire_discovery_probe_delays_acquisition_and_keeps_the_airfield_clear() -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(safety=True, live_fire=True, fire_discovery=True)
    config = getattr(mission, "_afac_probe_config")
    assert config["acquisitionSeconds"] == 60
    airport = mission.terrain.airports["Kobuleti"]
    for group in mission.country("Russia").vehicle_group:
        if group.name.startswith("AFAC_AA_"):
            threat = next(
                t
                for t in config["registry"]["airDefenseThreats"]
                if t["groupName"] == group.name
            )
            assert (
                group.points[0].position.distance_to_point(airport.position)
                > threat["radius"] + 20000
            )
    with pytest.raises(ValueError, match="requires live fire"):
        build_mission(fire_discovery=True)


def test_quick_probe_exports_complete_routes_accepted_by_native_adapter(
    tmp_path: Path,
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(safety=True, quick=True)
    config = getattr(mission, "_afac_probe_config")
    observers = [o for o in config["registry"]["observers"] if "afac" in o]
    assert len(observers) == 4
    assert all(o["afac"]["stationSeconds"] == 180 for o in observers)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    for name in (
        "core.lua",
        "afac-search.lua",
        "sensors.lua",
        "afac-safety.lua",
        "afac-navigation.lua",
    ):
        lua.execute((Path("resources/plugins/realisticcas") / name).read_text("utf-8"))
    lua.execute(
        "config="
        + lua_literal(
            {
                "observers": config["registry"]["observers"],
                "airDefenseThreats": config["registry"]["airDefenseThreats"],
            }
        )
    )
    lua.execute("nav=RealisticCAS.newAFACNavigation({},config);assert(nav.active)")
    path = tmp_path / "quick.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name == "mission" or name.endswith(".lua"):
                lua.compile(archive.read(name).decode("utf-8"))


def test_recovery_control_is_native_only_and_serializes_landing_routes(
    tmp_path: Path,
) -> None:
    from tools.realistic_cas_tests.build_afac_recovery_probe import build_mission

    mission = build_mission()
    assert mission.groundControl.blue_game_masters == 1
    groups = mission.country("USA").plane_group
    assert len(groups) == 2
    direct, cruise = groups
    assert len(direct.points) == 2 and len(cruise.points) == 3
    assert direct.points[-1].airdrome_id == cruise.points[-1].airdrome_id
    assert cruise.points[1].alt == 6000
    assert all(g.task == Nothing.name for g in groups)
    assert all(not unit.is_human() for group in groups for unit in group.units)
    path = tmp_path / "recovery-control.miz"
    mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(path) as archive:
        native = archive.read("mission").decode("utf-8")
        assert "RealisticCAS" not in native
        lua.execute(native)
        for _, action in lua.globals().mission["trig"]["actions"].items():
            lua.compile(action)


@pytest.mark.parametrize("lost", [False, True])
def test_safety_probe_reports_recovery_only_after_all_four_outcomes(
    tmp_path: Path, lost: bool
) -> None:
    from tools.realistic_cas_tests.build_afac_probe import build_mission

    mission = build_mission(safety=True, cloudy=True)
    observers = getattr(mission, "_afac_probe_config")["registry"]["observers"]
    names = [o["name"] for o in observers if "afac" in o]
    assert len(names) == 4
    path = tmp_path / "recovery-summary.miz"
    mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode("utf-8"))
    lua.execute("""
messages={};logs={}
trigger={action={outText=function(text)messages[#messages+1]=text end}}
env={info=function(text)logs[#logs+1]=text end}
timer={getTime=function()return 0 end,scheduleFunction=function()end}
world={event={S_EVENT_LAND=1,S_EVENT_CRASH=2,S_EVENT_DEAD=3,S_EVENT_UNIT_LOST=4},
  addEventHandler=function(value)handler=value end}
getValueDictByKey=function(key)return key end
a_do_script=function(source)assert(loadstring(source))()end
function event(name,id)
  handler:onEvent({id=id,initiator={getName=function()return name end}})
end
function completed()
  local count=0
  for _,row in ipairs(logs)do if row:find('RECOVERY_COMPLETE') then count=count+1 end end
  return count
end
""")
    actions = list(lua.globals().mission["trig"]["actions"].values())
    diagnostics = [action for action in actions if "AFAC_SAFETY_PROBE" in action]
    assert len(diagnostics) == 1
    lua.execute(diagnostics[0])
    lua.execute("names=" + lua_literal(names))
    lua.execute("lost=" + lua_literal(lost))
    lua.execute("""
handler:onEvent({id=1,initiator={}})
event('unrelated unit',1);assert(completed()==0)
event(names[1],1);event(names[1],1);assert(completed()==0)
event(names[2],lost and 2 or 1);event(names[2],lost and 4 or 1)
event(names[3],1);assert(completed()==0)
event(names[4],1);assert(completed()==1)
assert(messages[#messages]:find(lost and '3/4 landed, 1 lost' or '4/4 landed, 0 lost'))
event(names[4],1);assert(completed()==1)
""")


def test_recovery_matrix_isolates_switching_and_active_orbit_replacement(
    tmp_path: Path,
) -> None:
    from tools.realistic_cas_tests.build_afac_recovery_probe import build_mission

    mission = build_mission(replacement_matrix=True)
    groups = mission.country("USA").plane_group
    assert [group.name for group in groups] == [
        "NATIVE_DIRECT",
        "NATIVE_SWITCH",
        "REPLACED_DIRECT",
        "REPLACED_SWITCH",
    ]
    assert [len(group.points) for group in groups] == [2, 4, 2, 4]
    for group in groups:
        assert group.points[0].speed == pytest.approx(200 / 3.6)
        assert group.points[-1].type == "Land"
        assert group.points[-1].speed == 0
        ids = [task.id for task in group.points[0].tasks]
        assert ("Orbit" in ids) == group.name.startswith("REPLACED")
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    path = tmp_path / "recovery-matrix.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        lua.execute(archive.read("mission").decode("utf-8"))
        lua.execute(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))
        for _, action in lua.globals().mission["trig"]["actions"].items():
            lua.compile(action)
    # Execute the generated script with a bounded native API double. This checks
    # that only the two active-orbit controls receive a replacement mission.
    lua.execute("""
scheduled={}; assigned={}
trigger={action={outText=function()end}}
env={info=function()end};world={event={},addEventHandler=function()end}
timer={getTime=function()return 0 end,scheduleFunction=function(fn,_,at)
  scheduled[at]=fn
end}
Group={getByName=function(name)return {
  getUnits=function()return {{getName=function()return name..'-1' end,
    getPoint=function()return {x=1,y=3506,z=2}end}}end,
  getController=function()return {setTask=function(_,task)assigned[name]=task end}end
}end}
a_do_script=function(source)assert(loadstring(source))()end
getValueDictByKey=function(key)return dictionary[key] or key end
""")
    for _, action in lua.globals().mission["trig"]["actions"].items():
        lua.execute(action)
    lua.execute("""
scheduled[30]()
assert(assigned.NATIVE_DIRECT==nil and assigned.NATIVE_SWITCH==nil)
local direct=assigned.REPLACED_DIRECT.params.route.points
local switched=assigned.REPLACED_SWITCH.params.route.points
assert(#direct==2 and #switched==4)
assert(direct[1].alt==3506 and direct[1].speed==200/3.6)
assert(#direct[1].task.params.tasks==0)
assert(switched[1].task.params.tasks[1].params.action.params.goToWaypointIndex==4)
assert(direct[2].type=='Land' and direct[2].speed==0)
assert(switched[4].type=='Land' and switched[4].airdromeId==direct[2].airdromeId)
""")
