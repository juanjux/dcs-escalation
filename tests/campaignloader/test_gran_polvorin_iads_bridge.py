"""Ushuaia outposts remain autonomous; radio links follow range and damage."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.server.iadsnetwork.models import IadsNetworkJs
from game.settings import Settings
from game.theater import Player
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.utils import Heading
from tests.test_iads_automatic_topology import site

SECTORS = ("Ground-1", "Ground-2", "Ground-7", "Red EWR Ushuaia")


def test_ushuaia_outposts_remain_powered_and_autonomous() -> None:
    campaign = Campaign.from_file(Path("resources/campaigns/gran_polvorin.yaml"))
    theater = campaign.load_theater(True)
    assert "iads_config" not in campaign.data
    assert not any(
        cp.preset_locations.iads_connection_node for cp in theater.controlpoints
    )
    roles = {
        "long_range_sams": IadsRole.SAM,
        "medium_range_sams": IadsRole.SAM,
        "short_range_sams": IadsRole.SAM,
        "aaa": IadsRole.EWR,
        "ewrs": IadsRole.EWR,
        "iads_command_center": IadsRole.COMMAND_CENTER,
        "iads_connection_node": IadsRole.CONNECTION_NODE,
        "iads_power_source": IadsRole.POWER_SOURCE,
    }
    objectives = []
    outposts = {}
    for cp in theater.controlpoints:
        for kind, role in roles.items():
            for point in getattr(cp.preset_locations, kind):
                if point.original_name not in SECTORS and role in (
                    IadsRole.SAM,
                    IadsRole.EWR,
                ):
                    continue
                objective = site(point.original_name, role, side=cp.starting_coalition)
                objective.position = PointWithHeading.from_point(
                    point, Heading.from_degrees(0)
                )
                objectives.append(objective)
                if point.original_name in SECTORS:
                    assert cp.name == "Ushuaia", point.original_name
                    assert cp.starting_coalition is Player.RED
                    outposts[point.original_name] = objective
    assert set(outposts) == set(SECTORS)
    network = IadsNetwork(True)
    network.initialize_network(iter(objectives))
    connectivity = network.state_map.connectivity
    assert connectivity is not None
    for name, objective in outposts.items():
        node = network.node_for_tgo(objective)
        assert node is not None
        assert connectivity.powered(node), name
        assert not connectivity.connected(node), name
        status = network.state_map.status_for(objective)
        assert status is not None and status.state is IadsState.AUTONOMOUS, name


@pytest.mark.parametrize("side", [Player.RED, Player.BLUE])
@pytest.mark.parametrize("range_nm", [15, 200])
def test_relay_links_follow_coverage_and_remain_exported_when_destroyed(
    side: Player,
    range_nm: int,
) -> None:
    settings = Settings()
    settings.set_plugin_option("skynetiads.commsRangeNm", range_nm)
    distances = (0, 15 * 1852, 15 * 1852 + 1, 200 * 1852 + 1)
    sams = [
        site(f"SAM {index}", x=distance, side=side, settings=settings)
        for index, distance in enumerate(distances)
    ]
    relay = site("RELAY", IadsRole.CONNECTION_NODE, side=side, settings=settings)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, side=side, settings=settings)
    power = [
        site(f"POWER {index}", IadsRole.POWER_SOURCE, distance, side, settings)
        for index, distance in enumerate(distances)
    ]
    network = IadsNetwork(True)
    network.initialize_network(iter([*sams, relay, command, *power]))
    game: Any = SimpleNamespace(
        iads_considerate_culling=lambda _: False, skynet_culled=lambda _: False
    )
    nodes = network.skynet_nodes(game)
    expected = {
        sam.groups[0].group_name
        for sam, distance in zip(sams, distances)
        if distance <= range_nm * 1852
    }
    sam_nodes = [node for node in nodes if node.iads_role is IadsRole.SAM]
    assert len(expected) == (2 if range_nm == 15 else 3)
    assert len(sam_nodes) == len(sams)
    for node in sam_nodes:
        assert node.connections["ConnectionNode"] == (
            [relay.groups[0].units[0].unit_name] if node.dcs_name in expected else []
        )
    sam_ids = {sam.id for sam in sams}
    links = [
        link
        for link in IadsNetworkJs.from_network(network).connections
        if link.node in sam_ids and link.connected == relay.id
    ]
    assert len(links) == len(expected)
    assert all(link.active and link.blue == side.is_blue for link in links)
    link_ids = {link.id for link in links}
    relay.groups[0].units[0].alive = False
    network.invalidate_state_map()
    links = [
        link
        for link in IadsNetworkJs.from_network(network).connections
        if link.id in link_ids
    ]
    assert {link.id for link in links} == link_ids
    assert all(not link.active for link in links)
    for node in network.skynet_nodes(game):
        if node.iads_role is IadsRole.SAM:
            assert node.connections["ConnectionNode"] == (
                [relay.groups[0].units[0].unit_name]
                if node.dcs_name in expected
                else []
            )
