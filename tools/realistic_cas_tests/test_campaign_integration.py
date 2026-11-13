"""Real campaign plugin manager/generator/pydcs wiring, without running DCS."""

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
)
from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
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
        definition = json.loads(
            (ROOT / "resources/plugins/realisticcas/plugin.json").read_text()
        )
        self.assertIs(definition["defaultValue"], False)

    def test_contact_report_options_are_exported_and_validated(self):
        options = {o.identifier: o for o in self.p.options}
        config = prepare_campaign(self.g, [self.p])
        self.assertIs(config["contactReports"], True)
        self.assertEqual(config["contactReportSeconds"], 15)
        self.assertEqual(
            options["realisticcas.contactReportSeconds"].enabled_by,
            "realisticcas.contactReports",
        )
        options["realisticcas.contactReports"].set_value(False)
        options["realisticcas.contactReportSeconds"].set_value(45)
        config = prepare_campaign(self.g, [self.p])
        self.assertIs(config["contactReports"], False)
        self.assertEqual(config["contactReportSeconds"], 45)
        for value in (0, 301, False, 1.5):
            options["realisticcas.contactReportSeconds"].set_value(value)
            with self.assertRaisesRegex(ValueError, "report duration"):
                prepare_campaign(self.g, [self.p])
        options["realisticcas.contactReportSeconds"].set_value(15)
        options["realisticcas.contactReports"].set_value("yes")
        with self.assertRaisesRegex(ValueError, "reports must be boolean"):
            prepare_campaign(self.g, [self.p])

    def test_final_registry_environment_options_and_original_mission_unchanged(self):
        before = self.g.mission.weather.dict()
        units_before = [u.dict() for u in self.air.units]
        config = prepare_campaign(self.g, [self.p])
        self.assertEqual(config["ttl"], 600)
        self.assertIs(config["probabilisticDetection"], True)
        self.assertEqual(config["environment"]["defaultCover"], "grassland")
        # Actual existing suntime-based campaign calculator, not a fake sunrise.
        sunrise = config["environment"]["solarDays"][0]["sunrise"]
        self.assertTrue(4 * 3600 < sunrise < 6 * 3600)
        self.assertEqual(config["registry"]["groups"][0]["name"], "GROUND")
        self.assertEqual(before, self.m.weather.dict())
        self.assertEqual(units_before, [u.dict() for u in self.air.units])
        self.assertEqual(len(self.m.triggerrules.triggers), 0)

    def test_ctld_runs_alongside_realistic_cas(self):
        ctld = LuaPlugin.from_json("ctld", ROOT / "resources/plugins/ctld/plugin.json")
        assert ctld is not None
        ctld.set_value(True)
        self.game.settings = NS(jtac_count=3)
        self.assertIsNotNone(prepare_campaign(self.g, [self.p, ctld]))

    def test_ctld_keeps_full_infantry_capacity_without_jtacs(self):
        lua = LuaRuntime()
        lua.execute("""
        env={info=function()end,error=function()end,setErrorMessageBoxEnabled=function()end}
        timer={getTime=function()return 0 end,scheduleFunction=function()end}
        """)
        scripts = ROOT / "resources/plugins/ctld"
        lua.execute((scripts / "CTLD.lua").read_text(encoding="utf-8"))
        lua.execute("""
        assert(not ctld.JTACAutoLase and not ctld.addJTACRadioCommand)
        dcsRetribution={plugins={ctld={tailorctld=true}},Logistics={
          flights={},crates={},transports={},spawnable_crates={}
        }}
        """)
        lua.execute((scripts / "ctld-config.lua").read_text(encoding="utf-8"))
        lua.execute("""
        for _,squad in ipairs(ctld.loadableGroups)do
          assert(not squad.jtac)
          if squad.name=='Retribution Troops (24)'then
            assert(squad.inf+squad.mg+squad.at+squad.aa==24)
            return
          end
        end
        error('missing 24-person squad')
        """)

    def test_ctld_ai_transport_unloads_when_an_enemy_is_visible(self):
        lua = LuaRuntime()
        lua.execute("""
        env={info=function()end,error=function()end,setErrorMessageBoxEnabled=function()end}
        timer={getTime=function()return 0 end,scheduleFunction=function()end}
        """)
        source = ROOT / "resources/plugins/ctld/CTLD.lua"
        lua.execute(source.read_text(encoding="utf-8"))
        lua.execute("""
        local function unit(side, x)
          return {
            getPoint=function()return {x=x,y=0,z=0} end,
            getCoalition=function()return side end,
            getPlayerName=function()end,
            getLife=function()return 100 end,
            isActive=function()return true end,
            inAir=function()return false end,
          }
        end
        local transport, enemy = unit(2,0), unit(1,1000)
        local visible, deployments = false, 0
        ctld.getTransportUnit=function()return transport end
        ctld.troopsOnboard=function(_,troops)return troops end
        ctld.unitCanCarryVehicles=function()return false end
        ctld.deployTroops=function()deployments=deployments+1 end
        land={isVisible=function()return visible end}
        Object={Category={UNIT=1}}
        world={VolumeType={SPHERE=1},searchObjects=function(_,volume,visit)
          assert(volume.params.radius==10000)
          visit(enemy)
        end}
        assert(not ctld.unloadInProximityToEnemy('transport'))
        visible=true
        assert(ctld.unloadInProximityToEnemy('transport'))
        assert(deployments==1)
        """)

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

    def test_option_source_is_same_plugin_as_injection_not_game_settings(self):
        for option in self.p.options:
            if option.identifier == "realisticcas.terrainProfile":
                option.set_value(1)
            if option.identifier == "realisticcas.contactSeconds":
                option.set_value(123)
            if option.identifier == "realisticcas.probabilisticDetection":
                option.set_value(False)
        config = prepare_campaign(self.g, [self.p])
        self.assertEqual(config["environment"]["defaultCover"], "desert")
        self.assertEqual(config["ttl"], 123)
        self.assertIs(config["probabilisticDetection"], False)
        self.assertEqual(config["acquisitionSeconds"], 0)
        self.assertNotIn(
            "realisticcas.acquisitionSeconds", [o.identifier for o in self.p.options]
        )

    def test_missing_source_rejected_before_any_resource_or_trigger(self):
        config = prepare_campaign(self.g, [self.p])
        with patch(
            "game.missiongenerator.realisticcascampaign.Path.is_file",
            return_value=False,
        ):
            with self.assertRaises(FileNotFoundError):
                inject_campaign(self.g, config)
        self.assertEqual(len(self.m.triggerrules.triggers), 0)

    def test_retired_search_time_is_ignored_even_from_an_old_option_definition(self):
        old = NS(identifier="realisticcas.acquisitionSeconds", get_value=99)
        plugin = NS(
            identifier="realisticcas", enabled=True, options=[*self.p.options, old]
        )
        config = prepare_campaign(self.g, [plugin])
        self.assertEqual(config["acquisitionSeconds"], 0)
        self.assertEqual(old.get_value, 99)
        self.assertEqual(self.g.plugin_scripts, [])

    def test_probability_defaults_match_manifest_python_and_lua(self):
        from game.missiongenerator.realisticcasluadata import PROBABILITY_DEFAULTS

        from test_sensors import CORE, SOURCES

        defaults = {
            o.identifier.removeprefix("realisticcas."): o.get_value
            for o in self.p.options
        }
        rt = LuaRuntime()
        rt.execute(CORE)
        for source in SOURCES:
            rt.execute(source)
        lua_defaults = dict(rt.eval("RealisticCAS.Sensors.probabilityConfig()"))
        self.assertEqual(lua_defaults, PROBABILITY_DEFAULTS)
        for name, value in PROBABILITY_DEFAULTS.items():
            self.assertEqual(defaults[name], value)
        self.assertEqual(
            prepare_campaign(self.g, [self.p])["probability"], lua_defaults
        )

    def test_changed_probability_options_reach_export_and_bad_pairs_fail(self):
        options = {
            o.identifier.removeprefix("realisticcas."): o for o in self.p.options
        }
        options["retrySeconds"].set_value(17)
        options["radarFarPercent"].set_value(70)
        options["radarNearPercent"].set_value(99)
        options["visualMaxAGL"].set_value(2100)
        config = prepare_campaign(self.g, [self.p])
        self.assertEqual(config["probability"]["retrySeconds"], 17)
        self.assertEqual(config["probability"]["radarFarPercent"], 70)
        self.assertEqual(config["probability"]["radarNearPercent"], 99)
        self.assertEqual(config["probability"]["visualMaxAGL"], 2100)
        from game.missiongenerator.realisticcasluadata import render_startup

        rt = LuaRuntime()
        rt.execute("RealisticCAS={startMission=function(c) captured=c;return {} end}")
        rt.execute(render_startup(config))
        self.assertEqual(dict(rt.globals().captured.probability), config["probability"])
        options["radarFarPercent"].set_value(100)
        with self.assertRaisesRegex(ValueError, "far chance"):
            prepare_campaign(self.g, [self.p])

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
                self.assertEqual(
                    len(scripts), len(test_registry_export.EXPORT.SCRIPT_ORDER)
                )
                for name in scripts:
                    rt.compile(archive.read(name).decode("utf-8"))
                # Validate generated trigger action strings too (Lua text inside strings).
                rt.execute(archive.read("mission").decode("utf-8"))
                for _, action in rt.globals().mission["trig"]["actions"].items():
                    rt.compile(action)

    def test_real_generate_hook_calls_prepare_before_other_lua_and_starts_last(self):
        self.game.settings = Settings(gps_jamming_enabled=False)
        # Exercise the real generate() control flow, isolating unrelated plugins.
        with patch(
            "game.missiongenerator.luagenerator.LuaPluginManager.plugins",
            return_value=[self.p],
        ):
            with patch.object(self.g, "generate_plugin_data"), patch.object(
                self.g, "_seed_scenery_objectives"
            ), patch.object(self.g, "_seed_persistent_damage"), patch.object(
                self.g, "_inject_aircraft_maintenance"
            ):
                self.g.generate()
        self.assertEqual(
            self.m.triggerrules.triggers[-1].comment,
            "Realistic CAS: campaign registry and start",
        )


if __name__ == "__main__":
    unittest.main()
