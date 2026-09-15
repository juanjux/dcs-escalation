"""Offline structural + instrument smoke tests; absolutely not a DCS AI simulator."""

from pathlib import Path
import argparse
import json
import zipfile

from dcs import lua
from dcs.mission import Mission
from dcs.planes import plane_map
from dcs.helicopters import helicopter_map
from lupa.lua51 import LuaRuntime

MOCK = r"""
_logs={}; _clock=0; _pending={}; _units={}; _groups={}; _commands={}
env={info=function(s) _logs[#_logs+1]=s end,mission=mission}
timer={getTime=function() return _clock end,
 scheduleFunction=function(f,a,t) _pending[#_pending+1]={f=f,a=a,t=t} end}
trigger={action={outText=function() end, markToCoalition=function() end,
 markToAll=function() end,removeMark=function() end}}
land={getHeight=function() return 200 end,isVisible=function() return true end}
Controller={Detection={VISUAL=1,OPTIC=2,RADAR=4}}
AI={Option={Ground={id={ROE=0},val={ROE={WEAPON_HOLD=4,OPEN_FIRE=2}}}}}
world={event={S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=23,S_EVENT_SHOOTING_END=24,
 S_EVENT_HIT=2,S_EVENT_DEAD=8,S_EVENT_CRASH=5,S_EVENT_KILL=28,S_EVENT_UNIT_LOST=30},
 addEventHandler=function(h) _handler=h end}
function newController()
 return {setCommand=function(self,c) _commands[#_commands+1]=c end,
 setOption=function() end,pushTask=function() end,setTask=function(self,task)
   if task.id=='Mission' and self.owner then
     local p=task.params.route.points[2]
     for _,u in ipairs(self.owner.units) do u.point.x=p.x; u.point.z=p.y end
   end
 end,knowTarget=function() end,
 isTargetDetected=function(self,t,mode) return true,true,true,true,_clock,t:getPoint(),{x=0,y=0,z=0} end}
end
for side,c in pairs(mission.coalition) do
 for _,country in pairs(c.country or {}) do
  for _,category in ipairs({'vehicle','plane','helicopter'}) do
   for _,def in pairs((country[category] or {}).group or {}) do
    local g={name=def.name,controller=newController(),units={}}
    g.controller.owner=g
    function g:isExist() return true end
    function g:getUnit(i) return self.units[i] end
    function g:getController() return self.controller end
    _groups[g.name]=g
    for _,u in pairs(def.units) do
     local o={name=u.name,point={x=u.x,y=u.alt or 200,z=u.y},g=g,controller=newController(),kind=u.type}
     function o:isExist() return true end
     function o:getName() return self.name end
     function o:getPoint() return self.point end
     function o:getPosition() return {p=self.point,x={x=1,y=0,z=0},y={x=0,y=1,z=0},z={x=0,y=0,z=1}} end
     function o:getVelocity() return {x=20,y=0,z=0} end
     function o:getController() return self.controller end
     function o:getGroup() return self.g end
     function o:getSensors() return {{type=0}} end
     function o:getRadar() return false,nil end
     function o:getLife() return 100 end
     function o:getAmmo()
       return {{count=self.kind=='Su-25T' and 2 or 100,
         desc={typeName=self.kind=='Su-25T' and 'weapons.missiles.X_29T' or 'mock ammo'}}}
     end
     function o:getTypeName() return self.kind end
     g.units[#g.units+1]=o; _units[o.name]=o
    end
   end
  end
 end
end
Unit={getByName=function(n) return _units[n] end}
Group={getByName=function(n) return _groups[n] end}
function c_time_after(t) return _clock>=t end
function a_do_script(s) assert(loadstring(s))() end
"""


def verify(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        text = z.read("mission").decode()
        cfg = json.loads(z.read("rcas_manifest.json"))
    m = lua.loads(text)["mission"]
    units, groups, group_names, names = {}, {}, set(), set()
    for coal in m["coalition"].values():
        for country in coal.get("country", {}).values():
            for category in ("vehicle", "plane", "helicopter"):
                for g in country.get(category, {}).get("group", {}).values():
                    assert g["groupId"] not in groups
                    groups[g["groupId"]] = g
                    assert g["name"] not in group_names
                    group_names.add(g["name"])
                    for u in g["units"].values():
                        assert u["skill"] == "Average"
                        assert u["unitId"] not in units and u["name"] not in names
                        units[u["unitId"]] = u
                        names.add(u["name"])

    def references(obj):
        if isinstance(obj, dict):
            if obj.get("id") in ("AttackUnit", "EngageUnit"):
                assert obj["params"]["unitId"] in units
            if obj.get("id") in ("AttackGroup", "EngageGroup"):
                assert obj["params"]["groupId"] in groups
            for v in obj.values():
                references(v)
        elif isinstance(obj, list):
            for v in obj:
                references(v)

    references(m)
    references(cfg)
    # Load our explicit stores only; do not scan unrelated installed mod presets.
    types = {**plane_map, **helicopter_map}
    for u in units.values():
        if u["type"] in types:
            types[u["type"]].payloads = {}
    parsed = Mission()
    assert not parsed.load_file(str(path)), "pydcs returned mission load warnings"
    for a in cfg["actions"]:
        if "target" in a:
            assert a["target"] in names | group_names
        if "other" in a:
            assert a["other"] in names
    runtime = LuaRuntime()
    runtime.execute(text)
    runtime.execute(MOCK)
    # Execute the *serialized mission trigger*, not just its copy in the ZIP.
    runtime.execute("assert(loadstring(mission.trig.actions[1]))()")
    runtime.execute("""
      local names={}; for n in pairs(_units) do names[#names+1]=n end
      table.sort(names)
      local src,dst=_units['CAS-1'] or _units[names[1]],_units[names[2]]
      local weapon={isExist=function() return _clock<120 end,
        getPoint=function() return {x=1,y=2,z=3} end,
        getTarget=function() return dst end,getTypeName=function()
          if RCAS_CONFIG.experiment and RCAS_CONFIG.experiment.variant~='always_hidden' then return 'X_29T' end
          return 'mock missile'
        end}
      _handler:onEvent({id=world.event.S_EVENT_SHOT,initiator=src,weapon=weapon})
      _handler:onEvent({id=world.event.S_EVENT_HIT,initiator=src,target=dst,weapon=weapon})
      _handler:onEvent({id=world.event.S_EVENT_SHOOTING_START,initiator=src})
      local iterations=0
      while #_pending>0 do
        local p=table.remove(_pending,1); _clock=p.t
        local again=p.f(p.a,p.t)
        if again then _pending[#_pending+1]={f=p.f,a=p.a,t=again} end
        iterations=iterations+1; assert(iterations<2000,'scheduler never finishes')
      end
    """)
    logs = list(runtime.globals()._logs.values())
    errors = [line for line in logs if "|ERROR|" in line]
    assert not errors, errors
    assert any("FIN. Captura" in line for line in logs)
    assert any("WEAPON_TRACK" in line for line in logs)
    assert any("WEAPON_GONE" in line for line in logs)
    if "experiment" in cfg:
        assert not any(
            "INVALID" in line for line in logs
        ), "happy-path mock became invalid"
        assert any("knowType=true/knowDistance=true/lastTime=" in line for line in logs)
    print(
        f"PASS {path.name}: IDs/tasks/AI-only, serialized trigger, {len(logs)} mock log lines, zero Lua errors"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    files = sorted(args.directory.glob("*.miz"))
    assert files, "No missions found"
    for p in files:
        verify(p)
    print("Offline checks only: no DCS detection or weapon behavior has been verified.")
