"""Generate native missions with IMAC enabled and disabled."""

import copy
import json
import pickle
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zipfile import ZipFile

import pytest
from dcs import Point
from dcs.lua import loads
from dcs.planes import F_16C_50
from dcs.statics import Fortification
from dcs.task import CAP, ControlledTask, OrbitAction
from dcs.vehicles import AirDefence

from game.ato import FlightType
from game.missiongenerator import imac
from game.missiongenerator.luagenerator import LuaGenerator
from game.plugins.luaplugin import LuaPlugin, LuaPluginDefinition
from game.settings import Settings
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.player import Player
from game.unitmap import UnitMap
from .test_barcap_refuelling import scenario as barcap_scenario


def scenario() -> Any:
    s = barcap_scenario()
    s.cap.package = object()
    s.cap.waypoints = []
    s.cap.units = s.group.units
    s.data.frontline_visibility_groups = set()
    s.nodes = [
        NS(
            iads_role=IadsRole.COMMAND_CENTER,
            dcs_name='CC "quoted"',
            player=Player.BLUE,
            connections={IadsRole.POWER_SOURCE.value: ["POWER"]},
        )
    ]
    s.game.theater = NS(iads_network=NS(skynet_nodes=lambda game: s.nodes))
    s.game.settings = Settings()
    s.unit_map = UnitMap()
    s.generator = LuaGenerator(s.game, s.mission, s.data, s.unit_map)
    return s


def test_disabled_is_inert_without_inspecting_the_mission() -> None:
    assert imac.options([]) is None
    assert imac.configure(object(), None) is None
    imac.inject(object(), None)


def test_manifest_is_opt_in_and_all_exported_defaults_match() -> None:
    definition = LuaPluginDefinition.from_json(
        "imac", Path("resources/plugins/imac/plugin.json")
    )
    assert definition.enabled_by_default is False
    assert {
        o.identifier.removeprefix("imac."): o.value for o in definition.options
    } == imac.DEFAULTS
    assert "imac" in json.loads(Path("resources/plugins/plugins.json").read_text())


def test_imac_side_and_debug_settings_survive_campaign_settings_round_trip() -> None:
    definition = LuaPluginDefinition.from_json(
        "imac", Path("resources/plugins/imac/plugin.json")
    )
    plugin = LuaPlugin(definition)
    settings = Settings()
    plugin.set_settings(settings)
    plugin.set_value(True)
    for option in plugin.options:
        option.set_settings(settings)
        if option.identifier in ("imac.blue", "imac.red", "imac.debug"):
            option.set_value(option.identifier != "imac.blue")
    restored = pickle.loads(pickle.dumps(settings))
    plugin.set_settings(restored)
    for option in plugin.options:
        option.set_settings(restored)
    options = imac.options([plugin])
    assert options is not None
    assert options["blue"] is False
    assert options["red"] is True
    assert options["debug"] is True
    assert restored.plugins["imac.blue"] is False
    assert restored.plugins["imac.red"] is True
    assert restored.plugins["imac.debug"] is True


@pytest.mark.parametrize(
    "key,value",
    [
        ("blue", 1),
        ("reports", "yes"),
        ("interval", 0),
        ("holdSeconds", float("nan")),
        ("pursuitSeconds", True),
    ],
)
def test_options_reject_invalid_values_before_modifying_routes(
    key: str, value: Any
) -> None:
    plugin = NS(
        identifier="imac",
        enabled=True,
        options=[NS(identifier="imac." + key, get_value=value)],
    )
    with pytest.raises(ValueError, match="IMAC"):
        imac.options([plugin])


def test_miz_embeds_runtime_in_dependency_order_and_native_route() -> None:
    s = scenario()
    before = copy.deepcopy(s.group.dict())
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    flight = data["flights"][0]
    assert flight["mode"] == "cap"
    assert flight["stationStart"] == 2
    assert flight["recoveryIndex"] == 3
    assert flight["endTime"] == 4000
    assert flight["route"][-1]["name"] == "LANDING"
    assert data["commandCenters"][0]["name"] == 'CC "quoted" object'
    assert data["commandCenters"][0]["power"] == ["POWER object"]
    for index, point in enumerate(s.group.points, 1):
        assert (
            point.tasks[0]
            .dict()["params"]["action"]["params"]["command"]
            .endswith(f", {index}) end")
        )
    # Original geometry and tasks, including the patrol deadline, are retained.
    for old, new in zip(
        before["route"]["points"].values(), s.group.dict()["route"]["points"].values()
    ):
        assert old["x"] == new["x"] and old["y"] == new["y"]
    imac.inject(s.generator, data)
    assert [t.comment for t in s.mission.triggerrules.triggers] == [
        "Load imac-geometry.lua",
        "Load imac-commander.lua",
        "Load imac-dcs.lua",
        "In-Mission Air Commander",
    ]


def test_serialized_miz_contains_every_runtime_dependency(tmp_path: Path) -> None:
    s = scenario()
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    imac.inject(s.generator, data)
    path = tmp_path / "imac.miz"
    s.mission.save(path)
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    with ZipFile(path) as archive:
        mission = loads(archive.read("mission").decode())["mission"]
        assert mission["trig"]
        script_names = [n for n in archive.namelist() if n.endswith(".lua")]
        assert len(script_names) >= 3
        for name in imac.SCRIPTS:
            raw = next(
                archive.read(n).decode("utf-8")
                for n in script_names
                if n.endswith(name)
            )
            assert lua.eval("loadstring")(raw) is not None
        startup = s.mission.triggerrules.triggers[-1].actions[0].text.id
        assert "EscalationIMAC.start" in startup
        assert lua.eval("loadstring")(startup) is not None


@pytest.mark.parametrize(
    "role",
    [
        FlightType.BARCAP,
        FlightType.STRIKE,
        FlightType.AEWC,
        FlightType.AFAC_AREA,
        FlightType.ESCORT,
    ],
)
def test_human_or_mixed_group_is_only_an_asset_never_receives_route_hooks(
    role: FlightType,
) -> None:
    s = scenario()
    s.cap.flight_type = role
    s.cap.client_units = [object()]
    before = copy.deepcopy(s.group.dict())
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    assert data["flights"][0]["mode"] == "observe"
    assert data["flights"][0]["awacs"] is (role == FlightType.AEWC)
    assert s.group.dict() == before


def test_missing_orbit_window_and_afac_routes_are_not_claimed() -> None:
    s = scenario()
    s.group.points[1].tasks.clear()
    before = copy.deepcopy(s.group.dict())
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None and data["flights"][0]["mode"] == "observe"
    assert s.group.dict() == before


def test_red_ownership_comes_from_native_coalition_not_a_boolean_hint() -> None:
    s = scenario()
    group = s.mission.flight_group_inflight(
        s.mission.country("Russia"),
        "RED CAP",
        F_16C_50,
        Point(0, 0, s.mission.terrain),
        6000,
        500,
        CAP,
    )
    point = group.add_waypoint(
        Point(10000, 0, s.mission.terrain), 6000, 500, "RACETRACK START"
    )
    orbit = ControlledTask(OrbitAction(altitude=6000, speed=500))
    orbit.stop_after_time(4000)
    point.tasks.append(orbit)
    group.add_waypoint(Point(20000, 0, s.mission.terrain), 6000, 500, "RACETRACK END")
    clone = copy.copy(s.cap)
    clone.group_name = group.name
    clone.units = group.units
    s.data.flights.append(clone)
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    assert next(f for f in data["flights"] if f["group"] == "RED CAP")["side"] == 1


def test_late_bound_carrier_recovery_links_survive_the_export() -> None:
    s = scenario()
    s.group.points[-1].type = "Land"
    s.group.points[-1].helipad_id = 744
    s.group.points[-1].link_unit = 744
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    landing = data["flights"][0]["route"][-1]
    assert landing["helipadId"] == 744
    assert landing["linkUnit"] == 744


def test_native_ground_sensors_and_exact_launcher_radar_pairs() -> None:
    s = scenario()
    country = s.mission.country("Russia")
    launcher = s.mission.vehicle_group(
        country, "PATRIOT", AirDefence.Patriot_ln, Point(20000, 0, s.mission.terrain)
    )
    wrong = s.mission.vehicle("WRONG RADAR", AirDefence.Hawk_tr)
    wrong.position = launcher.units[0].position
    launcher.add_unit(wrong)
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    sam = next(t for t in data["threats"] if t["name"] == launcher.units[0].name)
    assert sam["needsRadar"] is True and sam["radars"] == []
    assert any(r["name"] == wrong.name for r in data["sensors"])
    correct = s.mission.vehicle("CORRECT RADAR", AirDefence.Patriot_str)
    correct.position = launcher.units[0].position
    launcher.add_unit(correct)
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    sam = next(t for t in data["threats"] if t["name"] == launcher.units[0].name)
    assert sam["radars"] == [correct.name]


def test_standalone_command_centre_does_not_require_advanced_iads_or_skynet() -> None:
    s = scenario()
    s.nodes.clear()
    group = s.mission.static_group(
        s.mission.country("USA"),
        "BASIC CC",
        Fortification._Command_Center,
        Point(0, 0, s.mission.terrain),
    )
    native = group.units[0]
    objective = NS(
        category="commandcenter", is_friendly=lambda p: p is Player.BLUE, groups=[]
    )
    unit = NS(unit_type=None, ground_object=objective, alive=True, unit_name="BASIC CC")
    objective.groups = [NS(iads_role=IadsRole.COMMAND_CENTER, units=[unit])]
    s.unit_map.theater_objects[native.name] = NS(
        theater_unit=unit,
        dcs_unit=native,
    )
    support = s.mission.static_group(
        s.mission.country("USA"),
        "SUPPORT",
        Fortification.GeneratorF,
        Point(100, 0, s.mission.terrain),
    ).units[0]
    s.unit_map.theater_objects[support.name] = NS(
        theater_unit=NS(unit_type=None, ground_object=objective), dcs_unit=support
    )
    data = imac.configure(s.generator, dict(imac.DEFAULTS))
    assert data is not None
    assert data["commandCenters"] == [
        {"name": "BASIC CC object", "key": "BASIC CC", "side": 2, "power": []}
    ]
