"""Operational paths, rather than coalition-wide command, drive advanced IADS."""

from typing import Any

import pytest

from game.server.iadsnetwork.models import IadsConnectionJs
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsexplain import describe
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStateMap
from game.theater.player import Player
from tests.test_iads_automatic_topology import site


def chain(side: Player = Player.RED) -> tuple[IadsNetwork, list[Any]]:
    objects = [
        site("COMMAND", IadsRole.COMMAND_CENTER, 0, side),
        site("RELAY A", IadsRole.CONNECTION_NODE, 20_000, side),
        site("RELAY B", IadsRole.CONNECTION_NODE, 40_000, side),
        site("SAM", IadsRole.SAM, 60_000, side),
        site("EWR", IadsRole.EWR, 60_001, side),
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    return network, objects


def state(network: IadsNetwork, obj: Any) -> IadsState:
    status = network.state_map.status_for(obj)
    assert status is not None
    return status.state


def node(network: IadsNetwork, obj: Any) -> Any:
    found = network.node_for_tgo(obj)
    assert found is not None
    return found


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
def test_multiple_relays_reach_command_and_remote_loss_breaks_the_chain(
    side: Player,
) -> None:
    network, (command, relay_a, relay_b, sam, ewr) = chain(side)
    assert state(network, sam) is IadsState.NETWORKED
    connectivity = network.state_map.connectivity
    assert connectivity is not None
    assert connectivity.centres_for(node(network, sam)) == [node(network, command)]
    # There is no direct link to the failed tower, only to the last relay.
    assert relay_a.groups[0] not in node(network, sam).connections.values()
    relay_a.groups[0].units[0].alive = False
    events = GameUpdateEvents()
    network.update_tgo(relay_a, events)
    assert state(network, sam) is IadsState.AUTONOMOUS
    assert state(network, ewr) is IadsState.AUTONOMOUS
    connectivity = network.state_map.connectivity
    assert connectivity is not None
    assert not connectivity.link_operational(node(network, sam), relay_b.groups[0])
    assert sam in events.updated_tgos
    relay_a.groups[0].units[0].alive = True
    network.update_tgo(relay_a, GameUpdateEvents())
    assert state(network, sam) is IadsState.NETWORKED


def test_redundant_radio_path_survives_one_relay_loss() -> None:
    network, objects = chain()
    backup = site("BACKUP", IadsRole.CONNECTION_NODE, 20_001)
    network.initialize_network(iter([*objects, backup]))
    objects[1].groups[0].units[0].alive = False
    network.update_tgo(objects[1], GameUpdateEvents())
    assert state(network, objects[3]) is IadsState.NETWORKED
    backup.groups[0].units[0].alive = False
    network.update_tgo(backup, GameUpdateEvents())
    assert state(network, objects[3]) is IadsState.AUTONOMOUS


def test_remote_infrastructure_link_changes_are_published_to_the_map() -> None:
    network, objects = chain()
    distant = site("RELAY C", IadsRole.CONNECTION_NODE, 60_000)
    network.initialize_network(iter([*objects, distant]))
    assert network.state_map.connectivity is not None
    objects[1].groups[0].units[0].alive = False
    events = GameUpdateEvents()
    network.update_tgo(objects[1], events)
    assert node(network, distant) in events.updated_iads
    assert distant in events.updated_tgos
    assert not any(
        link.active
        for link in IadsConnectionJs.connections_for_node(
            node(network, distant), network
        )
    )


def test_direct_command_link_does_not_require_a_neighboring_tower() -> None:
    sam = site("SAM")
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 500)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 1000)
    ewr = site("EWR", IadsRole.EWR, 100)
    tower.groups[0].units[0].alive = False
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, command, tower, ewr]))
    assert state(network, sam) is IadsState.NETWORKED


def test_power_stations_do_not_bridge_radio_gaps() -> None:
    sam = site("SAM", x=60_000)
    command = site("COMMAND", IadsRole.COMMAND_CENTER)
    plant = site("PLANT", IadsRole.POWER_SOURCE, 30_000)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, command, plant]))
    assert plant.groups[0] in node(network, sam).connections.values()
    assert plant.groups[0] in node(network, command).connections.values()
    assert state(network, sam) is IadsState.AUTONOMOUS


def test_power_loss_at_remote_relay_blocks_otherwise_powered_sites() -> None:
    network, (command, relay_a, relay_b, sam, ewr) = chain()
    # A dedicated power feed for the remote relay; it is not the SAM's supply.
    plant = site("RELAY POWER", IadsRole.POWER_SOURCE, -40_000)
    network.initialize_network(iter([command, relay_a, relay_b, sam, ewr, plant]))
    assert plant.groups[0] in node(network, relay_a).connections.values()
    assert plant.groups[0] not in node(network, sam).connections.values()
    assert state(network, sam) is IadsState.NETWORKED
    plant.groups[0].units[0].alive = False
    network.update_tgo(plant, GameUpdateEvents())
    assert state(network, sam) is IadsState.AUTONOMOUS
    connectivity = network.state_map.connectivity
    assert connectivity is not None
    assert connectivity.powered(node(network, sam))
    assert not connectivity.powered(node(network, relay_a))
    assert (
        describe(relay_a, network).headline
        == "No power: this relay cannot carry communications."
    )


def test_separate_command_components_do_not_share_cues() -> None:
    # The radar sees across the radio gap, but does not share a command path.
    sam = site("SAM", x=30_000)
    ewr = site("EWR", IadsRole.EWR, 30_001)
    first = site("FIRST", IadsRole.COMMAND_CENTER, 30_000)
    second = site("SECOND", IadsRole.COMMAND_CENTER, 30_000)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, ewr, first, second]))
    for obj, centre in [(sam, first), (ewr, second), (first, first), (second, second)]:
        current = node(network, obj)
        current.connections.clear()
        if obj is not centre:
            current.add_connection_for_group(centre.groups[0])
    network.invalidate_state_map()
    connectivity = network.state_map.connectivity
    assert connectivity is not None
    assert connectivity.connected(node(network, sam))
    assert connectivity.connected(node(network, ewr))
    assert not connectivity.can_exchange(node(network, sam), node(network, ewr))
    assert state(network, sam) is IadsState.AUTONOMOUS


def test_no_command_center_means_autonomous_not_implicitly_networked() -> None:
    sam, ewr = site("SAM"), site("EWR", IadsRole.EWR)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, ewr]))
    assert state(network, sam) is IadsState.AUTONOMOUS
    assert state(network, ewr) is IadsState.AUTONOMOUS


def test_map_api_explanation_and_hypothetical_losses_use_the_same_path() -> None:
    network, (_, relay_a, _, sam, _) = chain()
    before = describe(sam, network)
    assert (
        next(link for link in before.links if link.caption == "COMMAND").chip
        == "DIRECTING"
    )
    simulated = IadsStateMap(network, destroyed=[relay_a])
    simulated_status = simulated.status_for(sam)
    assert simulated_status is not None
    assert simulated_status.state is IadsState.AUTONOMOUS
    assert state(network, sam) is IadsState.NETWORKED
    relay_a.groups[0].units[0].alive = False
    network.update_tgo(relay_a, GameUpdateEvents())
    after = describe(sam, network)
    assert (
        next(link for link in after.links if link.caption == "COMMAND").chip
        == "CUT OFF"
    )
    assert next(link for link in after.links if link.caption == "COMMS").chip == "CUT"
    assert not any(
        link.active
        for link in IadsConnectionJs.connections_for_node(node(network, sam), network)
    )
