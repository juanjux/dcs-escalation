"""Configurable fixed power feeds retain their wiring after supply losses."""

import json
from pathlib import Path
import pickle
from types import SimpleNamespace
from typing import Any

import pytest

from game.plugins.luaplugin import LuaPlugin
from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, SkynetNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.topology import power_source_count
from game.theater.player import Player
from tests.missiongenerator.test_gpsjamming_power_runtime import (
    plant_object,
    runtime as gps_runtime,
    world as gps_world,
)
from tests.missiongenerator.test_iads_topology_runtime import (
    exported,
    start,
    vm,  # noqa: F401
)
from tests.test_iads_automatic_topology import site

OPTION = "skynetiads.powerSourceCount"
PLUGIN = Path("resources/plugins/skynetiads/plugin.json")


def settings_for(count: Any) -> Settings:
    settings = Settings()
    settings.set_plugin_option(OPTION, count)
    return settings


def feeds(network: IadsNetwork, obj: Any) -> set[Any]:
    node = network.node_for_tgo(obj)
    assert node is not None
    return {
        group.ground_object
        for group in node.connections.values()
        if group.iads_role is IadsRole.POWER_SOURCE
    }


def consumer(
    name: str, role: IadsRole, settings: Settings, *, gps: bool = False
) -> Any:
    obj = site(name, role, settings=settings)
    if gps:
        obj.groups[0].units[0].ground_unit_variant = "GPS Jammer (Red)"
        assert obj.carries_gps_jammer
    return obj


@pytest.mark.parametrize("settings", [None, Settings(), object()])
def test_missing_settings_and_older_saves_use_two_fixed_supplies(settings: Any) -> None:
    assert power_source_count(settings) == 2


@pytest.mark.parametrize(
    "value",
    [None, True, False, "many", [], {}, 1.5, float("nan"), float("inf"), -float("inf")],
)
def test_unreadable_or_nonintegral_counts_use_the_default(value: Any) -> None:
    assert power_source_count(settings_for(value)) == 2


@pytest.mark.parametrize("error", [AttributeError, KeyError, TypeError, ValueError])
def test_unreadable_saved_option_does_not_break_topology(
    error: type[Exception],
) -> None:
    def unreadable(_identifier: str, _default: Any) -> Any:
        raise error("old or malformed settings")

    assert power_source_count(SimpleNamespace(plugin_option_or=unreadable)) == 2


@pytest.mark.parametrize(
    "value,expected",
    [
        (-10, 1),
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 3),
        (3.0, 3),
        (10000, 10000),
        (10001, 10000),
    ],
)
def test_integral_counts_are_clamped_to_the_setting_bounds(
    value: Any, expected: int
) -> None:
    assert power_source_count(settings_for(value)) == expected


@pytest.mark.parametrize("count", [1, 2, 3, 5, 10000])
@pytest.mark.parametrize(
    "role,gps",
    [
        (IadsRole.SAM, False),
        (IadsRole.EWR, False),
        (IadsRole.COMMAND_CENTER, False),
        (IadsRole.CONNECTION_NODE, False),
        (IadsRole.EWR, True),
    ],
)
def test_all_land_consumers_use_the_configured_number_of_available_friendly_feeds(
    count: int, role: IadsRole, gps: bool
) -> None:
    settings = settings_for(count)
    obj = consumer("CONSUMER", role, settings, gps=gps)
    plants = [
        site(f"POWER {i}", IadsRole.POWER_SOURCE, i * 100, settings=settings)
        for i in (1, 2, 3)
    ]
    enemy = site("ENEMY", IadsRole.POWER_SOURCE, 1, Player.BLUE, settings)
    outside = site("OUTSIDE", IadsRole.POWER_SOURCE, 100_000, settings=settings)
    network = IadsNetwork(True)
    network.initialize_network(iter([obj, *plants, enemy, outside]))
    assert feeds(network, obj) == set(plants[:count])
    assert all(not feeds(network, plant) for plant in plants)


def test_each_consumer_reads_its_own_settings_not_the_power_stations_settings() -> None:
    configurations: list[tuple[str, IadsRole, int, bool]] = [
        ("SAM", IadsRole.SAM, 1, False),
        ("EWR", IadsRole.EWR, 2, False),
        ("COMMAND", IadsRole.COMMAND_CENTER, 3, False),
        ("COMMS", IadsRole.CONNECTION_NODE, 4, False),
        ("GPS", IadsRole.EWR, 10000, True),
    ]
    consumers = [
        consumer(name, role, settings_for(count), gps=gps)
        for name, role, count, gps in configurations
    ]
    plants = [
        site(f"POWER {i}", IadsRole.POWER_SOURCE, i * 100, settings=settings_for(1))
        for i in range(1, 6)
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter([*consumers, *plants]))
    for obj, (_, _, count, _) in zip(consumers, configurations):
        assert feeds(network, obj) == set(plants[:count])


@pytest.mark.parametrize("count", [1, 2, 3])
def test_damage_never_substitutes_an_unwired_available_station(count: int) -> None:
    settings = settings_for(count)
    sam = consumer("SAM", IadsRole.SAM, settings)
    plants = [
        site(f"POWER {i}", IadsRole.POWER_SOURCE, i * 100, settings=settings)
        for i in range(1, count + 2)
    ]
    for plant in plants[:count]:
        plant.groups[0].units[0].alive = False
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, *plants]))
    node = network.node_for_tgo(sam)
    assert node is not None
    assert plants[-1].groups[0].units[0].alive
    assert feeds(network, sam) == set(plants[:count])
    assert not IadsConnectivity(network).powered(node)
    network.initialize_network(iter([*reversed(plants), sam]))
    node = network.node_for_tgo(sam)
    assert node is not None
    assert feeds(network, sam) == set(plants[:count])
    assert not IadsConnectivity(network).powered(node)
    plants[count - 1].groups[0].units[0].alive = True
    network.update_tgo(plants[count - 1], GameUpdateEvents())
    assert feeds(network, sam) == set(plants[:count])
    assert IadsConnectivity(network).powered(node)


def test_plugin_exposes_integer_default_bounds_and_persistent_setting() -> None:
    data = json.loads(PLUGIN.read_text(encoding="utf-8"))
    [manifest] = [
        row for row in data["specificOptions"] if row["mnemonic"] == "powerSourceCount"
    ]
    assert type(manifest["defaultValue"]) is int and manifest["defaultValue"] == 2
    assert manifest["minimumValue"] == 1 and manifest["maximumValue"] == 10000
    plugin = LuaPlugin.from_json("skynetiads", PLUGIN)
    assert plugin is not None
    [option] = [item for item in plugin.options if item.identifier == OPTION]
    settings = Settings()
    plugin.set_settings(settings)
    option.set_settings(settings)
    assert option.get_value == 2
    assert option.min == 1 and option.max == 10000
    option.set_value(3)
    restored = pickle.loads(pickle.dumps(settings))
    option.set_settings(restored)
    assert option.get_value == 3
    assert power_source_count(restored) == 3


def test_three_configured_fixed_feeds_reach_the_production_skynet_lua(vm: Any) -> None:
    settings = settings_for(3)
    sam = consumer("SAM", IadsRole.SAM, settings)
    command = consumer("COMMAND", IadsRole.COMMAND_CENTER, settings)
    plants = [
        site(f"POWER {i}", IadsRole.POWER_SOURCE, i * 100, settings=settings)
        for i in range(1, 5)
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, command, *plants]))
    start(vm, exported(network))
    sam_name = SkynetNode.dcs_name_for_group(sam.groups[0])
    element = vm.globals().elements[sam_name]
    assert element.hasWorkingPowerSource(element)
    for index, plant in enumerate(plants[:3]):
        name = SkynetNode.dcs_name_for_group(plant.groups[0])
        vm.globals().objects[name].live = False
        topology = vm.globals().iads.topology
        topology.beginCycle(topology)
        assert element.hasWorkingPowerSource(element) is (index < 2)
    fourth_name = SkynetNode.dcs_name_for_group(plants[3].groups[0])
    assert vm.globals().objects[fourth_name].live
    vm.globals().objects[SkynetNode.dcs_name_for_group(plants[2].groups[0])].live = True
    topology.beginCycle(topology)
    assert element.hasWorkingPowerSource(element)


def test_three_configured_fixed_feeds_reach_the_production_gps_lua() -> None:
    w = gps_world(skynet=False)
    w.game.settings.set_plugin_option(OPTION, 3)
    fourth = site("FOURTH POWER", IadsRole.POWER_SOURCE, 400, settings=w.game.settings)
    fourth.control_point.ground_objects = [fourth]
    w.game.theater.controlpoints.append(fourth.control_point)
    objects = [obj for cp in w.game.theater.controlpoints for obj in cp.ground_objects]
    w.game.theater.iads_network.initialize_network(iter(objects))
    lua = gps_runtime(w)
    assert len(lua.globals().dcsRetribution.gpsJamming.sites[1].power.sources) == 3
    for index, plant in enumerate(w.plants):
        plant_object(lua, plant).live = False
        assert lua.globals().gpsAlive() is (index < 2)
    assert plant_object(lua, fourth).live
    plant_object(lua, w.plants[2]).live = True
    assert lua.globals().gpsAlive()
