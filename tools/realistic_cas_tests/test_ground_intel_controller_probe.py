"""Serialization and scheduler contracts for V2, not native AI acceptance."""

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from dcs import Mission
from dcs.lua import loads
from lupa.lua51 import LuaRuntime

from build_ground_intel_controller_probe import build_mission, METHODS, PLUGIN
from test_contact_core import CORE, ADAPTER, ADAPTER_FIXTURE

NATIVE_DOUBLE = """
Unit={getByName=function(name)return units[name]end}
units={};knows={};maxLive=0
AI={Option={Ground={id={ROE=0},val={ROE={OPEN_FIRE=2,WEAPON_HOLD=4}}}}}
world.event.S_EVENT_HIT=2
land={isVisible=function()return true end}
trigger={action={outText=function()end,activateGroup=function(g)
  g.exists=true
  for _,u in ipairs(g.units)do u.exists=true end
  local live=0
  for _,other in pairs(groups)do if other.exists then live=live+1 end end
  maxLive=math.max(maxLive,live);assert(live<=2,'overlapping active pairs')
end}}
function controller(scope,g)
  return {knowTarget=function(_,enemy,typed,distance)
    assert(typed and distance and enemy.g.side~=g.side)
    assert(RealisticCAS._running.service:isRevealed(enemy.g.id,g.side),'expired contact shared')
    knows[#knows+1]={scope=scope,receiver=g.name,target=enemy.name}
  end,isTargetDetected=function()return false end,getDetectedTargets=function()return {}end,
  setOption=function()end,setTask=function(_,task)
    local p=task.params.route.points[#task.params.route.points]
    for _,u in ipairs(g.units)do u.point={x=p.x,y=0,z=p.y}end
  end}
end
for side,data in pairs(mission.coalition)do
  if side=='blue' or side=='red' then
    for _,country in pairs(data.country)do
      for _,def in pairs((country.vehicle or {}).group or {})do
        local g=group(def.name,def.groupId,side=='blue' and 2 or 1)
        g.exists=false;g.units={}
        local native=controller('group',g)
        g.controller.knowTarget=native.knowTarget
        g.controller.isTargetDetected=native.isTargetDetected
        g.controller.getDetectedTargets=native.getDetectedTargets
        g.controller.setOption=native.setOption;g.controller.setTask=native.setTask
        function g:destroy()
          self.exists=false;for _,u in ipairs(self.units)do u.exists=false end
        end
        for _,data in pairs(def.units)do
          local u={name=data.name,id=data.unitId,g=g,exists=false,point={x=data.x,y=0,z=data.y}}
          function u:getName()return self.name end
          function u:getID()return self.id end
          function u:isExist()return self.exists end
          function u:getLife()return 100 end
          function u:getGroup()return self.g end
          function u:getCoalition()return self.g.side end
          function u:getPoint()return self.point end
          function u:getTypeName()return 'Ural-375'end
          function u:getPosition()return {x={x=0,y=0,z=1}}end
          function u:getAmmo()return {{count=100}}end
          u.controller=controller('unit',g)
          function u:getController()return self.controller end
          units[u.name]=u;g.units[#g.units+1]=u
        end
      end
    end
  end
end
"""


class GroundIntelControllerProbeTests(unittest.TestCase):
    def setUp(self):
        self.mission = build_mission()

    def saved(self, path):
        self.mission.save(path)
        Mission().load_file(str(path))
        with ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            native = archive.read("mission").decode("utf-8")
            saved = loads(native)["mission"]
            dictionary = loads(archive.read("l10n/DEFAULT/dictionary").decode("utf-8"))[
                "dictionary"
            ]
            action = saved["trigrules"][4]["actions"][1]["text"]
            script = dictionary.get(action, action)
            runtime = LuaRuntime()
            runtime.compile(native)
            runtime.compile(script)
            for source in ("core.lua", "ground-intel.lua", "dcs.lua"):
                content = archive.read("l10n/DEFAULT/" + source)
                self.assertEqual(content, (PLUGIN / source).read_bytes())
                runtime.compile(content.decode("utf-8"))
            return native, saved, script

    def test_round_trip_preserves_isolated_cases_geometry_and_locked_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            _, saved, script = self.saved(Path(directory) / "v2.miz")
        receivers, targets = [], []
        for side in ("blue", "red"):
            for country in saved["coalition"][side]["country"].values():
                for group in country.get("vehicle", {}).get("group", {}).values():
                    self.assertTrue(group["lateActivation"])
                    self.assertTrue(group["route"]["points"][1]["ETA_locked"])
                    self.assertEqual(len(group["units"]), 1)
                    unit = group["units"][1]
                    (targets if unit["type"] == "Ural-375" else receivers).append(unit)
        self.assertEqual(len(receivers), len(METHODS) * 2)
        self.assertEqual(len(targets), len(receivers))
        self.assertEqual(len({(u["x"], u["y"]) for u in receivers}), 1)
        self.assertEqual(len({(u["x"], u["y"]) for u in targets}), 1)
        self.assertNotIn("__CONFIG__", script)
        for method in METHODS:
            self.assertIn(method, script)
        self.assertIn("controller:getDetectedTargets(1,2,4,8,16,32)", script)
        self.assertIn("'r'..n..'='..raw(result[n])", script)

    def test_all_cases_run_without_overlapping_pairs_or_hidden_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            native, _, script = self.saved(Path(directory) / "v2.miz")
        runtime = LuaRuntime()
        for source in (
            CORE,
            ADAPTER_FIXTURE,
            ADAPTER,
            (PLUGIN / "ground-intel.lua").read_text("utf-8"),
            native,
            NATIVE_DOUBLE,
            script,
        ):
            runtime.execute(source)
        runtime.execute("""
        local steps=0
        while #pending>0 do
          table.sort(pending,function(a,b)return a.t<b.t end)
          local nextCall=table.remove(pending,1);now=nextCall.t
          local again=nextCall.f(nextCall.a,now)
          if again then pending[#pending+1]={f=nextCall.f,a=nextCall.a,t=again}end
          steps=steps+1;assert(steps<20000,'scheduler did not terminate')
        end
        assert(maxLive==2 and not RealisticCAS._running and next(handlers)==nil)
        local completed,results=0,0
        for _,line in ipairs(logs)do
          assert(not line:find('|ERROR|',1,true),line)
          assert(not line:find('SETUP_ERROR',1,true),line)
          assert(not line:find('ACTIVATION_ERROR',1,true),line)
          if line:find('GROUND_INTEL_V2|RESULT|',1,true)then results=results+1 end
          if line:find('GROUND_INTEL_V2|COMPLETE|',1,true)then
            completed=completed+1;assert(line:find('errors=0',1,true))
          end
        end
        assert(completed==1 and results==12)
        local counts={}
        for _,call in ipairs(knows)do
          assert(call.target==call.receiver..'_TARGET Unit #1','unrelated target delivered')
          assert(not call.receiver:find('CONTROL',1,true))
          local expected=call.receiver:find('GROUP_',1,true)and 'group' or 'unit'
          assert(call.scope==expected,'wrong controller scope')
          counts[call.receiver]=(counts[call.receiver]or 0)+1
        end
        for _,side in ipairs({'BLUE_','RED_'})do
          assert(counts[side..'CONTROL']==nil)
          for _,method in ipairs({'PRODUCTION','UNIT_ONCE','GROUP_ONCE'})do
            assert(counts[side..method]==2)
          end
          assert(counts[side..'UNIT_REFRESH']>2 and counts[side..'GROUP_REFRESH']>2)
        end
        for _,g in pairs(groups)do assert(not g.exists)end
        """)


if __name__ == "__main__":
    unittest.main()
