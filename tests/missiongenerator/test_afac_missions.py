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
from dcs.planes import MQ_9_Reaper
from dcs.task import Nothing, RunScript, SetUnlimitedFuelCommand

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
from game.missiongenerator.realisticcasluadata import collect_registry
from game.settings import Settings
from game.squadrons.squadron import Squadron
from game.utils import feet


@pytest.fixture(autouse=True)
def saved_games(tmp_path: Path) -> None:
    persistency.setup(str(tmp_path), False, 0)


def scenario(task: FlightType = FlightType.AFAC_AREA) -> Any:
    settings = Settings()
    settings.plugins.update({"realisticcas": True, "realisticcas.afacEnabled": True})
    settings.live_pilots_enabled = False
    settings.ai_unlimited_fuel = True
    mission = Mission()
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "AFAC",
        MQ_9_Reaper,
        Point(0, 0, mission.terrain),
        3000,
        speed=250,
    )
    group.points[0].tasks.clear()
    aircraft = AircraftType.named("MQ-9 Reaper")
    layout: Any = NS(
        patrol_start=NS(position=Point(-2000, 0, mission.terrain), alt=feet(10000)),
        patrol_end=NS(position=Point(2000, 0, mission.terrain)),
    )
    flight: Any = NS(
        flight_type=task,
        unit_type=aircraft,
        is_helo=False,
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


def test_afac_behavior_is_unarmed_no_infinite_fuel_and_no_winchester_rtb() -> None:
    s = scenario()
    AircraftBehavior(FlightType.AFAC_AREA, MagicMock()).apply_to(s.flight, s.group)
    assert s.group.task == Nothing.name
    tasks = [t.dict() for t in s.group.points[0].tasks]
    assert not any(t["id"].startswith(("Engage", "Attack")) for t in tasks)
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
        assert group.task == Nothing.name
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
