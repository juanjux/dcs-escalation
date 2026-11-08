"""Relocating SAM and radar sites rejoin local IADS infrastructure on deployment."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from game.groundmovement.dispatch import advance_armor, stop_armor
from game.groundmovement.orders import GroundPosition
from game.groundmovement.planning import armor_movement_options, preview_armor_movement
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, SkynetNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from tests.test_armor_movement_planning import world  # noqa: F401
from tests.test_iads_automatic_topology import links, site
from tests.test_sam_movement import RBS98, make_site, move, selected


def infrastructure(
    world: Any,
    name: str,
    role: IadsRole,
    point: GroundPosition,
    side: Player = Player.BLUE,
) -> Any:
    obj = site(name, role, point.x, side, world.game.settings)
    obj.control_point = world.a if side is Player.BLUE else world.enemy
    obj.position._terrain = world.game.theater.terrain
    obj.position.y = point.z
    for group in obj.groups:
        group.position._terrain = world.game.theater.terrain
        group.position.y = point.z
        for unit in group.units:
            unit.position._terrain = world.game.theater.terrain
            unit.position.y = point.z
    obj.control_point.connected_objectives.append(obj)
    world.game.db.tgos.add(obj.id, obj)
    return obj


def sectors(
    world: Any,
    deployed: GroundPosition,
    *,
    missing: str | None = None,
) -> Any:
    # One-mile coverage and feeds near its opposite boundaries let the small
    # movement fixture cross between separate sectors without changing its roads.
    for option in ("commsRangeNm", "powerRangeNm"):
        world.game.settings.set_plugin_option(f"skynetiads.{option}", 1)
    old_position = GroundPosition(world.sam.position.x - 1842, world.sam.position.y)
    new_position = GroundPosition(deployed.x + 1842, deployed.z)
    roles = {
        "power": IadsRole.POWER_SOURCE,
        "comms": IadsRole.CONNECTION_NODE,
        "command": IadsRole.COMMAND_CENTER,
        "ewr": IadsRole.EWR,
    }
    old = {
        kind: infrastructure(world, f"OLD {kind}", role, old_position)
        for kind, role in roles.items()
    }
    new = {
        kind: infrastructure(world, f"NEW {kind}", role, new_position)
        for kind, role in roles.items()
        if kind != missing and not (missing == "radio" and kind in ("comms", "command"))
    }
    enemy = [
        infrastructure(world, f"ENEMY {kind}", role, deployed, Player.RED)
        for kind, role in roles.items()
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter([world.sam, *old.values(), *new.values(), *enemy]))
    world.game.theater.iads_network = network
    return old, new, enemy


def exported_site(world: Any) -> SkynetNode | None:
    name = SkynetNode.dcs_name_for_group(world.sam.groups[0])
    return next(
        (
            node
            for node in world.game.theater.iads_network.skynet_nodes(world.game)
            if node.dcs_name == name
        ),
        None,
    )


@pytest.mark.parametrize("radar", [False, True])
@pytest.mark.parametrize("explicit_stop", [False, True])
def test_arrival_and_explicit_stop_reconnect_to_the_new_friendly_sector(
    world: Any, radar: bool, explicit_stop: bool
) -> None:
    sam = make_site(world, radar=radar)
    with patch("game.groundmovement.planning.distance_per_turn", return_value=40):
        preview = preview_armor_movement(
            world.game, sam.id, Player.BLUE, selected(world), world.destination
        )
    deployed = preview.first_turn_stop if explicit_stop else world.destination.position
    old, new, enemy = sectors(world, deployed)
    network = world.game.theater.iads_network
    assert old["power"] in links(network, sam)
    assert links(network, sam).isdisjoint(new.values())
    assert network.state_map.status_for(sam).state is IadsState.NETWORKED
    old_connections = set(network.node_for_tgo(sam).connections)
    transit = move(world)
    assert sam.in_transit
    assert not links(network, sam)
    assert network.state_map.status_for(sam).state is IadsState.DARK
    assert exported_site(world) is None

    world.game.turn += 1
    events = GameUpdateEvents()
    if explicit_stop:
        with patch("game.groundmovement.dispatch.distance_per_turn", return_value=40):
            advance_armor(world.game, events)
        assert not transit.finished and sam.in_transit
        assert GroundPosition(sam.position.x, sam.position.y) == deployed
        assert exported_site(world) is None
        assert network.state_map.status_for(sam).state is IadsState.DARK
        stop_armor(world.game, transit.order_id, Player.BLUE, events)
    else:
        advance_armor(world.game, events)

    assert transit.finished and not sam.in_transit
    assert GroundPosition(sam.position.x, sam.position.y) == deployed
    current = links(network, sam)
    assert new["power"] in current
    assert current & {new["comms"], new["command"]}
    assert current.isdisjoint([*old.values(), *enemy])
    assert old_connections.isdisjoint(network.node_for_tgo(sam).connections)
    state_map = network.state_map
    node = network.node_for_tgo(sam)
    assert state_map.status_for(sam).state is IadsState.NETWORKED
    assert state_map.connectivity.powered(node)
    assert state_map.connectivity.connected(node)
    assert {
        centre.group.ground_object
        for centre in state_map.connectivity.centres_for(node)
    } == {new["command"]}
    exported = exported_site(world)
    assert exported is not None and exported.requires_power
    assert exported.connections["PowerSource"] == [
        SkynetNode.dcs_name_for_group(new["power"].groups[0])
    ]
    assert {name for names in exported.connections.values() for name in names} == {
        SkynetNode.dcs_name_for_group(obj.groups[0]) for obj in current
    }


@pytest.mark.parametrize("radar", [False, True])
@pytest.mark.parametrize(
    "missing,expected",
    [("power", IadsState.DARK), ("radio", IadsState.AUTONOMOUS)],
)
def test_redeployment_does_not_keep_old_or_enemy_power_and_radio_links(
    world: Any, radar: bool, missing: str, expected: IadsState
) -> None:
    sam = make_site(world, radar=radar)
    old, new, enemy = sectors(world, world.destination.position, missing=missing)
    network = world.game.theater.iads_network
    transit = move(world)
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and not sam.in_transit
    assert links(network, sam).isdisjoint([*old.values(), *enemy])
    assert network.state_map.status_for(sam).state is expected
    exported = exported_site(world)
    assert exported is not None and exported.requires_power
    if missing == "power":
        assert not exported.connections.get("PowerSource")
    else:
        assert exported.connections["PowerSource"] == [
            SkynetNode.dcs_name_for_group(new["power"].groups[0])
        ]
        assert not exported.connections.get("ConnectionNode")
        assert not exported.connections.get("CommandCenter")


def test_relocation_copy_explains_reconnection_without_generic_defense_details(
    world: Any,
) -> None:
    sam = make_site(world)
    warnings = armor_movement_options(world.game, sam.id, Player.BLUE).warnings
    assert (
        "SAM/radar sites relocate as a whole. IADS connections are recalculated "
        "from nearby friendly power stations, comms and command centres when "
        "the site stops or arrives."
    ) in warnings
    assert not any("leave the IADS" in text or "defend" in text for text in warnings)


def test_rbs98_keeps_its_specific_transit_defense_restriction(world: Any) -> None:
    sam = make_site(world, RBS98)
    warnings = armor_movement_options(world.game, sam.id, Player.BLUE).warnings
    assert any(
        "RBS-98: no self-defense during relocation." in text for text in warnings
    )
