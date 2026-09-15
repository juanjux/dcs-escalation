"""Read-only final-pydcs registry contract, without loading the campaign UI."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from dcs import Mission
from dcs.countries import CombinedJointTaskForcesBlue, CombinedJointTaskForcesRed
from dcs.mapping import Point
from dcs.planes import FA_18C_hornet
from dcs.task import SetInvisibleCommand
from dcs.unit import Skill
from dcs.vehicles import Unarmed
from lupa.lua51 import LuaRuntime

SOURCE = (
    Path(__file__).resolve().parents[2] / "game/missiongenerator/realisticcasluadata.py"
)
SPEC = importlib.util.spec_from_file_location("rcas_registry", SOURCE)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        # Use only the explicitly supplied stores, not unrelated installed mod presets.
        FA_18C_hornet.payloads = {}
        self.m = Mission()
        self.m.coalition["blue"].add_country(CombinedJointTaskForcesBlue())
        self.m.coalition["red"].add_country(CombinedJointTaskForcesRed())
        red = self.m.country("Combined Joint Task Forces Red")
        blue = self.m.country("Combined Joint Task Forces Blue")
        p = Point(0, 0, self.m.terrain)
        self.g = self.m.vehicle_group(red, "GROUND", Unarmed.Ural_375, p, group_size=2)
        self.air = self.m.flight_group(
            blue,
            "MISLEADING BARCAP",
            FA_18C_hornet,
            airport=None,
            position=p,
            altitude=4000,
            group_size=2,
        )
        self.air.units[0].pylons = {4: {"CLSID": "{AN_ASQ_228}"}}
        self.air.units[1].pylons = {4: {"CLSID": "{ALQ_164_RF_Jammer}"}}
        self.data = NS(
            tic_groups=[],
            jtacs=[],
            flights=[NS(flight_type=NS(value="BAI"), units=self.air.units)],
        )

    def collect(self, **kwargs):
        kwargs.setdefault("unit_map", NS(theater_objects={}))
        return EXPORT.collect_registry(self.m, self.data, enabled=True, **kwargs)

    def test_unit_map_required_to_protect_campaign_sam_sites(self):
        with self.assertRaisesRegex(ValueError, "requires UnitMap"):
            self.collect(unit_map=None)

    def test_campaign_sam_excluded_but_identical_frontline_sam_hidden(self):
        # Same vehicle type, different campaign membership. Support members in
        # the SAM's DCS group must not be hidden separately either.
        red = self.m.country("Combined Joint Task Forces Red")
        front = self.m.vehicle_group(
            red, "FRONT", Unarmed.Ural_375, Point(4000, 0, self.m.terrain)
        )
        self.g.units[0].type = "Strela-10M3"
        front.units[0].type = "Strela-10M3"
        mapping = NS(
            theater_objects={
                self.g.units[0].name: NS(
                    theater_unit=NS(ground_object=NS(category="aa", name="QUAGGA"))
                )
            }
        )
        r = self.collect(unit_map=mapping)
        self.assertEqual([g["name"] for g in r["knownAirDefenseGroups"]], ["GROUND"])
        self.assertEqual([g["name"] for g in r["groups"]], ["FRONT"])
        self.assertEqual([t["name"] for t in r["targets"]], [front.units[0].name])
        # Being excluded from concealment does not disable their ordinary observation.
        self.assertIn(self.g.units[0].name, {o["name"] for o in r["observers"]})

    def test_bai_ground_object_is_not_exempt_for_having_a_known_position(self):
        mapping = NS(
            theater_objects={
                self.g.units[0].name: NS(
                    theater_unit=NS(ground_object=NS(category="armor", name="PLATYPUS"))
                )
            }
        )
        r = self.collect(unit_map=mapping)
        self.assertEqual(len(r["targets"]), 2)
        self.assertEqual(r["knownAirDefenseGroups"], [])

    def test_disabled_has_no_reads_or_effects(self):
        self.assertIsNone(EXPORT.collect_registry(None, None, enabled=False))

    def test_real_pydcs_names_roles_and_per_unit_payloads(self):
        before = [u.dict() for u in self.air.units + self.g.units]
        r = self.collect()
        self.assertEqual(len(r["groups"]), 1)
        self.assertEqual(len(r["targets"]), 2)
        air = [o for o in r["observers"] if o["category"] == "air"]
        self.assertEqual({o["role"] for o in air}, {"BAI"})
        self.assertEqual([o["equipment"]["targetingPod"] for o in air], [True, False])
        self.assertEqual([u.dict() for u in self.air.units + self.g.units], before)

    def test_explicit_and_waypoint_ownership_preserved(self):
        self.assertEqual(self.collect(excluded_groups=["GROUND"])["targets"], [])
        self.g.points[0].tasks.append(SetInvisibleCommand(False))
        r = self.collect()
        self.assertEqual(r["targets"], [])
        self.assertEqual(len(r["warnings"]), 1)

    def test_blue_ground_and_red_air_use_real_coalition(self):
        red = self.m.country("Combined Joint Task Forces Red")
        blue = self.m.country("Combined Joint Task Forces Blue")
        blue.vehicle_group.append(self.g)
        red.vehicle_group.remove(self.g)
        red.plane_group.append(self.air)
        blue.plane_group.remove(self.air)
        r = self.collect()
        self.assertEqual(r["groups"][0]["coalition"], 2)
        self.assertEqual(
            {o["coalition"] for o in r["observers"] if o["category"] == "air"}, {1}
        )

    def test_tic_rejected_until_adapter_exists(self):
        self.data.tic_groups = ["GROUND"]
        with self.assertRaisesRegex(ValueError, "TIC"):
            self.collect()

    def test_mixed_flight_excludes_only_human_observer(self):
        self.air.units[0].skill = Skill.Client
        r = self.collect()
        names = {o["name"] for o in r["observers"]}
        self.assertNotIn(self.air.units[0].name, names)
        self.assertIn(self.air.units[1].name, names)

    def test_jtac_exact_name_and_unknown_air_omitted(self):
        self.data.flights = []
        self.data.jtacs = [NS(unit_name=self.air.units[0].name)]
        air = [o for o in self.collect()["observers"] if o["category"] == "air"]
        self.assertEqual(len(air), 1)
        self.assertEqual(air[0]["role"], "JTAC")

    def test_duplicate_unit_fails_before_lua_emission(self):
        self.g.units[1].name = self.g.units[0].name
        with self.assertRaisesRegex(ValueError, "duplicate DCS unit"):
            self.collect()

    def test_typed_lua_round_trip_and_control_chars(self):
        rt = LuaRuntime()
        record = self.collect()
        record["odd"] = 'quoted" slash\\ newline\n nul\0' + "123\tñ"
        result = rt.execute("return " + EXPORT.lua_literal(record))
        self.assertEqual(result["odd"], record["odd"])
        self.assertIs(result["groups"][1]["originalInvisible"], False)
        self.assertEqual(result["schemaVersion"], 1)
        with self.assertRaises(ValueError):
            EXPORT.lua_literal(float("nan"))
        with self.assertRaises(TypeError):
            EXPORT.lua_literal(object())


if __name__ == "__main__":
    unittest.main()
