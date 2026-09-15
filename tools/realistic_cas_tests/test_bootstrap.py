"""Exporter -> Lua entry point -> real plugin modules, with DCS doubles only."""

import unittest

import test_sensors
from test_contact_core import PLUGIN
from test_registry_export import EXPORT


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        test_sensors.BridgeTests.setUp(self)
        self.rt.execute((PLUGIN / "bootstrap.lua").read_text(encoding="utf-8"))
        self.rt.execute("""
        assert(fog:stop());run(3)
        world.event.S_EVENT_MISSION_END=12
        cfg={enabled=true,registry={schemaVersion=1,
          groups={{name='red',originalInvisible=false}},targets=config.targets,
          observers=config.observers,knownAirDefenseGroups={},warnings={}},
          acquisitionSeconds=20,ttl=600,environment={defaultCover='desert',
          startTime=43200,sunrise=21600,sunset=64800,weather=1,visibility=30000}}
        """)

    def check(self, script):
        self.rt.execute(script)

    def test_explicit_start_acquire_and_stop_restore(self):
        self.check("""
        m=assert(RealisticCAS.startMission(cfg));assert(red.hidden and m.active)
        assert(not RealisticCAS.startMission(cfg))
        run(100);assert(not red.hidden and m.fog.service:isRevealed(1,2))
        assert(m:stop());run(5)
        assert(not m.active and not RealisticCAS._running and not RealisticCAS.mission)
        assert(#pending==0)
        """)

    def test_invalid_sensor_rolls_back_already_hidden_groups(self):
        self.check("""
        cfg.registry.observers[1].typeName=nil
        local m,why=RealisticCAS.startMission(cfg)
        assert(not m and why:find('type required'))
        run(3);assert(not red.hidden and not RealisticCAS._running)
        assert(not RealisticCAS.mission and #pending==0)
        """)

    def test_sam_overlap_and_bad_environment_rejected_before_hide(self):
        self.check("""
        local before=#commands
        cfg.registry.knownAirDefenseGroups={{name='red'}}
        assert(not pcall(RealisticCAS.startMission,cfg))
        cfg.registry.knownAirDefenseGroups={};cfg.environment.defaultCover=nil
        assert(not pcall(RealisticCAS.startMission,cfg))
        assert(#commands==before and not RealisticCAS.mission)
        """)

    def test_disabled_no_callbacks_and_mission_end_cleanup(self):
        self.check("""
        local n=#pending;local c=#commands
        assert(not RealisticCAS.startMission({enabled=false}))
        assert(#pending==n and #commands==c)
        m=assert(RealisticCAS.startMission(cfg))
        for h in pairs(handlers)do h:onEvent({id=12})end
        run(5)
        assert(not red.hidden and not RealisticCAS.mission and #pending==0)
        """)

    def test_failed_restoration_keeps_recovery_handle(self):
        self.check("""
        m=assert(RealisticCAS.startMission(cfg));red.fail=true
        assert(not m:stop() and RealisticCAS.mission==m)
        assert(not m.detectors:getDiagnostics().enabled)
        red.fail=false;assert(m:stop());run(5)
        assert(not red.hidden and not RealisticCAS.mission and #pending==0)
        """)

    def test_exported_startup_compiles_and_executes(self):
        cfg = {
            "enabled": True,
            "registry": {
                "schemaVersion": 1,
                "groups": [{"name": "red", "originalInvisible": False}],
                "targets": [{"name": "target", "groupName": "red"}],
                "observers": [
                    {
                        "name": "observer",
                        "typeName": "FA-18C_hornet",
                        "category": "air",
                        "role": "CAS",
                    }
                ],
                "knownAirDefenseGroups": [],
                "warnings": [],
            },
            "acquisitionSeconds": 20,
            "environment": {
                "defaultCover": "desert",
                "startTime": 43200,
                "sunrise": 21600,
                "sunset": 64800,
                "weather": 1,
                "visibility": 30000,
            },
        }
        script = EXPORT.render_startup(cfg)
        self.rt.compile(script)
        self.rt.execute(script)
        self.check(
            "assert(RealisticCAS.mission.active);assert(RealisticCAS.mission:stop())"
        )
        self.assertIsNone(EXPORT.render_startup({"enabled": False}))
        for seconds in (0, -1, True, float("nan"), 601):
            with self.assertRaises(ValueError):
                EXPORT.render_startup({**cfg, "acquisitionSeconds": seconds})

    def test_each_lua_and_declared_bundle_compile(self):
        sources = [
            (PLUGIN / n).read_text(encoding="utf-8") for n in EXPORT.SCRIPT_ORDER
        ]
        for source in sources:
            self.rt.compile(source)
        self.rt.compile("\n".join(sources))


if __name__ == "__main__":
    unittest.main()
