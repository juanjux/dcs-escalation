"""Search geometry and its native waypoint command do not require a known target."""

from datetime import datetime, timedelta
import math
from types import SimpleNamespace as NS
from typing import Any
from pathlib import Path
from zipfile import ZipFile

from dcs import Mission
from dcs.helicopters import AH_1W
from dcs.mapping import Point
from dcs.task import ControlledTask, EngageTargetsInZone, OptECMUsing, Targets
import pytest

from game.ato import FlightType
from game.missiongenerator.aircraft.searchpattern import add_search_pattern
from game.utils import nautical_miles


def scenario(
    task: FlightType = FlightType.CAS,
    *,
    heading: float = 37,
    length: float = 20000,
    radius: float = 5,
) -> tuple[Any, Any, list[Any], datetime]:
    mission = Mission()
    center = Point(0, 0, mission.terrain)
    group = mission.flight_group_inflight(
        mission.country("USA"), "Searching Cobra", AH_1W, center, 300, speed=180
    )
    group.points[0].tasks.clear()
    logical = NS(
        position=(
            center.point_from_heading(heading + 180, length / 2)
            if task == FlightType.CAS
            else center
        )
    )
    finish = NS(position=center.point_from_heading(heading, length / 2))
    anchor = group.add_waypoint(logical.position, 300, speed=180, name="OBJECTIVE")
    anchor.add_task(EngageTargetsInZone(center, 2000, [Targets.All.GroundUnits]))
    group.add_waypoint(Point(9000, 0, mission.terrain), 300, speed=180, name="RTB")
    now = datetime(2026, 6, 1, 12)
    plan = NS(
        layout=NS(patrol_start=logical, patrol_end=finish),
        tot_waypoint=logical,
        tot=now,
        patrol_end_time=now + timedelta(minutes=15),
        ui_zone=lambda: NS(points=[center], radius=nautical_miles(radius)),
    )
    flight = NS(
        client_count=0,
        is_helo=True,
        flight_type=task,
        flight_plan=plan,
        coalition=NS(
            game=NS(settings=NS(plugins={"realisticcas": True})),
            doctrine=NS(cas_duration=timedelta(minutes=20)),
        ),
    )
    return flight, group, [(logical, anchor)], now


@pytest.mark.parametrize("heading", [0, 37, 90, 180, 270])
@pytest.mark.parametrize("length", [500, 18720, 40000])
@pytest.mark.parametrize("radius", [0.1, 10])
def test_cas_search_spans_and_follows_the_full_frontline(
    heading: float, length: float, radius: float
) -> None:
    flight, group, generated, now = scenario(
        heading=heading, length=length, radius=radius
    )
    start = flight.flight_plan.layout.patrol_start.position
    finish = flight.flight_plan.layout.patrol_end.position
    ux, uy = (finish.x - start.x) / length, (finish.y - start.y) / length
    width = min(1500.0, max(250.0, nautical_miles(radius).meters * 0.35))
    anchor = generated[0][1]
    anchor.alt_type = "RADIO"
    engagement = anchor.tasks[0].dict()
    assert add_search_pattern(flight, group, now, generated)
    corners = group.points[2:6]
    for corner, along, across in zip(
        corners, (0, length, length, 0), (-width, -width, width, width)
    ):
        dx, dy = corner.position.x - start.x, corner.position.y - start.y
        assert dx * ux + dy * uy == pytest.approx(along, abs=1e-6)
        assert -dx * uy + dy * ux == pytest.approx(across, abs=1e-6)
        assert corner.alt == anchor.alt
        assert corner.alt_type == anchor.alt_type
        assert math.isfinite(corner.position.x) and math.isfinite(corner.position.y)
    # Navigation changes must not expand or replace the native attack zone.
    assert anchor.tasks[0].params["task"] == engagement


@pytest.mark.parametrize("task", [FlightType.CAS, FlightType.ARMED_RECON])
@pytest.mark.parametrize("radius", [0.1, 1, 10])
def test_area_search_and_collapsed_fronts_keep_the_original_square(
    task: FlightType, radius: float
) -> None:
    flight, group, generated, now = scenario(task, length=0, radius=radius)
    assert add_search_pattern(flight, group, now, generated)
    width = min(1500.0, max(250.0, nautical_miles(radius).meters * 0.35))
    assert [(p.position.x, p.position.y) for p in group.points[2:6]] == [
        (-width, -width),
        (-width, width),
        (width, width),
        (width, -width),
    ]


@pytest.mark.parametrize("task", [FlightType.CAS, FlightType.ARMED_RECON])
@pytest.mark.parametrize("is_helo", [False, True])
def test_search_moves_then_preserves_rtb_route(task: FlightType, is_helo: bool) -> None:
    flight, group, generated, now = scenario(task)
    flight.is_helo = is_helo
    original = list(group.points)
    assert add_search_pattern(flight, group, now, generated)
    assert len(group.points) == len(original) + 4
    assert group.points[-1] is original[-1]
    assert group.points[0] is original[0]
    legs = group.points[2:6]
    assert all(p.speed > 0 and p.speed_locked and not p.ETA_locked for p in legs)
    assert all(
        a.position.distance_to_point(b.position) > 0 for a, b in zip(legs, legs[1:])
    )
    assert "SwitchWaypoint" in legs[-1].tasks[-1].params["action"]["params"]["command"]


@pytest.mark.parametrize(
    "case", ["disabled", "client", "other task", "expired", "already passed"]
)
def test_unmanaged_routes_are_unchanged(case: str) -> None:
    flight, group, generated, now = scenario()
    if case == "disabled":
        flight.coalition.game.settings.plugins.clear()
    if case == "client":
        flight.client_count = 1
    if case == "other task":
        flight.flight_type = FlightType.BAI
    if case == "expired":
        flight.flight_plan.patrol_end_time = now
    if case == "already passed":
        generated = []
    before = [p.dict() for p in group.points]
    assert not add_search_pattern(flight, group, now, generated)
    assert before == [p.dict() for p in group.points]


@pytest.mark.parametrize(
    "time,fuel,expected", [(10, 0.5, 3), (900, 0.5, 7), (10, 0.1, 7)]
)
def test_loop_command_obeys_deadline_and_reserve(
    time: float, fuel: float, expected: int
) -> None:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    flight, group, generated, now = scenario()
    add_search_pattern(flight, group, now, generated)
    script = group.points[5].tasks[-1].params["action"]["params"]["command"]
    lua.execute(f"""
        commands={{}}; env={{info=function() end}}
        timer={{getTime=function() return {time} end}}
        unit={{isExist=function() return true end,getFuel=function() return {fuel} end}}
        controller={{setCommand=function(self,c) commands[#commands+1]=c end}}
        group={{isExist=function() return true end,getUnits=function() return {{unit}} end,
            getController=function() return controller end}}
        Group={{getByName=function(name) assert(name=='Searching Cobra'); return group end}}
    """)
    lua.execute(script)
    assert lua.eval("#commands") == 1
    assert lua.eval("commands[1].params.fromWaypointIndex") == 6
    assert lua.eval("commands[1].params.goToWaypointIndex") == expected


@pytest.mark.parametrize("time,expected", [(10, 0), (900, 1)])
def test_intermediate_corners_do_not_override_native_navigation(
    time: float, expected: int
) -> None:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    flight, group, generated, now = scenario()
    add_search_pattern(flight, group, now, generated)
    lua.execute(f"""
        commands={{}}; env={{info=function() end}}
        timer={{getTime=function() return {time} end}}
        controller={{setCommand=function(self,c) commands[#commands+1]=c end}}
        group={{isExist=function() return true end,getUnits=function() return {{}} end,
            getController=function() return controller end}}
        Group={{getByName=function() return group end}}
    """)
    lua.execute(group.points[2].tasks[-1].params["action"]["params"]["command"])
    assert lua.eval("#commands") == expected
    if expected:
        assert lua.eval("commands[1].params.goToWaypointIndex") == 7


@pytest.mark.parametrize("wrapped", [False, True])
def test_native_engagement_has_limits_even_when_no_corner_is_reached(
    wrapped: bool,
) -> None:
    flight, group, generated, now = scenario()
    anchor = group.points[1]
    original = anchor.tasks[0].dict()
    if wrapped:
        controlled = ControlledTask(anchor.tasks[0])
        controlled.stop_after_time(800)
        controlled.stop_after_duration(200)
        controlled.stop_if_lua_predicate("originalStop")
        anchor.tasks[0] = controlled
    option = OptECMUsing(value=OptECMUsing.Values.UseIfDetectedLockByRadar)
    anchor.add_task(option)
    assert add_search_pattern(flight, group, now, generated)
    task = anchor.tasks[0]
    assert task.id == "ControlledTask"
    assert task.params["task"] == original
    stop = task.params["stopCondition"]
    assert stop["time"] == (800 if wrapped else 900)
    if wrapped:
        assert stop["duration"] == 200
    assert anchor.tasks[1] is option
    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    lua.execute("""
        originalStop=false; fuel=0.5
        unit={isExist=function() return true end,getFuel=function() return fuel end}
        Group={getByName=function() return {
            isExist=function() return true end,getUnits=function() return {unit} end} end}
    """)
    condition = stop["condition"]
    assert not lua.eval(condition)
    lua.execute("fuel=0.1")
    assert lua.eval(condition)
    if wrapped:
        lua.execute("fuel=0.5; originalStop=true")
        assert lua.eval(condition)


@pytest.mark.parametrize("frontline_length", [0, 18720])
def test_generated_probe_serializes_and_compiles_search_tasks(
    tmp_path: Path, frontline_length: float
) -> None:
    from dcs.lua import loads
    from tools.realistic_cas_tests.build_search_probe import build_mission

    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    mission = build_mission(frontline_length_m=frontline_length)
    path = tmp_path / "search.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        data = loads(archive.read("mission").decode())["mission"]
    assert data["groundControl"]["roles"]["instructor"]["blue"] == 1
    countries = data["coalition"]["blue"]["country"].values()
    assert all(not c.get("plane", {}).get("group") for c in countries)
    helicopters = [
        g for c in countries for g in c.get("helicopter", {}).get("group", {}).values()
    ]
    assert len(helicopters) == 4
    for group in helicopters:
        points = list(group["route"]["points"].values())
        assert not points[0]["task"]["params"]["tasks"]
        engagement = points[1]["task"]["params"]["tasks"][1]
        assert engagement["id"] == "ControlledTask"
        assert engagement["params"]["task"]["id"] == "EngageTargetsInZone"
        assert engagement["params"]["stopCondition"]["time"] == 720
        legs = [
            p
            for p in points
            if p.get("name", "").startswith("SEARCH ")
            and p.get("name") != "SEARCH AREA"
        ]
        control = "CONTROL" in group["name"]
        assert len(legs) == (64 if control else 4)
        if frontline_length and group["name"].endswith("_CAS"):
            start = next(p for p in points if p.get("name") == "FLOT START")
            end = next(p for p in points if p.get("name") == "FLOT END")
            assert math.hypot(end["x"] - start["x"], end["y"] - start["y"]) == (
                pytest.approx(frontline_length)
            )
            assert math.hypot(
                legs[1]["x"] - legs[0]["x"], legs[1]["y"] - legs[0]["y"]
            ) == pytest.approx(frontline_length)
            for a, b, boundary in ((legs[0], legs[3], start), (legs[1], legs[2], end)):
                assert (a["x"] + b["x"]) / 2 == pytest.approx(boundary["x"])
                assert (a["y"] + b["y"]) / 2 == pytest.approx(boundary["y"])
        for point in legs:
            tasks = list(point["task"]["params"]["tasks"].values())
            if control:
                assert not tasks
            else:
                script = tasks[-1]["params"]["action"]["params"]["command"]
                lua.compile(script)
            assert point["speed"] > 0
        assert points[-1]["type"] == "Land"
    for trigger in data["trigrules"].values():
        for action in trigger["actions"].values():
            assert action["text"].strip()
            lua.compile(action["text"])


def test_probe_events_tolerate_unnamed_weapons_and_expired_objects(
    tmp_path: Path,
) -> None:
    from dcs.lua import loads
    from tools.realistic_cas_tests.build_search_probe import build_mission

    lua = pytest.importorskip("lupa.lua51").LuaRuntime()
    lua.execute("""
        messages={}
        env={info=function(message) messages[#messages+1]=message end}
        Group={getByName=function() return {
            getController=function() return {setCommand=function() end} end} end}
        timer={getTime=function() return 10 end,scheduleFunction=function() end}
        world={event={S_EVENT_SHOT=1,S_EVENT_HIT=2,S_EVENT_DEAD=8},
            addEventHandler=function(value) eventHandler=value end}
    """)
    mission = build_mission()
    path = tmp_path / "events.miz"
    mission.save(path)
    with ZipFile(path) as archive:
        data = loads(archive.read("mission").decode())["mission"]
    for trigger in data["trigrules"].values():
        for action in trigger["actions"].values():
            script = action["text"]
            assert script.strip()
            lua.execute(script)
    lua.execute("""
        eventHandler:onEvent({id=8})
        eventHandler:onEvent({id=8,initiator={},target={}})
        local expired={getName=function() error('object no longer exists') end}
        eventHandler:onEvent({id=2,initiator=expired,target=expired})
        local invalid=newproxy(true)
        getmetatable(invalid).__index=function() error('invalid native object') end
        eventHandler:onEvent({id=8,initiator=invalid,target=invalid})
        eventHandler:onEvent({id=8,initiator={getName=function() return nil end}})
        local unit={getName=function() return 'Cobra' end}
        eventHandler:onEvent({id=1,time=12.5,initiator=unit,target=unit})
    """)
    assert lua.eval("#messages") == 6
    for index in range(1, 6):
        assert "initiator=? target=?" in lua.eval(f"messages[{index}]")
    assert "t=12.5 initiator=Cobra target=Cobra" in lua.eval("messages[6]")
