"""Distinct Yankee Station command objectives must not replace one another."""

from pathlib import Path
from typing import Any

import pytest

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.player import Player
from game.utils import Heading
from tests.test_iads_automatic_topology import site

CAMPAIGN = Path("resources/campaigns/1968_Yankee_Station.yaml")


@pytest.mark.parametrize("inverted", [False, True])
def test_all_twelve_command_sites_keep_their_own_identity(inverted: bool) -> None:
    campaign = Campaign.from_file(CAMPAIGN)
    theater = campaign.load_theater(True)
    placements: list[tuple[str, Any, Any]] = []
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        for point in cp.preset_locations.iads_command_center:
            placements.append((point.original_name, point, cp))
        for scenery in cp.preset_locations.scenery:
            if scenery.category == "commandcenter":
                placements.append((scenery.zone_def.name, scenery.position, cp))
    assert len(placements) == 12
    assert len({name for name, _, _ in placements}) == 12
    owners = {name: (cp.name, cp.starting_coalition) for name, _, cp in placements}
    assert owners["Command Center-1"] == ("FOB Khe-Sahn", Player.BLUE)
    assert owners["Red IADS Command FOB Laos"] == ("FOB Laos", Player.RED)
    assert owners["Command Center-2"] == ("Sukhumi-Babushara", Player.RED)
    assert owners["Red IADS Command FOB Thailand"] == ("FOB Thailand", Player.RED)
    assert owners["Command Center-3"] == ("Senaki-Kolkhi", Player.RED)
    assert owners["Red IADS Command FOB Cambodia"] == ("FOB Cambodia", Player.RED)

    objects = []
    for name, point, cp in placements:
        owner = cp.starting_coalition.opponent if inverted else cp.starting_coalition
        obj = site(name, IadsRole.COMMAND_CENTER, side=owner)
        obj.position = PointWithHeading.from_point(point, Heading.from_degrees(0))
        objects.append(obj)
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    assert len(network.nodes) == 12
    assert {id(n.group.ground_object) for n in network.nodes} == {
        id(obj) for obj in objects
    }
    for node in network.nodes:
        assert all(
            group.ground_object.control_point.captured
            is node.group.ground_object.control_point.captured
            for group in node.connections.values()
        )
