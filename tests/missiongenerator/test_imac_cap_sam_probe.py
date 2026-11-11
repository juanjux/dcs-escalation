"""Saved native probe resources and unattended case scheduling."""

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from typing import Any

import pytest

from dcs import Mission
from dcs.lua import loads
from dcs.unittype import FlyingType

from tools.imac_cap_sam_probe import build_mission, PLUGIN, SCRIPTS


def saved_probe(path: Path) -> tuple[dict[str, Any], str]:
    build_mission().save(path)
    Mission().load_file(str(path))
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        native = archive.read("mission").decode("utf-8")
        saved = loads(native)["mission"]
        dictionary = loads(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))[
            "dictionary"
        ]
        text = saved["trigrules"][4]["actions"][1]["text"]
        script = dictionary.get(text, text)
        runtime = pytest.importorskip("lupa.lua51").LuaRuntime()
        runtime.compile(native)
        runtime.compile(script)
        for name in SCRIPTS:
            resource = archive.read("l10n/DEFAULT/" + name)
            assert resource == (PLUGIN / name).read_bytes()
            runtime.compile(resource.decode("utf-8"))
        return saved, script


def test_probe_serializes_stock_armed_patrols_and_locked_late_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(FlyingType, "loadout", classmethod(lambda cls, task: None))
    saved, script = saved_probe(tmp_path / "cap.miz")
    planes = []
    vehicles = []
    for side in ("blue", "red"):
        for country in saved["coalition"][side]["country"].values():
            planes.extend(country.get("plane", {}).get("group", {}).values())
            vehicles.extend(country.get("vehicle", {}).get("group", {}).values())
    assert len(planes) == 8 and len(vehicles) == 4
    for group in planes + vehicles:
        assert group["lateActivation"]
        assert group["route"]["points"][1]["ETA_locked"]
    fighters = [g for g in planes if not g["name"].endswith("_BAIT")]
    assert len(fighters) == 4
    for group in fighters:
        assert len(group["units"]) == 2
        assert all(unit["payload"]["pylons"] for unit in group["units"].values())
        tasks = group["route"]["points"][2]["task"]["params"]["tasks"]
        engage = next(task for task in tasks.values() if task["id"] == "EngageTargets")
        assert engage["params"]["maxDist"] == 92600
        assert engage["params"]["targetTypes"][1] == "Air"
    assert "__CONFIG__" not in script


def test_probe_sequence_activates_only_one_case_and_cleans_up() -> None:
    with TemporaryDirectory() as directory:
        _, script = saved_probe(Path(directory) / "cap.miz")
    runtime = pytest.importorskip("lupa.lua51").LuaRuntime()
    runtime.execute("""
        now=0;pending={};groups={};logs={};handlers={};peak=0
        timer={getTime=function()return now end,scheduleFunction=function(f,a,t)
          pending[#pending+1]={f=f,a=a,t=t}end}
        env={info=function(line)logs[#logs+1]=line end}
        world={event={S_EVENT_SHOT=1},addEventHandler=function(h)handlers[h]=true end,
          removeEventHandler=function(h)handlers[h]=nil end}
        Group={getByName=function(name)return groups[name]end}
        trigger={action={outText=function()end,activateGroup=function(g)
          g.active=true
          local count=0;for _,other in pairs(groups)do if other.active then count=count+1 end end
          peak=math.max(peak,count);assert(count<=3,'overlapping cases')
        end}}
        EscalationIMAC={geometry={distance=function(a,b)
          return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2)end},start=function(cfg)
          local api={states={},history={}}
          function api:stop()self.stopped=true end
          for _,flight in ipairs(cfg.flights)do
            api.states[flight.group]={}
            for _,name in ipairs({flight.group,flight.group..'_BAIT',flight.group..'_SAM'})do
              local g={active=false}
              function g:isExist()return self.active end
              function g:destroy()self.active=false end
              local u={}
              function u:isExist()return g.active end
              function u:getLife()return 100 end
              function u:getPoint()return {x=0,y=6500,z=0}end
              function u:getController()return {isTargetDetected=function()return false end}end
              function g:getUnits()return {u}end
              groups[name]=g
            end
          end
          savedAPI=api;return api
        end}
    """)
    runtime.execute(script)
    runtime.execute("""
        local steps=0
        while #pending>0 do
          table.sort(pending,function(a,b)return a.t<b.t end)
          local call=table.remove(pending,1);now=call.t
          local again=call.f(call.a,now)
          if again then pending[#pending+1]={f=call.f,a=call.a,t=again}end
          steps=steps+1;assert(steps<2000,'sequence did not terminate')
        end
        assert(savedAPI.stopped and next(handlers)==nil and peak==3)
        for _,g in pairs(groups)do assert(not g.active)end
        local results,complete=0,0
        for _,line in ipairs(logs)do
          assert(not line:find('|ERROR|',1,true),line)
          if line:find('|RESULT|',1,true)then results=results+1 end
          if line:find('|COMPLETE|',1,true)then complete=complete+1 end
        end
        assert(results==4 and complete==1)
    """)
