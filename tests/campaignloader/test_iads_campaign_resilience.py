"""Lean campaign networks retain coverage after any single command-centre loss."""

import json
from pathlib import Path
from typing import Any

import pytest

from game.campaignloader.campaign import Campaign
from game.point_with_heading import PointWithHeading
from game.theater.iadsnetwork.connectivity import IadsConnectivity
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, SkynetNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.utils import Heading
from game.theater.player import Player
from tests.missiongenerator.test_iads_topology_runtime import exported, start, vm
from tests.campaignloader.test_iads_campaign_expansion import ROLES
from tests.test_iads_automatic_topology import site

MANIFEST = json.loads(Path(__file__).with_name("iads_resilience.json").read_text())


@pytest.mark.parametrize("filename", MANIFEST)
def test_network_survives_any_single_command_loss(filename: str, vm: Any) -> None:
    campaign = Campaign.from_file(Path("resources/campaigns") / filename)
    assert campaign.advanced_iads
    theater = campaign.load_theater(True)
    row = MANIFEST[filename]
    objects: list[Any] = []
    for cp in theater.controlpoints:
        if cp.starting_coalition.is_neutral:
            continue
        placements = [
            (point.original_name, point, role)
            for kind, role in ROLES.items()
            for point in getattr(cp.preset_locations, kind)
        ]
        placements.extend(
            (
                scenery.zone_def.name,
                scenery.position,
                IadsRole.for_category(scenery.category),
            )
            for scenery in cp.preset_locations.scenery
            if IadsRole.for_category(scenery.category) is not IadsRole.NO_BEHAVIOR
        )
        for name, point, role in placements:
            obj = site(name, role, side=cp.starting_coalition)
            obj.position = PointWithHeading.from_point(point, Heading.from_degrees(0))
            objects.append(obj)
            if " IADS Regional Command " in name or " IADS Consolidated Relay " in name:
                if not theater.is_on_land(point, ignore_exclusion=True):
                    assert [point.x, point.y] == row["island_mask_exceptions"][name]
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    relays = [n for n in network.nodes if n.group.iads_role is IadsRole.CONNECTION_NODE]
    commands = [
        n for n in network.nodes if n.group.iads_role is IadsRole.COMMAND_CENTER
    ]
    assert len(relays) == row["after"]["relays"]
    assert len(commands) == row["after"]["command_centres"]
    assert len(relays) <= row["before"]["relays"]
    # Require resilience only for previously connected sites. Autonomous
    # outposts are not a reason to introduce additional command networks.
    targets = [
        n
        for n in network.nodes
        if n.group.iads_role in (IadsRole.SAM, IadsRole.EWR)
        and n.group.ground_object.original_name not in row["autonomous_sites"]
    ]
    by_name = {n.group.ground_object.original_name: n for n in targets}
    normal = IadsConnectivity(network)
    for sector in row["network_sectors"]:
        shared = [normal.roots(by_name[name]) for name in sector]
        assert shared and set.intersection(*(set(roots) for roots in shared)), (
            "An existing command sector no longer shares contacts",
            sector,
        )
    for loss in [[], *[[n.group.ground_object] for n in commands]]:
        connectivity = IadsConnectivity(network, loss)
        assert all(connectivity.connected(n) for n in targets), [
            n.group.ground_object.original_name
            for n in targets
            if not connectivity.connected(n)
        ]
    for side in (Player.BLUE, Player.RED):
        start(vm, exported(network, side), 2 if side.is_blue else 1)
        side_commands = [
            n for n in commands if n.group.ground_object.control_point.captured is side
        ]
        side_targets = [
            n for n in targets if n.group.ground_object.control_point.captured is side
        ]
        for failed in [None, *side_commands]:
            loss = [failed.group.ground_object] if failed is not None else []
            if failed is not None:
                vm.globals().objects[
                    SkynetNode.dcs_name_for_group(failed.group)
                ].live = False
            topology = vm.globals().iads.topology
            topology.beginCycle(topology)
            connectivity = IadsConnectivity(network, loss)
            for target in side_targets:
                element = vm.globals().elements[
                    SkynetNode.dcs_name_for_group(target.group)
                ]
                assert element.hasActiveConnectionNode(
                    element
                ) == connectivity.connected(target)
                assert element.hasWorkingPowerSource(element) == connectivity.powered(
                    target
                )
            if failed is not None:
                vm.globals().objects[
                    SkynetNode.dcs_name_for_group(failed.group)
                ].live = True
