"""V3 serialization, isolation guards and reporting, not native fog acceptance."""

from pathlib import Path
import tempfile
import unittest

from lupa.lua51 import LuaRuntime

from build_ground_intel_controller_probe import build_mission, ISOLATION_CASES, PLUGIN
from test_contact_core import CORE, ADAPTER, ADAPTER_FIXTURE
import test_ground_intel_controller_probe as controller_probe_tests

SENSOR_DOUBLE = """
fogThickness=0;fogVisibility=0;weatherCalls=0
world.weather={
  setFogThickness=function(value)fogThickness=value;weatherCalls=weatherCalls+1 end,
  setFogVisibilityDistance=function(value)fogVisibility=value end,
  getFogThickness=function()return fogThickness end,
  getFogVisibilityDistance=function()return fogVisibility end}
for _,g in pairs(groups)do
  if not g.name:find('_TARGET',1,true)then
    local function detected()
      local target=groups[g.name..'_TARGET']
      local visible=RealisticCAS._running and RealisticCAS._running.service:isRevealed(target.id,g.side)
      if leak and g.name:find('FOG_PRODUCTION',1,true)and g.notified then return true end
      return visible and (fogThickness==0 or blindControlFails or (effect and g.notified))or false
    end
    for _,controller in ipairs({g.controller,g.units[1].controller})do
      local know=controller.knowTarget
      controller.knowTarget=function(self,...)
        know(self,...);g.notified=true;return true
      end
      controller.isTargetDetected=detected
      controller.getDetectedTargets=function()
        return detected()and {{object=units[g.name..'_TARGET Unit #1']}}or{}
      end
      controller.setOption=function()
        if detected()and not g.fired and not noFiring and not (knowledgeOnly and fogThickness>0)then
          g.fired=true
          for h in pairs(handlers)do h:onEvent({id=world.event.S_EVENT_SHOT,initiator=g.units[1]})end
        end
      end
    end
  end
end
"""

RUN_SEQUENCE = """
local steps=0
while #pending>0 do
  table.sort(pending,function(a,b)return a.t<b.t end)
  local nextCall=table.remove(pending,1);now=nextCall.t
  local again=nextCall.f(nextCall.a,now)
  if again then pending[#pending+1]={f=nextCall.f,a=nextCall.a,t=again}end
  steps=steps+1;assert(steps<20000,'scheduler did not terminate')
end
assert(not RealisticCAS._running and next(handlers)==nil)
for _,g in pairs(groups)do assert(not g.exists)end
"""


class GroundIntelSensorProbeTests(unittest.TestCase):
    saved = controller_probe_tests.GroundIntelControllerProbeTests.saved

    def setUp(self):
        self.mission = build_mission(sensor_isolation=True)

    def execute(self, options="", weather_override=""):
        with tempfile.TemporaryDirectory() as directory:
            native, _, script = self.saved(Path(directory) / "v3.miz")
        runtime = LuaRuntime()
        for source in (
            CORE,
            ADAPTER_FIXTURE,
            ADAPTER,
            (PLUGIN / "ground-intel.lua").read_text("utf-8"),
            native,
            controller_probe_tests.NATIVE_DOUBLE,
            options,
            SENSOR_DOUBLE,
            weather_override,
            script,
            RUN_SEQUENCE,
        ):
            runtime.execute(source)
        return [line for _, line in runtime.globals().logs.items()]

    def test_round_trip_keeps_fresh_pairs_and_clear_cloud_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            _, saved, script = self.saved(Path(directory) / "v3.miz")
        self.assertEqual(saved["weather"]["clouds"]["base"], 3000)
        self.assertFalse(saved["weather"]["enable_fog"])
        positions = {}
        groups = []
        for side in ("blue", "red"):
            for country in saved["coalition"][side]["country"].values():
                for group in country.get("vehicle", {}).get("group", {}).values():
                    groups.append(group)
                    self.assertTrue(group["lateActivation"])
                    self.assertTrue(group["route"]["points"][1]["ETA_locked"])
                    self.assertEqual(len(group["units"]), 1)
                    unit = group["units"][1]
                    positions.setdefault(unit["type"], set()).add(
                        (unit["x"], unit["y"])
                    )
                    tasks = group["route"]["points"][1]["task"]["params"]["tasks"]
                    immortal = any(
                        task["params"].get("action", {}).get("id") == "SetImmortal"
                        for task in tasks.values()
                    )
                    self.assertEqual(immortal, unit["type"] == "Ural-375")
        self.assertEqual(len(groups), len(ISOLATION_CASES) * 4)
        self.assertTrue(all(len(p) == 1 for p in positions.values()))
        for scenario, _, _ in ISOLATION_CASES:
            self.assertIn(scenario, script)
        self.assertIn('"sensorIsolation"', script)

    def test_isolated_control_reports_knowledge_and_firing_separately(self):
        logs = self.execute("effect=true")
        results = [line for line in logs if "GROUND_INTEL_V3|RESULT|" in line]
        self.assertEqual(len(results), 10)
        self.assertTrue(all("errors=0" in line for line in results))
        qualifications = [line for line in logs if "|QUALIFICATION|" in line]
        self.assertEqual(len(qualifications), 2)
        self.assertTrue(all("status=ISOLATED" in line for line in qualifications))
        effects = [line for line in logs if "|EFFECT|" in line]
        self.assertEqual(len(effects), 6)
        self.assertTrue(
            all("knowledge=OBSERVED|engagement=OBSERVED" in s for s in effects)
        )
        self.assertTrue(all("expiry=NO_LEAK_OBSERVED" in s for s in effects))
        self.assertTrue(any("|COMPLETE|" in s and "errors=0" in s for s in logs))

    def test_blind_control_acquisition_makes_positive_effect_inconclusive(self):
        logs = self.execute("effect=true;blindControlFails=true")
        self.assertEqual(sum("|QUALIFICATION|" in s for s in logs), 2)
        self.assertTrue(
            all("status=INCONCLUSIVE" in s for s in logs if "|QUALIFICATION|" in s)
        )
        self.assertTrue(
            all(
                "knowledge=INCONCLUSIVE|engagement=INCONCLUSIVE" in s
                for s in logs
                if "|EFFECT|" in s
            )
        )

    def test_accepted_calls_alone_do_not_report_an_effect(self):
        logs = self.execute()
        self.assertTrue(
            all("status=ISOLATED" in s for s in logs if "|QUALIFICATION|" in s)
        )
        self.assertTrue(
            all(
                "knowledge=NOT_OBSERVED|engagement=NOT_OBSERVED" in s
                for s in logs
                if "|EFFECT|" in s
            )
        )

    def test_knowledge_is_not_reported_as_engagement(self):
        logs = self.execute("effect=true;knowledgeOnly=true")
        effects = [s for s in logs if "|EFFECT|" in s]
        self.assertEqual(len(effects), 6)
        self.assertTrue(
            all("knowledge=OBSERVED|engagement=NOT_OBSERVED" in s for s in effects)
        )

    def test_failed_clear_weapon_control_makes_the_side_inconclusive(self):
        logs = self.execute("effect=true;noFiring=true")
        qualifications = [s for s in logs if "|QUALIFICATION|" in s]
        self.assertEqual(len(qualifications), 2)
        self.assertTrue(all("status=INCONCLUSIVE" in s for s in qualifications))

    def test_native_contact_remaining_after_expiry_is_reported(self):
        logs = self.execute("effect=true;leak=true")
        effects = [s for s in logs if "|EFFECT|" in s and "method=FOG_PRODUCTION" in s]
        self.assertEqual(len(effects), 2)
        self.assertTrue(all("expiry=LEAK_OBSERVED" in s for s in effects))

    def test_missing_or_clamped_weather_does_not_silently_run(self):
        for override in (
            "world.weather=nil",
            "world.weather.setFogThickness=function(value)fogThickness=math.min(value,500)end",
        ):
            with self.subTest(override=override):
                logs = self.execute("effect=true", override)
                self.assertTrue(any("ACTIVATION_ERROR" in s for s in logs))
                self.assertTrue(
                    all(
                        "status=INCONCLUSIVE" in s
                        for s in logs
                        if "|QUALIFICATION|" in s
                    )
                )
                self.assertFalse(any("knowledge=OBSERVED" in s for s in logs))


if __name__ == "__main__":
    unittest.main()
