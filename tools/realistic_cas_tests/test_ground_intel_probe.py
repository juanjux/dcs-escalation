"""Round-trip the native ground-intelligence probe and compile its saved scripts."""

from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from dcs import Mission
from dcs.lua import loads
from lupa.lua51 import LuaRuntime

from build_ground_intel_probe import build_mission, PLUGIN


class GroundIntelProbeTests(unittest.TestCase):
    def test_stock_mission_round_trip_keeps_scripts_and_automatic_phases(self):
        mission = build_mission()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ground-intel.miz"
            mission.save(path)
            Mission().load_file(str(path))
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                runtime = LuaRuntime()
                runtime.compile(archive.read("mission").decode("utf-8"))
                saved = loads(archive.read("mission").decode("utf-8"))["mission"]
                dictionary = loads(
                    archive.read("l10n/DEFAULT/dictionary").decode("utf-8")
                )["dictionary"]
                for source in ("core.lua", "ground-intel.lua", "dcs.lua"):
                    content = archive.read("l10n/DEFAULT/" + source)
                    self.assertEqual(content, (PLUGIN / source).read_bytes())
                    runtime.compile(content.decode("utf-8"))
                action = saved["trigrules"][4]["actions"][1]["text"]
                script = dictionary.get(action, action)
                runtime.compile(script)
                self.assertNotIn("__CONFIG__", script)
                for phase in ("later(20,observe)", "later(140,observe)", "later(240,"):
                    self.assertIn(phase, script)
                vehicles = []
                for side in ("blue", "red"):
                    for country in saved["coalition"][side]["country"].values():
                        vehicles.extend(
                            country.get("vehicle", {}).get("group", {}).values()
                        )
                self.assertEqual(len(vehicles), 8)
                for group in vehicles:
                    self.assertEqual(len(group["units"]), 1)
                    self.assertIn(
                        group["units"][1]["type"], ("T-72B", "M-1 Abrams", "Ural-375")
                    )


if __name__ == "__main__":
    unittest.main()
