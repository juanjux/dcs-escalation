"""Final pydcs weather -> Lua environment. No DCS-engine claims."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from dcs import Mission
from dcs.weather import CloudPreset
from lupa.lua51 import LuaRuntime

from test_contact_core import PLUGIN
from test_registry_export import EXPORT

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "rcas_environment", ROOT / "game/missiongenerator/realisticcasenvironment.py"
)
ENV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENV)


class EnvironmentExportTests(unittest.TestCase):
    def setUp(self):
        self.m = Mission()
        self.m.start_time = datetime(2026, 5, 17, 5)
        self.theater = NS(
            timezone=timezone(timedelta(hours=3)),
            reference_position=NS(lat=35.4, lng=44.4),
        )
        self.dates = []

    def sun(self, lat, lon, tz, date):
        self.dates.append((lat, lon, tz, date))
        return (
            datetime(date.year, date.month, date.day, 5, 10, tzinfo=tz),
            datetime(date.year, date.month, date.day, 19, 2, tzinfo=tz),
        )

    def export(self, **kwargs):
        kwargs.setdefault("sun_times", self.sun)
        return ENV.export_environment(
            self.m, self.theater, default_cover="desert", **kwargs
        )

    def lua_environment(self, config):
        rt = LuaRuntime()
        for name in ("core.lua", "sensors.lua", "environment.lua"):
            rt.execute((PLUGIN / name).read_text(encoding="utf-8"))
        rt.execute(
            "e=RealisticCAS.newEnvironment(" + EXPORT.lua_literal(config) + ");"
            "a={point={x=0,y=5000,z=0}};b={point={x=0,y=0,z=0}};"
            "function sample(t) return e(a,b,t) end"
        )
        return rt

    def test_final_mission_time_visibility_and_no_mutation(self):
        before = self.m.weather.dict()
        self.m.weather.visibility_distance = 17000
        cfg, warnings = self.export()
        self.assertEqual(cfg["startTime"], 18000)
        self.assertEqual(cfg["visibility"], 17000)
        self.assertEqual(len(self.dates), 3)
        self.assertEqual(self.dates[-1][3].day, 19)
        self.assertEqual(cfg["solarDays"][0]["sunrise"], 18600)
        self.assertNotIn("clouds", cfg)
        before["visibility"]["distance"] = 17000
        self.assertEqual(self.m.weather.dict(), before)
        self.assertTrue(any("homogeneous" in w for w in warnings))
        sample = self.lua_environment(cfg).globals().sample
        self.assertLess(sample(0)["light"], 1)
        self.assertEqual(sample(601)["light"], 1)

    def test_aware_time_converted_before_selecting_calendar_date(self):
        self.m.start_time = datetime(2026, 5, 16, 23, tzinfo=timezone.utc)
        cfg, _ = self.export()
        self.assertEqual(cfg["startTime"], 7200)
        self.assertEqual(self.dates[0][3].day, 17)

    def test_calendar_uses_next_day_schedule_and_is_copied(self):
        cfg, _ = self.export()
        cfg["startTime"] = 23 * 3600
        cfg["solarDays"] = [
            {"constantLight": 1},
            {"constantLight": 0},
            {"constantLight": 1},
        ]
        rt = self.lua_environment(cfg)
        sample = rt.globals().sample
        self.assertEqual(sample(0)["light"], 1)
        self.assertEqual(sample(3600)["light"], 0)
        self.assertEqual(sample(90000)["light"], 1)
        self.assertEqual(sample(400000)["light"], 1)  # documented final-day repeat

    def test_polar_day_and_night_and_opposite_hemisphere(self):
        self.theater.reference_position.lat = 75
        for month, expected in ((6, 1), (12, 0)):
            self.m.start_time = datetime(2026, month, 21)
            cfg, warnings = self.export(sun_times=lambda *a: None)
            self.assertEqual(cfg["solarDays"][0]["constantLight"], expected)
            self.assertEqual(
                self.lua_environment(cfg).globals().sample(1234)["light"], expected
            )
            self.assertTrue(any("polar" in w for w in warnings))
        self.theater.reference_position.lat = -75
        cfg, _ = self.export(sun_times=lambda *a: None)
        self.assertEqual(cfg["solarDays"][0]["constantLight"], 1)

    def test_wrapped_solar_day_and_midnight_twilight(self):
        rt = self.lua_environment(self.export()[0])
        rt.execute("""
        local S=RealisticCAS.Sensors
        assert(S.lightAt(0,23*3600,3600)==1)
        assert(S.lightAt(12*3600,23*3600,3600)==0)
        assert(S.lightAt(0,900,23*3600)==0.5)
        assert(S.lightAt(43200,0,86400)==1)
        assert(not pcall(S.lightAt,0,1,1))
        """)

    def preset(self, text):
        self.m.weather.clouds_preset = CloudPreset("Preset1", text, text, 500, 5000)
        self.m.weather.clouds_base = 1500
        self.m.weather.clouds_density = 0
        self.m.weather.clouds_thickness = 0

    def test_zero_density_preset_is_not_clear_and_name_is_not_capability(self):
        self.preset("Overcast rain")
        cfg, warnings = self.export()
        self.assertEqual(cfg["clouds"]["base"], 1500)
        self.assertEqual(cfg["clouds"]["top"], 4500)
        self.assertEqual(cfg["weather"], 0.7)
        sample = self.lua_environment(cfg).globals().sample(3600)
        self.assertEqual(sample["visualTransmission"], 0.05)
        self.assertEqual(sample["irTransmission"], 0.35)
        self.assertTrue(any("approximate slab" in w for w in warnings))
        self.preset("Few clouds")  # same Preset1 key, different authored pack
        other, _ = self.export()
        self.assertEqual(other["clouds"]["visualTransmission"], 0.8)

    def test_unknown_preset_is_explicit_fallback_not_clear(self):
        self.preset("Custom 2026")
        cfg, warnings = self.export()
        self.assertIn("clouds", cfg)
        self.assertTrue(any("unclassified fallback" in w for w in warnings))

    def test_numeric_clouds_ir_not_universal_veto(self):
        self.m.weather.clouds_density = 8
        self.m.weather.clouds_thickness = 1700
        cfg, _ = self.export()
        self.assertAlmostEqual(cfg["clouds"]["visualTransmission"], 0.2)
        self.assertGreater(cfg["clouds"]["irTransmission"], 0)
        self.m.weather.clouds_density = float("nan")
        with self.assertRaises(ValueError):
            self.export()

    def test_inactive_fog_default_does_not_limit_visibility(self):
        cfg, _ = self.export()
        self.assertEqual(cfg["visibility"], 80000)
        self.m.weather.enable_fog = True
        self.m.weather.fog_thickness = 200
        self.m.weather.fog_visibility = 1200
        cfg, _ = self.export()
        self.assertEqual(cfg["visibility"], 1200)
        self.m.weather.auto_fog = True
        cfg, warnings = self.export()
        self.assertEqual(cfg["visibility"], 80000)
        self.assertTrue(any("automatic fog" in w for w in warnings))

    def test_explicit_biome_and_dust(self):
        with self.assertRaises(ValueError):
            ENV.export_environment(self.m, self.theater, default_cover="unknown")
        self.m.weather.enable_dust = True
        self.m.weather.dust_density = 2500
        self.assertEqual(self.export()[0]["visibility"], 2500)


if __name__ == "__main__":
    unittest.main()
