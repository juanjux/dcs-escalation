"""Check Scenic Route 2: Dust to Dust infrastructure against the default automatic IADS ranges."""

from pathlib import Path
from typing import Any

import pytest

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.utils import Heading
from tests.test_iads_automatic_topology import site

CAMPAIGN = Path("resources/campaigns/scenic_inland.yaml")
ROLES = {
    "long_range_sams": IadsRole.SAM,
    "medium_range_sams": IadsRole.SAM,
    "short_range_sams": IadsRole.SAM,
    "aaa": IadsRole.EWR,
    "ewrs": IadsRole.EWR,
    "iads_command_center": IadsRole.COMMAND_CENTER,
    "iads_connection_node": IadsRole.CONNECTION_NODE,
    "iads_power_source": IadsRole.POWER_SOURCE,
}


@pytest.mark.parametrize("inverted", [False, True])
def test_all_land_defences_have_a_friendly_command_path(inverted: bool) -> None:
    campaign = Campaign.from_file(CAMPAIGN)
    theater = campaign.load_theater(True)
    objects: list[Any] = []
    placements: list[tuple[str, Any, Any, IadsRole]] = []
    overrides = campaign.data.get("ground_forces", {})
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        owner = cp.starting_coalition.opponent if inverted else cp.starting_coalition
        for kind, role in ROLES.items():
            for point in getattr(cp.preset_locations, kind):
                if "GPS Jamming" not in str(overrides.get(point.original_name, "")):
                    placements.append((point.original_name, point, owner, role))
        for scenery in cp.preset_locations.scenery:
            role = IadsRole.for_category(scenery.category)
            if role is not IadsRole.NO_BEHAVIOR:
                placements.append(
                    (scenery.zone_def.name, scenery.position, owner, role)
                )
    names = [name for name, _, _, _ in placements]
    assert len(names) == len(
        set(names)
    ), "An objective would overwrite another IADS node"
    for name, point, owner, role in placements:
        obj = site(name, role, side=owner)
        obj.position = PointWithHeading.from_point(point, Heading.from_degrees(0))
        objects.append(obj)
        if name.startswith(
            (
                "Blue IADS Relay ",
                "Red IADS Relay ",
                "Blue IADS Command ",
                "Red IADS Command ",
            )
        ):
            assert theater.is_on_land(point, ignore_exclusion=True), name

    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    connectivity = IadsConnectivity(network)
    ground = [
        n for n in network.nodes if n.group.iads_role in (IadsRole.SAM, IadsRole.EWR)
    ]
    assert ground
    assert all(connectivity.connected(n) for n in ground), [
        n.group.ground_object.original_name
        for n in ground
        if not connectivity.connected(n)
    ]
    for node in ground:
        owner = node.group.ground_object.control_point.captured
        assert all(
            root.group.ground_object.control_point.captured is owner
            for root in connectivity.centres_for(node)
        )
    for owner in {obj.control_point.captured for obj in objects}:
        roots = {
            frozenset(id(root) for root in connectivity.centres_for(node))
            for node in ground
            if node.group.ground_object.control_point.captured is owner
        }
        assert len(roots) <= 1, "A mainland command sector is unintentionally split"

    commands = [
        obj for obj in objects if obj.groups[0].iads_role is IadsRole.COMMAND_CENTER
    ]
    destroyed = IadsConnectivity(network, commands)
    assert all(not destroyed.connected(n) for n in ground)
