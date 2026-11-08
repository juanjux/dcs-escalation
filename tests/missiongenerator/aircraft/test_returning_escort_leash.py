"""The package leash releases ROE once its native escort task has ended."""

from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pytest
from dcs import Mission
from dcs.action import DoScript

from game.ato import FlightType
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)
from game.missiongenerator.luagenerator import LuaGenerator
from game.missiongenerator.missiondata import EscortInfo, MissionData
from game.settings import Settings


@pytest.mark.parametrize("role", [FlightType.ESCORT, FlightType.SEAD_ESCORT])
def test_generated_leash_uses_the_package_split_flag(role: FlightType) -> None:
    package = NS(primary_flight=NS(group_id=1))
    configurator = NS(
        flight=NS(
            flight_type=role,
            package=package,
            group_id=2,
            is_helo=False,
            coalition=NS(
                doctrine=NS(
                    escort_engagement_range=NS(meters=50000),
                    sead_escort_engagement_range=NS(meters=40000),
                )
            ),
        ),
        mission_data=NS(escorts=[]),
    )
    FlightGroupConfigurator.register_escort_leash(configurator)  # type: ignore[arg-type]
    assert configurator.mission_data.escorts[0].release_flag == f"split-{id(package)}"


def test_release_flag_survives_lua_export() -> None:
    game: Any = NS(
        settings=Settings(),
        theater=NS(
            controlpoints=[],
            iads_network=NS(advanced_iads=False, skynet_nodes=lambda _: []),
        ),
    )
    game.settings.set_plugin_option("gpsjamming", False)
    mission = Mission()
    data = MissionData()
    data.escorts.append(EscortInfo(2, 1, 50000, "split-test"))
    generator = LuaGenerator(game, mission, data)
    generator.generate_plugin_data()
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("env={info=function()end}")
    action = mission.triggerrules.triggers[-1].actions[0]
    assert isinstance(action, DoScript)
    lua.execute(action.text.id)
    assert lua.eval("dcsRetribution.Escorts[1].releaseFlag") == "split-test"


def runtime() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        now=0;flag=0;groups={};scheduled={}
        timer={getTime=function()return now end,
          scheduleFunction=function(fn)scheduled[#scheduled+1]=fn end}
        trigger={misc={getUserFlag=function(name)assert(name=='split-test');return flag end}}
        AI={Option={Air={id={ROE=0},val={ROE={OPEN_FIRE=2,RETURN_FIRE=3}}}}}
        mist={DBs={groupsById={[1]={groupName='target'},[2]={groupName='escort'}}}}
        Group={getByName=function(name)return groups[name]end}
        function add(name,x)
          local u={};function u:getPoint()return {x=x,z=0}end
          local c={changes=0};function c:setOption(id,value)
            assert(id==0);self.roe=value;self.changes=self.changes+1
          end
          local g={controller=c};function g:getUnit()return u end
          function g:getController()return c end;groups[name]=g
        end
        add('target',0);add('escort',100000)
        dcsRetribution={Escorts={{escortGroupId=2,escortedGroupId=1,
          engagementRangeMeters=50000,releaseFlag='split-test'}}}
        function tick(t)now=t;return scheduled[1]()end
    """)
    script = Path("resources/plugins/base/dcs_retribution.lua").read_text(
        encoding="utf-8"
    )
    lua.execute(script[script.index("-- Escort leash") :])
    return lua


def test_split_releases_escort_roe_without_overriding_later_manual_orders() -> None:
    lua = runtime()
    lua.execute("tick(1)")
    assert lua.eval("groups.escort.controller.roe") == 3
    lua.execute("flag=1;tick(11)")
    assert lua.eval("groups.escort.controller.roe") == 2
    lua.execute("groups.escort.controller.roe=4;tick(21);tick(31)")
    assert lua.eval("groups.escort.controller.roe") == 4
    assert lua.eval("groups.escort.controller.changes") == 2


def test_legacy_leash_without_release_flag_keeps_existing_behavior() -> None:
    lua = runtime()
    lua.execute("dcsRetribution.Escorts[1].releaseFlag=nil;flag=1;tick(1);tick(11)")
    assert lua.eval("groups.escort.controller.roe") == 3
    assert lua.eval("groups.escort.controller.changes") == 2
