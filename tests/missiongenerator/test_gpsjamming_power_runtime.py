"""GPS jammers use their fixed physical supplies, independently of radio links."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from game.dcs.groundunittype import GroundUnitType
from game.gpsjamming import gps_jammer_sites
from game.missiongenerator.gpsjammingluadata import populate_gps_jamming_lua
from game.missiongenerator.luagenerator import LuaData
from game.missiongenerator.missiondata import MissionData
from game.settings import Settings
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.player import Player
from game.theater.theatergroup import SceneryUnit
from tests.test_iads_automatic_topology import site

SCRIPT = Path("resources/plugins/gpsjamming/gpsjamming-config.lua")


def world(
    side: Player = Player.RED, *, skynet: bool = True, advanced: bool = True
) -> Any:
    settings = Settings()
    settings.gps_jamming_enabled = True
    settings.set_plugin_option("skynetiads", skynet)
    jammer = site("JAMMER", IadsRole.EWR, side=side, settings=settings)
    variant = GroundUnitType.named(
        "GPS Jammer (Red)" if side.is_red else "GPS Jammer (Blue)"
    )
    jammer.groups[0].units[0].type = variant.dcs_unit_type
    jammer.groups[0].units[0].ground_unit_variant = variant.variant_id
    plants = [
        site(f"POWER {i}", IadsRole.POWER_SOURCE, i * 100, side, settings)
        for i in (1, 2, 3)
    ]
    enemy = site("ENEMY POWER", IadsRole.POWER_SOURCE, 1, side.opponent, settings)
    comms = site("COMMS", IadsRole.CONNECTION_NODE, side=side, settings=settings)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, side=side, settings=settings)
    objects = [jammer, *plants, enemy, comms, command]
    network = IadsNetwork(advanced)
    network.initialize_network(iter(objects))
    for obj in objects:
        obj.control_point.ground_objects = [obj]
    game: Any = SimpleNamespace(
        settings=settings,
        theater=SimpleNamespace(
            controlpoints=[obj.control_point for obj in objects], iads_network=network
        ),
    )
    return SimpleNamespace(
        game=game,
        jammer=jammer,
        plants=plants,
        enemy=enemy,
        comms=comms,
        command=command,
    )


def config(world: Any) -> str:
    root = LuaData("dcsRetribution")
    populate_gps_jamming_lua(root, world.game, MissionData())
    return root.serialize()


def runtime(world: Any, *, legacy: bool = False) -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    lua.execute("""
        objects={}; statics={}; handler=nil
        coalition={side={RED=1,BLUE=2}}
        env={info=function() end}
        world={addEventHandler=function(h) handler=h end}
        Unit={getByName=function(name) return objects[name] end}
        StaticObject={getByName=function(name) return statics[name] end}
        function add(kind,name,side,live)
            local obj={live=live,side=side}
            function obj:isExist() return self.live end
            function obj:getLife() return self.live and 100 or 0 end
            function obj:getCoalition() return self.side end
            if kind=='static' then statics[name]=obj else objects[name]=obj end
        end
    """)
    lua.execute(config(world))
    if legacy:
        lua.execute("dcsRetribution.gpsJamming.sites[1].power=nil")
    for cp in world.game.theater.controlpoints:
        for obj in cp.ground_objects:
            for unit in obj.units:
                if isinstance(unit, SceneryUnit):
                    continue
                kind = "static" if unit.is_static else "unit"
                name = unit.unit_name + " object" if unit.is_static else unit.unit_name
                lua.globals().add(
                    kind, name, 2 if cp.captured.is_blue else 1, unit.alive
                )
    # The test hooks close over the production plugin's private functions.
    lua.execute(
        SCRIPT.read_text(encoding="utf-8")
        + "\nfunction gpsAlive() return siteAlive(sites[1]) end"
        + "\nfunction gpsAt(side) return jammingAt({x=0,z=0},side) ~= nil end"
    )
    return lua


def plant_object(lua: Any, plant: Any, index: int = 0) -> Any:
    return lua.globals().statics[plant.groups[0].units[index].unit_name + " object"]


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("skynet", [False, True])
def test_two_fixed_supplies_work_without_comms_or_command_and_never_use_a_third(
    side: Player, skynet: bool
) -> None:
    w = world(side, skynet=skynet)
    lua = runtime(w)
    row = lua.globals().dcsRetribution.gpsJamming.sites[1]
    assert row.power.required
    assert {ref.name for ref in row.power.sources.values()} == {
        plant.groups[0].units[0].unit_name + " object" for plant in w.plants[:2]
    }
    assert lua.globals().gpsAlive()
    assert lua.globals().gpsAt(1 if side.is_blue else 2)
    assert not lua.globals().gpsAt(2 if side.is_blue else 1)
    plant_object(lua, w.comms).live = False
    plant_object(lua, w.command).live = False
    assert lua.globals().gpsAlive()
    plant_object(lua, w.plants[0]).live = False
    assert lua.globals().gpsAlive()
    plant_object(lua, w.plants[1]).live = False
    assert plant_object(lua, w.plants[2]).live
    assert plant_object(lua, w.enemy).live
    assert not lua.globals().gpsAlive()
    assert not lua.globals().gpsAt(1 if side.is_blue else 2)
    plant_object(lua, w.plants[0]).live = True
    assert lua.globals().gpsAlive()
    lua.globals().objects[w.jammer.groups[0].units[0].unit_name].live = False
    assert not lua.globals().gpsAlive()


@pytest.mark.parametrize("skynet", [False, True])
def test_initially_unpowered_live_jammer_is_exported_and_can_restart_after_repair(
    skynet: bool,
) -> None:
    w = world(skynet=skynet)
    for plant in w.plants[:2]:
        plant.groups[0].units[0].alive = False
    w.game.theater.iads_network.invalidate_state_map()
    if skynet:
        assert not gps_jammer_sites(w.game)
    assert [s.name for s in gps_jammer_sites(w.game, include_unpowered=True)] == [
        "JAMMER"
    ]
    lua = runtime(w)
    assert not lua.globals().gpsAlive()
    plant_object(lua, w.plants[1]).live = True
    assert lua.globals().gpsAlive()


def test_all_members_of_a_selected_power_station_are_live_supply_references() -> None:
    w = world()
    group = w.plants[0].groups[0]
    group.units.append(replace(group.units[0], id=2, name="POWER second building"))
    group.units[0].alive = False
    w.plants[1].groups[0].units[0].alive = False
    lua = runtime(w)
    assert lua.globals().gpsAlive()
    plant_object(lua, w.plants[0], 1).live = False
    assert not lua.globals().gpsAlive()


def test_an_organic_generator_supplies_the_jammer_and_remains_attackable() -> None:
    w = world(skynet=False)
    generator = GroundUnitType.named("SAM Patriot EPP-III")
    unit = replace(
        w.jammer.groups[0].units[0],
        id=2,
        name="GENERATOR",
        type=generator.dcs_unit_type,
        ground_unit_variant=generator.variant_id,
    )
    w.jammer.groups[0].units.append(unit)
    for plant in w.plants[:2]:
        plant.groups[0].units[0].alive = False
    lua = runtime(w)
    assert lua.globals().gpsAlive()
    lua.globals().objects[unit.unit_name].live = False
    assert not lua.globals().gpsAlive()
    lua.globals().objects[unit.unit_name].live = True
    assert lua.globals().gpsAlive()


def test_captured_or_missing_supply_objects_cannot_power_the_enemy_jammer() -> None:
    w = world()
    lua = runtime(w)
    plant_object(lua, w.plants[0]).side = 2
    plant_object(lua, w.plants[1]).side = 2
    assert not lua.globals().gpsAlive()
    lua.globals().statics[w.plants[0].groups[0].units[0].unit_name + " object"] = None
    assert not lua.globals().gpsAlive()


def test_enemy_power_connection_is_not_exported_as_a_physical_supply() -> None:
    w = world()
    node = w.game.theater.iads_network.node_for_tgo(w.jammer)
    node.connections.clear()
    node.add_connection_for_group(w.enemy.groups[0])
    lua = runtime(w)
    assert not list(
        lua.globals().dcsRetribution.gpsJamming.sites[1].power.sources.values()
    )
    assert not lua.globals().gpsAlive()


@pytest.mark.parametrize("advanced,legacy", [(False, False), (True, True)])
def test_basic_iads_and_old_metadata_keep_their_independent_power_behavior(
    advanced: bool, legacy: bool
) -> None:
    w = world(advanced=advanced)
    lua = runtime(w, legacy=legacy)
    for plant in w.plants:
        plant_object(lua, plant).live = False
    assert lua.globals().dcsRetribution.gpsJamming.sites[1].power is None
    assert lua.globals().gpsAlive()


def test_advanced_jammer_without_any_fixed_supply_fails_closed() -> None:
    w = world(skynet=False)
    node = w.game.theater.iads_network.node_for_tgo(w.jammer)
    node.connections.clear()
    lua = runtime(w)
    assert lua.globals().dcsRetribution.gpsJamming.sites[1].power.required
    assert not lua.globals().gpsAlive()


def test_scenery_power_is_checked_without_skynet_static_standins() -> None:
    w = world(skynet=False)
    group = w.plants[0].groups[0]
    original = group.units[0]
    group.units[0] = SceneryUnit(
        original.id,
        "MAP POWER",
        original.type,
        original.position,
        original.ground_object,
    )
    w.plants[1].groups[0].units[0].alive = False
    lua = runtime(w)
    assert (
        not lua.globals().gpsAlive()
    )  # The generated scenery table is not loaded yet.
    lua.execute('ESCALATION_SCENERY_ZONES={{name="MAP POWER",dead=false}}')
    assert lua.globals().gpsAlive()
    lua.execute('scenery_zone_reported={["MAP POWER"]=true}')
    assert not lua.globals().gpsAlive()
