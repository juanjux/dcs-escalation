"""Automatic radio parents fail over without changing fixed power feeds."""

from typing import Any
from types import SimpleNamespace

import pytest

from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.server.iadsnetwork.models import IadsConnectionJs
from game.theater.iadsnetwork.iadsstate import IadsStateMap
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from tests.test_iads_automatic_topology import site

RADIO_ROLES = {IadsRole.COMMAND_CENTER, IadsRole.CONNECTION_NODE}


def network_for(
    *objects: Any, comms_nm: float = 35, power_nm: float = 35
) -> IadsNetwork:
    settings = Settings()
    settings.set_plugin_option("skynetiads.commsRangeNm", comms_nm)
    settings.set_plugin_option("skynetiads.powerRangeNm", power_nm)
    for obj in objects:
        obj.control_point.coalition.game.settings = settings
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    return network


def node(network: IadsNetwork, obj: Any) -> IadsNetworkNode:
    result = network.node_for_tgo(obj)
    assert result is not None
    return result


def feeds(network: IadsNetwork, obj: Any) -> set[Any]:
    return {
        group.ground_object
        for group in node(network, obj).connections.values()
        if group.iads_role is IadsRole.POWER_SOURCE
    }


def parent(connectivity: IadsConnectivity, current: IadsNetworkNode) -> Any:
    group = connectivity.radio_parent(current)
    return group.ground_object if group is not None else None


def radio_links(connectivity: IadsConnectivity, current: IadsNetworkNode) -> set[Any]:
    return {
        group.ground_object
        for group in connectivity.effective_connections(current).values()
        if group.iads_role in RADIO_ROLES
    }


def redundant_sector() -> tuple[IadsNetwork, list[Any]]:
    objects = [
        site("SAM"),
        site("A TOWER", IadsRole.CONNECTION_NODE, 100),
        site("B TOWER", IadsRole.CONNECTION_NODE, 200),
        site("C TOWER", IadsRole.CONNECTION_NODE, 300),
        site("COMMAND", IadsRole.COMMAND_CENTER, 1000),
        site("POWER", IadsRole.POWER_SOURCE),
    ]
    return network_for(*objects), objects


@pytest.mark.parametrize("failed", [0, 1, 2])
def test_exactly_two_nearest_power_feeds_are_fixed_despite_damage(failed: int) -> None:
    sam = site("SAM")
    plants = [
        site("FIRST", IadsRole.POWER_SOURCE, 100),
        site("SECOND", IadsRole.POWER_SOURCE, 200),
        site("THIRD", IadsRole.POWER_SOURCE, 300),
    ]
    for plant in plants[:failed]:
        plant.groups[0].units[0].alive = False
    network = network_for(sam, *plants)
    assert feeds(network, sam) == set(plants[:2])
    assert IadsConnectivity(network).powered(node(network, sam)) is (failed < 2)
    assert plants[2].groups[0].units[0].alive
    network.initialize_network(iter([sam, *plants]))
    assert feeds(network, sam) == set(plants[:2])
    assert IadsConnectivity(network).powered(node(network, sam)) is (failed < 2)


def test_power_feed_ties_use_stable_names_not_iteration_order() -> None:
    sam = site("SAM")
    plants = [site(name, IadsRole.POWER_SOURCE, 100) for name in ("C", "B", "A")]
    network = network_for(sam, *plants)
    assert {obj.original_name for obj in feeds(network, sam)} == {"A", "B"}
    network.initialize_network(iter([*reversed(plants), sam]))
    assert {obj.original_name for obj in feeds(network, sam)} == {"A", "B"}


def test_radio_parent_fails_over_to_second_and_third_available_tower() -> None:
    network, (sam, first, second, third, _, _) = redundant_sector()
    current = node(network, sam)
    for destroyed, expected in [
        ([], first),
        ([first], second),
        ([first, second], third),
    ]:
        connectivity = IadsConnectivity(network, destroyed=destroyed)
        assert parent(connectivity, current) is expected
        assert radio_links(connectivity, current) == {expected}
        assert connectivity.connected(current)


def test_repaired_primary_tower_becomes_the_parent_again() -> None:
    network, (sam, first, second, _, _, _) = redundant_sector()
    first.groups[0].units[0].alive = False
    network.update_tgo(first, GameUpdateEvents())
    assert parent(IadsConnectivity(network), node(network, sam)) is second
    first.groups[0].units[0].alive = True
    network.update_tgo(first, GameUpdateEvents())
    assert parent(IadsConnectivity(network), node(network, sam)) is first


def test_live_but_isolated_tower_does_not_win_over_a_rooted_tower() -> None:
    sam = site("SAM")
    isolated = site("NEAR ISOLATED", IadsRole.CONNECTION_NODE, -1000)
    available = site("FAR CONNECTED", IadsRole.CONNECTION_NODE, 1700)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 3400)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, isolated, available, command, power, comms_nm=1)
    connectivity = IadsConnectivity(network)
    assert connectivity.available(node(network, isolated))
    assert not connectivity.connected(node(network, isolated))
    assert parent(connectivity, node(network, sam)) is available
    assert connectivity.connected(node(network, sam))


def test_remote_tower_power_loss_switches_parent_and_repair_restores_it() -> None:
    sam = site("SAM")
    first = site("FIRST", IadsRole.CONNECTION_NODE, 1000)
    backup = site("BACKUP", IadsRole.CONNECTION_NODE, -1200)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 2000)
    plants = [
        site("SAM POWER", IadsRole.POWER_SOURCE),
        site("FIRST POWER", IadsRole.POWER_SOURCE, 1000),
        site("BACKUP POWER", IadsRole.POWER_SOURCE, -1200),
        site("COMMAND POWER", IadsRole.POWER_SOURCE, 2000),
    ]
    network = network_for(
        sam, first, backup, command, *plants, comms_nm=2, power_nm=0.1
    )
    assert parent(IadsConnectivity(network), node(network, sam)) is first
    plants[1].groups[0].units[0].alive = False
    network.update_tgo(plants[1], GameUpdateEvents())
    connectivity = IadsConnectivity(network)
    assert connectivity.powered(node(network, sam))
    assert not connectivity.powered(node(network, first))
    assert parent(connectivity, node(network, sam)) is backup
    plants[1].groups[0].units[0].alive = True
    network.update_tgo(plants[1], GameUpdateEvents())
    assert parent(IadsConnectivity(network), node(network, sam)) is first


def test_tower_is_preferred_over_a_closer_direct_command_link() -> None:
    sam = site("SAM")
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 1)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 100)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, command, tower, power)
    assert parent(IadsConnectivity(network), node(network, sam)) is tower


def test_direct_command_connection_works_without_any_tower() -> None:
    sam = site("SAM")
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 100)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, command, power)
    connectivity = IadsConnectivity(network)
    assert parent(connectivity, node(network, sam)) is command
    assert connectivity.connected(node(network, sam))
    assert parent(connectivity, node(network, command)) is None
    assert connectivity.roots(node(network, sam)) == {id(node(network, command))}


def test_dead_consumers_have_no_effective_radio_parent() -> None:
    network, (sam, _, _, _, _, _) = redundant_sector()
    connectivity = IadsConnectivity(network, destroyed=[sam])
    assert parent(connectivity, node(network, sam)) is None
    assert radio_links(connectivity, node(network, sam)) == set()
    assert not connectivity.connected(node(network, sam))


def test_command_only_component_shares_all_roots_bidirectionally() -> None:
    first = site("A COMMAND", IadsRole.COMMAND_CENTER)
    second = site("B COMMAND", IadsRole.COMMAND_CENTER, 1000)
    sam = site("SAM", x=1100)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(first, second, sam, power)
    connectivity = IadsConnectivity(network)
    roots = {id(node(network, first)), id(node(network, second))}
    assert parent(connectivity, node(network, first)) is None
    assert parent(connectivity, node(network, second)) is first
    assert parent(connectivity, node(network, sam)) is second
    for obj in (first, second, sam):
        assert connectivity.roots(node(network, obj)) == roots
    assert connectivity.can_exchange(node(network, first), node(network, sam))


def test_destroyed_root_command_does_not_hide_a_surviving_command() -> None:
    first = site("A COMMAND", IadsRole.COMMAND_CENTER)
    second = site("B COMMAND", IadsRole.COMMAND_CENTER, 1000)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 2000)
    sam = site("SAM", x=2100)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(first, second, tower, sam, power)
    connectivity = IadsConnectivity(network, destroyed=[first])
    assert connectivity.roots(node(network, sam)) == {id(node(network, second))}
    assert parent(connectivity, node(network, second)) is None
    assert connectivity.connected(node(network, sam))


def test_rootless_tower_tree_does_not_give_consumers_command() -> None:
    first = site("A TOWER", IadsRole.CONNECTION_NODE)
    second = site("B TOWER", IadsRole.CONNECTION_NODE, 100)
    sam = site("SAM", x=200)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(first, second, sam, power)
    connectivity = IadsConnectivity(network)
    assert parent(connectivity, node(network, first)) is None
    assert parent(connectivity, node(network, second)) is first
    assert not connectivity.connected(node(network, first))
    assert not connectivity.connected(node(network, second))
    assert parent(connectivity, node(network, sam)) is None
    assert not connectivity.connected(node(network, sam))


def test_router_forest_has_one_oriented_parent_and_no_cycles() -> None:
    routers = [
        site("A TOWER", IadsRole.CONNECTION_NODE, 0),
        site("B TOWER", IadsRole.CONNECTION_NODE, 100),
        site("C TOWER", IadsRole.CONNECTION_NODE, 300),
        site("D TOWER", IadsRole.CONNECTION_NODE, 450),
        site("Z COMMAND", IadsRole.COMMAND_CENTER, 1000),
    ]
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(*routers, power)
    expected = dict(zip(routers, [*routers[1:], None]))
    for objects in ([*routers, power], [power, *reversed(routers)]):
        network.initialize_network(iter(objects))
        connectivity = IadsConnectivity(network)
        for obj in routers:
            current = node(network, obj)
            assert parent(connectivity, current) is expected[obj]
            assert len(radio_links(connectivity, current)) <= 1
            assert not any(
                group.iads_role in RADIO_ROLES for group in current.connections.values()
            )
        assert (
            sum(len(radio_links(connectivity, node(network, obj))) for obj in routers)
            == len(routers) - 1
        )


def test_radio_candidates_are_not_simultaneous_effective_connections() -> None:
    network, (sam, first, second, third, command, _) = redundant_sector()
    current = node(network, sam)
    assert current.radio_candidates is not None
    assert {group.ground_object for group, _ in current.radio_candidates} == {
        first,
        second,
        third,
        command,
    }
    assert radio_links(IadsConnectivity(network), current) == {first}
    assert not any(
        group.iads_role in RADIO_ROLES for group in current.connections.values()
    )


@pytest.mark.parametrize(
    "distance, expected", [(100.49, 100), (100.5, 101), (100.99, 101)]
)
def test_candidate_distances_use_integer_half_up_rounding(
    distance: float, expected: int
) -> None:
    sam = site("SAM")
    tower = site("TOWER", IadsRole.CONNECTION_NODE, distance)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 1000)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, tower, command, power)
    candidates = node(network, sam).radio_candidates
    assert candidates is not None
    assert (
        next(d for group, d in candidates if group.ground_object is tower) == expected
    )


def test_equal_rounded_candidate_distances_use_stable_names() -> None:
    sam = site("SAM")
    first = site("A TOWER", IadsRole.CONNECTION_NODE, 100.49)
    second = site("B TOWER", IadsRole.CONNECTION_NODE, 100.4)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 1000)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, second, first, command, power)
    assert parent(IadsConnectivity(network), node(network, sam)) is first


def test_gps_jammer_has_two_power_feeds_and_no_radio_candidates() -> None:
    jammer = site("JAMMER")
    jammer.groups[0].units[0].ground_unit_variant = "GPS Jammer (Red)"
    assert jammer.carries_gps_jammer
    first = site("FIRST POWER", IadsRole.POWER_SOURCE, 100)
    second = site("SECOND POWER", IadsRole.POWER_SOURCE, 200)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 300)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 400)
    network = network_for(jammer, first, second, tower, command)
    current = node(network, jammer)
    connectivity = IadsConnectivity(network)
    assert feeds(network, jammer) == {first, second}
    assert current.radio_candidates == []
    assert parent(connectivity, current) is None
    assert radio_links(connectivity, current) == set()
    assert not any(
        group.iads_role in RADIO_ROLES for group in current.connections.values()
    )


@pytest.mark.parametrize("side", [Player.RED, Player.BLUE])
def test_candidate_parents_and_roots_never_cross_coalitions(side: Player) -> None:
    sam = site("SAM", side=side)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 1000, side)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 2000, side)
    power = site("POWER", IadsRole.POWER_SOURCE, 2000, side)
    enemy = site("ENEMY TOWER", IadsRole.CONNECTION_NODE, 1, side.opponent)
    enemy_command = site("ENEMY COMMAND", IadsRole.COMMAND_CENTER, 2, side.opponent)
    enemy_power = site("ENEMY POWER", IadsRole.POWER_SOURCE, 3, side.opponent)
    network = network_for(sam, tower, command, power, enemy, enemy_command, enemy_power)
    current = node(network, sam)
    assert current.radio_candidates is not None
    assert {group.ground_object for group, _ in current.radio_candidates} == {
        tower,
        command,
    }
    assert feeds(network, sam) == {power}
    connectivity = IadsConnectivity(network)
    assert connectivity.roots(current) == {id(node(network, command))}
    assert not connectivity.can_exchange(current, node(network, enemy))


def test_shared_router_component_exchanges_all_command_roots() -> None:
    first = site("FIRST COMMAND", IadsRole.COMMAND_CENTER)
    second = site("SECOND COMMAND", IadsRole.COMMAND_CENTER, 10_000)
    bridge = site("BRIDGE", IadsRole.CONNECTION_NODE, 5000)
    sam = site("SAM")
    ewr = site("EWR", IadsRole.EWR, 10_000)
    power = site("POWER", IadsRole.POWER_SOURCE, 5000)
    network = network_for(first, second, bridge, sam, ewr, power, comms_nm=3)
    connectivity = IadsConnectivity(network)
    assert connectivity.can_exchange(node(network, sam), node(network, ewr))
    assert connectivity.roots(node(network, sam)) == {
        id(node(network, first)),
        id(node(network, second)),
    }
    separated = IadsConnectivity(network, destroyed=[bridge])
    assert separated.connected(node(network, sam))
    assert separated.connected(node(network, ewr))
    assert not separated.can_exchange(node(network, sam), node(network, ewr))


def test_hypothetical_failover_does_not_change_live_links_candidates_or_health() -> (
    None
):
    network, (sam, first, second, _, _, _) = redundant_sector()
    before = {
        id(current): (
            dict(current.connections),
            list(current.radio_candidates or []),
            [unit.alive for unit in current.group.units],
        )
        for current in network.nodes
    }
    live = IadsConnectivity(network)
    simulated = IadsStateMap(network, destroyed=[first])
    assert simulated.connectivity is not None
    assert parent(simulated.connectivity, node(network, sam)) is second
    assert parent(live, node(network, sam)) is first
    assert parent(IadsConnectivity(network), node(network, sam)) is first
    assert before == {
        id(current): (
            dict(current.connections),
            list(current.radio_candidates or []),
            [unit.alive for unit in current.group.units],
        )
        for current in network.nodes
    }


def test_nonoperational_roots_use_an_undamaged_forest_without_mutation() -> None:
    sam = site("SAM")
    relay = site("RELAY", IadsRole.CONNECTION_NODE, 1500)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 3000)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(sam, relay, command, power, comms_nm=1)
    connectivity = IadsConnectivity(network, destroyed=[relay])
    current = node(network, sam)
    assert connectivity.roots(current) == set()
    assert connectivity.roots(current, operational=False) == {
        id(node(network, command))
    }
    assert connectivity.roots(current) == set()
    assert parent(connectivity, current) is None
    assert relay.groups[0].units[0].alive
    assert IadsConnectivity(network).connected(current)


def test_failover_replaces_map_edge_even_while_site_stays_networked() -> None:
    network, (sam, first, second, _, _, _) = redundant_sector()
    current = node(network, sam)
    before = network.state_map.status_for(sam)
    old = next(
        link
        for link in IadsConnectionJs.connections_for_node(current, network)
        if not link.is_power
    )
    assert old.connected == first.id
    first.groups[0].units[0].alive = False
    events = GameUpdateEvents()
    network.update_tgo(first, events)
    updated = next(
        link
        for link in IadsConnectionJs.connections_for_node(current, network)
        if not link.is_power
    )
    assert updated.connected == second.id and updated.id != old.id
    assert old.id in events.deleted_iads_connections
    assert current in events.updated_iads and sam in events.updated_tgos
    assert network.state_map.status_for(sam) == before


def test_newly_registered_site_is_enrolled_even_without_an_existing_node() -> None:
    command = site("COMMAND", IadsRole.COMMAND_CENTER)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = network_for(command, power)
    late = site("LATE SAM", x=100)
    network.ground_objects[late.original_name] = late
    assert network.enrol_sites_that_arrived_late() == [late.name]
    assert feeds(network, late) == {power}
    assert network.state_map.connectivity is not None
    assert network.state_map.connectivity.connected(node(network, late))
    assert network.enrol_sites_that_arrived_late() == []


def test_late_power_station_rewires_cached_sites_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sam = site("SAM")
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 100)
    radar = site("EARLY WARNING", IadsRole.EWR, 150)
    network = network_for(sam, command, radar)
    before = network.state_map.status_for(sam)
    assert before is not None and before.state is IadsState.DARK
    power = site("LATE POWER", IadsRole.POWER_SOURCE, 200)
    network.ground_objects[power.original_name] = power
    calls = []
    original = network._rebuild_advanced_connections

    def rebuild(events: Any = None) -> None:
        calls.append(events)
        original(events)

    monkeypatch.setattr(network, "_rebuild_advanced_connections", rebuild)
    assert network.enrol_sites_that_arrived_late() == []
    assert feeds(network, sam) == {power}
    after = network.state_map.status_for(sam)
    assert after is not None and after.state is IadsState.NETWORKED
    assert network.enrol_sites_that_arrived_late() == []
    assert len(calls) == 1


def test_legacy_explicit_feed_is_removed_when_station_is_captured() -> None:
    sam = site("SAM")
    power = site("POWER", IadsRole.POWER_SOURCE, 100)
    network = network_for(sam, power)
    current = node(network, sam)
    current.radio_candidates = None
    network.invalidate_state_map()
    assert IadsConnectivity(network).powered(current)
    power.control_point.captured = Player.BLUE
    power.control_point.coalition.player = Player.BLUE
    network.update_tgo(power, GameUpdateEvents())
    assert current.radio_candidates is None
    assert power.groups[0] not in current.connections.values()
    assert not IadsConnectivity(network).powered(current)
    game: Any = SimpleNamespace(
        iads_considerate_culling=lambda _obj: False, skynet_culled=lambda _obj: False
    )
    exported = next(
        row
        for row in network.skynet_nodes(game)
        if row.dcs_name == sam.groups[0].group_name
    )
    assert exported.requires_power and exported.connections["PowerSource"] == []
