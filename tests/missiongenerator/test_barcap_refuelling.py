"""Fuel management retains native CAP tasking and fails safely to recovery."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from dcs import Mission, Point
from dcs.lua import loads
from dcs.planes import F_16C_50, KC_135
from dcs.task import CAP, ControlledTask, OrbitAction, Tanker

from game.ato.flighttype import FlightType
from game.missiongenerator.barcaprefuelling import configure


def runtime(*, end: int = 4000, tanker_start: int = 0) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now=0; scheduled={}; logs={}; warnings={}; flag=0
        env={info=function(s) logs[#logs+1]=s end,
             warning=function(s) warnings[#warnings+1]=s end}
        trigger={misc={getUserFlag=function() return flag end}}
        groups={}
        function add(name,x,fuel)
            local g={alive=true, fuel=fuel, life=100, ammo=4, x=x, airborne=true}
            local c={bingo=true,pushes=0,rtbs=0}
            function c:setOption(id,value) assert(id==6); self.bingo=value end
            function c:pushTask(task) self.pushes=self.pushes+1; self.task=task end
            function c:setTask(task) self.rtbs=self.rtbs+1; self.home=task end
            function c:setCommand(task) self.command=task end
            g.controller=c
            local u={}
            function u:isExist() return g.alive end
            function u:getFuel() return g.fuel end
            function u:getLife() return g.life end
            function u:getLife0() return 100 end
            function u:getPoint() return {x=g.x,y=6000,z=0} end
            function u:inAir() return g.airborne end
            function u:getAmmo() return {{count=g.ammo,desc={missileCategory=1}}} end
            function g:isExist() return self.alive end
            function g:getController() return c end
            function g:getUnits() return {u} end
            groups[name]=g
        end
        add("CAP",0,.7); add("TANKER",10000,.8)
        Group={getByName=function(name) return groups[name] end}
        timer={
            getTime=function() return now end,
            scheduleFunction=function(fn,arg,t)
                scheduled[#scheduled+1]={fn=fn,arg=arg,time=t}
            end
        }
        function tick(time)
            now=time
            return scheduled[1].fn(nil,time)
        end
    """)
    lua.globals().ESCALATION_BARCAP_REFUELLING = lua.table_from(
        [
            {
                "group": "CAP",
                "flag": "station",
                "endTime": end,
                "bingo": 0.3,
                "reserve": 0.1,
                "burnPerMeter": 0.000001,
                "home": [{"name": "LANDING", "type": "Land", "airdromeId": 1}],
                "tankers": [
                    {"group": "TANKER", "startTime": tanker_start, "endTime": 6000}
                ],
            }
        ],
        recursive=True,
    )
    lua.execute(Path("resources/plugins/base/barcap_refuelling.lua").read_text())
    return lua


def test_en_route_bingo_is_not_disabled_until_station_activation() -> None:
    lua = runtime()
    lua.execute("groups.CAP.fuel=.25; tick(5)")
    assert lua.eval("groups.CAP.controller.bingo") is True
    assert lua.eval("groups.CAP.controller.pushes") == 0
    lua.execute("flag=1; tick(10)")
    assert lua.eval("groups.CAP.controller.bingo") is False
    assert lua.eval("groups.CAP.controller.task.params.task.id") == "Refueling"


@pytest.mark.parametrize("remaining,expected", [(1200, 0), (1199, 0), (1201, 1)])
def test_strictly_more_than_twenty_minutes_are_needed(
    remaining: int,
    expected: int,
) -> None:
    lua = runtime(end=remaining + 5)
    lua.execute("flag=1; groups.CAP.fuel=.25; tick(5)")
    assert lua.eval("groups.CAP.controller.pushes") == expected
    assert lua.eval("groups.CAP.controller.rtbs") == 1 - expected


def test_refuel_completion_resumes_suspended_orbit_without_resetting_end_time() -> None:
    lua = runtime()
    lua.execute("flag=1; groups.CAP.fuel=.25; tick(5)")
    assert lua.eval('EscalationBARCAP.done("CAP")') is False
    lua.execute("groups.CAP.fuel=.95; tick(200)")
    assert lua.eval('EscalationBARCAP.done("CAP")') is True
    assert lua.eval("EscalationBARCAP.states.CAP.cfg.endTime") == 4000
    assert lua.eval("groups.CAP.controller.rtbs") == 0
    assert lua.eval("groups.CAP.controller.pushes") == 1
    # A later BINGO can send it back to the tanker before the original end.
    lua.execute("groups.CAP.fuel=.25; tick(500)")
    assert lua.eval("groups.CAP.controller.pushes") == 2


@pytest.mark.parametrize(
    "change",
    [
        "groups.TANKER.alive=false",
        "groups.TANKER.airborne=false",
        "groups.TANKER.fuel=.05",
        "groups.TANKER.x=1000000",
        "EscalationBARCAP.states.CAP.cfg.tankers={}",
    ],
)
def test_no_usable_tanker_returns_home(change: str) -> None:
    lua = runtime()
    lua.execute("flag=1; groups.CAP.fuel=.25; " + change + "; tick(5)")
    assert lua.eval("groups.CAP.controller.rtbs") == 1
    assert lua.eval("groups.CAP.controller.bingo") is True
    assert lua.eval("groups.CAP.controller.home.params.route.points[2].airdromeId") == 1


@pytest.mark.parametrize(
    "change,time",
    [
        ("groups.TANKER.alive=false", 10),
        ("groups.CAP.fuel=.09", 10),
        ("", 970),
        ("", 4000),
    ],
)
def test_tanker_loss_low_reserve_timeout_or_station_end_aborts_refuel(
    change: str,
    time: int,
) -> None:
    lua = runtime()
    lua.execute(
        "; ".join(
            filter(
                None,
                ["flag=1", "groups.CAP.fuel=.25", "tick(5)", change, f"tick({time})"],
            )
        )
    )
    assert lua.eval("groups.CAP.controller.rtbs") == 1
    assert lua.eval('EscalationBARCAP.done("CAP")') is True


def test_tanker_not_yet_on_station_is_not_available() -> None:
    lua = runtime(tanker_start=100)
    lua.execute("flag=1; groups.CAP.fuel=.25; tick(5)")
    assert lua.eval("groups.CAP.controller.rtbs") == 1


@pytest.mark.parametrize("change", ["groups.CAP.ammo=0", "groups.CAP.life=80"])
def test_native_winchester_and_damage_recovery_are_not_overridden(change: str) -> None:
    lua = runtime()
    lua.execute("flag=1; " + change + "; groups.CAP.fuel=.25; tick(5)")
    assert lua.eval("groups.CAP.controller.bingo") is True
    assert lua.eval("groups.CAP.controller.pushes") == 0
    assert lua.eval("groups.CAP.controller.rtbs") == 0


def test_external_fuel_and_departing_station_do_not_trigger_refuel() -> None:
    lua = runtime()
    lua.execute("flag=1; groups.CAP.fuel=1.2; tick(5)")
    assert lua.eval("groups.CAP.controller.pushes") == 0
    lua.execute("flag=0; tick(10)")
    assert lua.eval("groups.CAP.controller.bingo") is True
    assert lua.eval("EscalationBARCAP.states.CAP.finished") is True


def test_monitor_failure_restores_native_bingo_and_recovery_route() -> None:
    lua = runtime()
    lua.execute("""
        flag=1
        groups.CAP.getUnits=function() error("telemetry failed") end
        tick(5)
    """)
    assert lua.eval("groups.CAP.controller.bingo") is True
    assert lua.eval("groups.CAP.controller.rtbs") == 1
    assert lua.eval("#warnings") == 1


def scenario() -> Any:
    mission = Mission()
    side = mission.country("USA")
    group = mission.flight_group_inflight(
        side,
        "CAP",
        F_16C_50,
        Point(0, 0, mission.terrain),
        6000,
        500,
        CAP,
    )
    start = group.add_waypoint(
        Point(10000, 0, mission.terrain), 6000, 500, "RACETRACK START"
    )
    orbit = ControlledTask(OrbitAction(altitude=6000, speed=500))
    orbit.stop_after_time(4000)
    start.tasks.append(orbit)
    group.add_waypoint(Point(20000, 0, mission.terrain), 6000, 500, "RACETRACK END")
    group.add_waypoint(Point(15000, 0, mission.terrain), 6000, 500, "REFUEL")
    group.add_waypoint(Point(5000, 0, mission.terrain), 6000, 500, "HOME NAV")
    group.add_waypoint(Point(0, 0, mission.terrain), 0, 500, "LANDING")
    cap = NS(
        flight_type=FlightType.BARCAP,
        client_units=[],
        group_name="CAP",
        friendly=True,
        aircraft_type=NS(
            dcs_id=F_16C_50.id,
            max_fuel=F_16C_50.fuel_max,
            fuel_consumption=NS(cruise=12, min_safe=800),
            gunfighter=False,
        ),
        bingo_fuel=2000,
    )
    # Use the installed variant name rather than assuming a display label.
    tanker = NS(
        flight_type=FlightType.REFUELING,
        group_name="TANKER",
        friendly=True,
        aircraft_type=NS(dcs_id=KC_135.id),
    )
    now = datetime(2026, 1, 1)
    info = NS(group_name="TANKER", start_time=now, end_time=now + timedelta(hours=2))
    data = NS(flights=[cap, tanker], tankers=[info])
    game = NS(conditions=NS(start_time=now), settings=NS(ai_unlimited_fuel=False))
    return NS(
        mission=mission, cap=cap, tanker=tanker, data=data, game=game, group=group
    )


def test_generation_keeps_orbit_and_uses_native_recovery_waypoints(
    tmp_path: Path,
) -> None:
    s = scenario()
    config = configure(s.game, s.mission, s.data)
    assert len(config) == 1
    assert config[0]["endTime"] == 4000
    assert [point["name"] for point in config[0]["home"]] == ["HOME NAV", "LANDING"]
    assert config[0]["tankers"][0]["group"] == "TANKER"
    assert _orbit_present(s.group.points[1])
    output = tmp_path / "barcap.miz"
    s.mission.save(output)
    with ZipFile(output) as archive:
        assert loads(archive.read("mission").decode())["mission"]


def _orbit_present(point: Any) -> bool:
    return any(
        t.dict().get("params", {}).get("task", {}).get("id") == "Orbit"
        for t in point.tasks
    )


@pytest.mark.parametrize("change", ["player", "tarcap", "incompatible", "no_tanker"])
def test_generation_never_disables_unmanaged_native_rtb(change: str) -> None:
    s = scenario()
    if change == "player":
        s.cap.client_units = [Mock()]
    elif change == "tarcap":
        s.cap.flight_type = FlightType.TARCAP
    elif change == "incompatible":
        s.tanker.aircraft_type = NS(dcs_id=F_16C_50.id)
    else:
        s.data.tankers = []
    assert configure(s.game, s.mission, s.data) == []
    assert len(s.group.points[1].tasks) == 1
