"""Real campaign plugin manager/generator/pydcs wiring, without running DCS."""

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from dcs import Mission
from dcs.action import DoScriptFile
from game.missiongenerator.luagenerator import LuaGenerator
from game.missiongenerator.realisticcascampaign import (
    inject_campaign,
    prepare_campaign,
    suppress_legacy_jtac,
    validate_compatibility,
    RealisticCASConfigurationError,
)
from game.plugins.luaplugin import LuaPlugin
from lupa.lua51 import LuaRuntime

import test_registry_export

ROOT = Path(__file__).resolve().parents[2]


class CampaignIntegrationTests(unittest.TestCase):
    def setUp(self):
        test_registry_export.RegistryTests.setUp(self)
        self.m.start_time = datetime(2026, 5, 17, 5)
        self.game = NS(
            theater=NS(
                timezone=timezone(timedelta(hours=3)),
                reference_position=NS(lat=35.4, lng=44.4),
            )
        )
        self.g = LuaGenerator(self.game, self.m, self.data, NS(theater_objects={}))
        self.p = LuaPlugin.from_json(
            "realisticcas", ROOT / "resources/plugins/realisticcas/plugin.json"
        )
        assert self.p is not None
        self.p.set_value(True)

    def test_disabled_inert_and_option_default_off(self):
        self.p.set_value(False)
        self.assertIsNone(prepare_campaign(object(), [self.p]))
        inject_campaign(object(), None)
        self.assertFalse(suppress_legacy_jtac([self.p]))
        definition = json.loads(
            (ROOT / "resources/plugins/realisticcas/plugin.json").read_text()
        )
        self.assertIs(definition["defaultValue"], False)

    def test_final_registry_environment_options_and_original_mission_unchanged(self):
        before = self.g.mission.weather.dict()
        units_before = [u.dict() for u in self.air.units]
        config = prepare_campaign(self.g, [self.p])
        self.assertEqual(config["ttl"], 600)
        self.assertEqual(config["environment"]["defaultCover"], "grassland")
        # Actual existing suntime-based campaign calculator, not a fake sunrise.
        sunrise = config["environment"]["solarDays"][0]["sunrise"]
        self.assertTrue(4 * 3600 < sunrise < 6 * 3600)
        self.assertEqual(config["registry"]["groups"][0]["name"], "GROUND")
        self.assertEqual(before, self.m.weather.dict())
        self.assertEqual(units_before, [u.dict() for u in self.air.units])
        self.assertEqual(len(self.m.triggerrules.triggers), 0)
        self.assertTrue(suppress_legacy_jtac([self.p]))

    def test_incompatible_plugins_and_legacy_jtac_rejected_before_injection(self):
        for name in ("tic", "ctld", "MooseAutolase"):
            with self.assertRaisesRegex(ValueError, name):
                prepare_campaign(self.g, [self.p, NS(identifier=name, enabled=True)])
            self.assertEqual(len(self.m.triggerrules.triggers), 0)
        self.data.jtacs.append(NS())
        with self.assertRaisesRegex(ValueError, "legacy JTAC"):
            prepare_campaign(self.g, [self.p])

    def test_actual_pydcs_sinai_and_falklands_names(self):
        from dcs.terrain import Sinai, Falklands

        for terrain, cover in ((Sinai(), "desert"), (Falklands(), "grassland")):
            with self.subTest(terrain=terrain.name):
                self.g.mission = Mission(terrain)
                self.g.mission.start_time = self.m.start_time
                config = prepare_campaign(self.g, [self.p])
                self.assertEqual(config["environment"]["defaultCover"], cover)
                self.assertEqual(config["observerBudget"], 64)
                self.assertEqual(config["losBudget"], 64)

    def test_compatibility_preflight_is_actionable_and_disabled_is_inert(self):
        ctld = NS(identifier="ctld", enabled=True)
        with self.assertRaisesRegex(RealisticCASConfigurationError, "ctld"):
            validate_compatibility([self.p, ctld])
        self.p.set_value(False)
        validate_compatibility([self.p, ctld])
        # Take Off must check before fallback planning or beginning the simulation.
        tree = ast.parse((ROOT / "qt_ui/widgets/QTopPanel.py").read_text())
        launch = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "launch_mission"
        )
        text = ast.unparse(launch)
        self.assertLess(
            text.index("validate_compatibility("),
            text.index("run_opfor_fallback_if_needed("),
        )
        self.assertIn("except RealisticCASConfigurationError", text)
        self.assertIn("Incompatible mission plugins", text)

    def test_option_source_is_same_plugin_as_injection_not_game_settings(self):
        for option in self.p.options:
            if option.identifier == "realisticcas.terrainProfile":
                option.set_value(1)
            if option.identifier == "realisticcas.contactSeconds":
                option.set_value(123)
        config = prepare_campaign(self.g, [self.p])
        self.assertEqual(config["environment"]["defaultCover"], "desert")
        self.assertEqual(config["ttl"], 123)
        for option in self.p.options:
            if option.identifier == "realisticcas.acquisitionSeconds":
                option.set_value(0)
        with self.assertRaises(ValueError):
            prepare_campaign(self.g, [self.p])

    def test_missing_source_rejected_before_any_resource_or_trigger(self):
        config = prepare_campaign(self.g, [self.p])
        with patch(
            "game.missiongenerator.realisticcascampaign.Path.is_file",
            return_value=False,
        ):
            with self.assertRaises(FileNotFoundError):
                inject_campaign(self.g, config)
        self.assertEqual(len(self.m.triggerrules.triggers), 0)
        self.assertEqual(self.g.plugin_scripts, [])

    def test_generated_miz_contains_ordered_files_and_typed_startup(self):
        config = prepare_campaign(self.g, [self.p])
        inject_campaign(self.g, config)
        triggers = self.m.triggerrules.triggers
        from game.missiongenerator.realisticcasluadata import SCRIPT_ORDER

        self.assertEqual(
            [t.comment for t in triggers[:-1]],
            [f"Load realisticcas-{n}" for n in SCRIPT_ORDER],
        )
        self.assertTrue(
            all(isinstance(t.actions[0], DoScriptFile) for t in triggers[:-1])
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integration.miz"
            self.m.save(path)
            parsed = Mission()
            parsed.load_file(str(path))
            rt = LuaRuntime()
            with zipfile.ZipFile(path) as archive:
                rt.compile(archive.read("mission").decode("utf-8"))
                scripts = [name for name in archive.namelist() if name.endswith(".lua")]
                self.assertEqual(len(scripts), 7)
                for name in scripts:
                    rt.compile(archive.read(name).decode("utf-8"))
                # Validate generated trigger action strings too (Lua text inside strings).
                rt.execute(archive.read("mission").decode("utf-8"))
                for _, action in rt.globals().mission["trig"]["actions"].items():
                    rt.compile(action)

    def test_real_generate_hook_calls_prepare_before_other_lua_and_starts_last(self):
        # Exercise the real generate() control flow, isolating unrelated plugins.
        with patch(
            "game.missiongenerator.luagenerator.LuaPluginManager.plugins",
            return_value=[self.p],
        ):
            with patch.object(self.g, "generate_plugin_data"), patch.object(
                self.g, "_seed_pilot_roster"
            ), patch.object(self.g, "_seed_scenery_objectives"), patch.object(
                self.g, "_inject_tic_script"
            ):
                self.g.generate()
        self.assertEqual(
            self.m.triggerrules.triggers[-1].comment,
            "Realistic CAS: campaign registry and start",
        )

    def test_flot_jtac_guard_does_not_swallow_frontline_metadata(self):
        # Structural regression for the legacy branch; creating a real FLOT needs
        # the campaign fixtures in the subsequent full-campaign acceptance test.
        tree = ast.parse((ROOT / "game/missiongenerator/flotgenerator.py").read_text())
        guards = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.If) and "suppress_legacy_jtac" in ast.unparse(n.test)
        ]
        self.assertEqual(len(guards), 1)
        text = ast.unparse(guards[0])
        self.assertIn("mission_data.jtacs.append", text)
        self.assertNotIn("mission_data.player_frontline_groups.append", text)
        self.assertNotIn("mission_data.enemy_frontline_groups.append", text)


if __name__ == "__main__":
    unittest.main()
