"""Sparse radio backbones preserve local connectivity without a full mesh."""

from math import cos, sin, tau
from typing import Any
from dcs.terrain import Caucasus

from game.point_with_heading import PointWithHeading
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsStateMap
from game.utils import Heading
from tests.test_iads_automatic_topology import links, site


def layout() -> tuple[IadsNetwork, list[Any]]:
    objects = [site("POWER", IadsRole.POWER_SOURCE)]
    for i in range(12):
        role = IadsRole.COMMAND_CENTER if i in (0, 6) else IadsRole.CONNECTION_NODE
        obj = site(f"ROUTER {i:02}", role)
        obj.position = PointWithHeading(
            cos(tau * i / 12) * 10_000,
            sin(tau * i / 12) * 10_000,
            Heading.from_degrees(0),
            Caucasus(),
        )
        objects.append(obj)
    for i in range(30):
        objects.append(site(f"SAM {i:02}", x=i * 500))
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    return network, objects


def test_dense_sectors_use_a_sparse_backbone_and_bounded_local_feeds() -> None:
    network, objects = layout()
    for obj in objects:
        parents = links(network, obj)
        assert len([p for p in parents if p.category == "power"]) <= 1
        if obj.category == "aa":
            assert len(parents) == 3  # Two radio paths and one local power feed.
    backbone = [
        n
        for n in network.nodes
        if n.group.iads_role
        in (
            IadsRole.COMMAND_CENTER,
            IadsRole.CONNECTION_NODE,
        )
    ]
    edges = sum(
        len(
            [
                g
                for g in n.connections.values()
                if g.iads_role is not IadsRole.POWER_SOURCE
            ]
        )
        for n in backbone
    )
    assert edges < 4 * len(backbone)
    assert links(network, objects[0]) == set()  # Plants do not relay radio or power.


def test_existing_single_router_loss_bypasses_remain_available() -> None:
    network, objects = layout()
    targets = [n for n in network.nodes if n.group.iads_role is IadsRole.SAM]
    for failed in objects[1:13]:
        connectivity = IadsConnectivity(network, destroyed=[failed])
        assert all(connectivity.connected(n) for n in targets), failed.name


def test_input_order_does_not_change_the_selected_topology() -> None:
    network, objects = layout()
    before = {obj.name: {p.name for p in links(network, obj)} for obj in objects}
    network.initialize_network(iter(reversed(objects)))
    assert {
        obj.name: {p.name for p in links(network, obj)} for obj in objects
    } == before


def test_destroying_a_feed_does_not_silently_select_another_station() -> None:
    sam = site("SAM")
    primary = site("PRIMARY", IadsRole.POWER_SOURCE, 100)
    remote = site("REMOTE", IadsRole.POWER_SOURCE, 10_000)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, primary, remote]))
    assert links(network, sam) == {primary}
    primary.groups[0].units[0].alive = False
    network.update_tgo(primary, GameUpdateEvents())
    assert links(network, sam) == {primary}
    node = network.node_for_tgo(sam)
    assert node is not None
    assert not IadsConnectivity(network).powered(node)
    network.initialize_network(iter([sam, primary, remote]))
    assert links(network, sam) == {primary}


def test_unchanged_links_keep_their_identifiers_when_a_station_changes() -> None:
    network, objects = layout()
    sam = network.node_for_tgo(objects[-1])
    assert sam is not None
    before = dict(sam.connections)
    objects[2].groups[0].units[0].alive = False
    network.update_tgo(objects[2], GameUpdateEvents())
    assert sam.connections == before


def test_power_outage_simulation_does_not_modify_the_network() -> None:
    network, objects = layout()
    statuses = list(network.state_map)
    simulated = IadsStateMap(network, destroyed=[objects[0]])
    assert simulated.connectivity is not None
    assert all(
        not simulated.connectivity.powered(n)
        for n in network.nodes
        if n.group.iads_role is not IadsRole.POWER_SOURCE
    )
    assert list(network.state_map) == statuses


def test_power_loss_affects_the_local_feed_not_a_remote_sector() -> None:
    west = site("WEST")
    east = site("EAST", x=100_000)
    west_power = site("WEST POWER", IadsRole.POWER_SOURCE)
    east_power = site("EAST POWER", IadsRole.POWER_SOURCE, 100_000)
    network = IadsNetwork(True)
    network.initialize_network(iter([west, east, west_power, east_power]))
    west_power.groups[0].units[0].alive = False
    network.update_tgo(west_power, GameUpdateEvents())
    connectivity = IadsConnectivity(network)
    west_node, east_node = network.node_for_tgo(west), network.node_for_tgo(east)
    assert west_node is not None and east_node is not None
    assert not connectivity.powered(west_node)
    assert connectivity.powered(east_node)


def test_power_stations_do_not_trigger_repeated_late_enrolment(
    monkeypatch: Any,
) -> None:
    network, _ = layout()

    def unexpected_rebuild() -> None:
        raise AssertionError(
            "An already wired network must not be rebuilt for its plants"
        )

    monkeypatch.setattr(network, "_rebuild_advanced_connections", unexpected_rebuild)
    assert network.enrol_sites_that_arrived_late() == []
