"""The Ushuaia airport and inland sector share a real communications objective."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dcs import Mission
from dcs.statics import Fortification
from dcs.vehicles import AirDefence
from dcs.unittype import UnitType

from game.campaignloader.campaign import Campaign
from game.data.groups import GroupTask
from game.point_with_heading import PointWithHeading
from game.server.iadsnetwork.models import IadsNetworkJs
from game.settings import Settings
from game.theater import Player
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import (
    IadsBuildingGroundObject,
    SamGroundObject,
    TheaterGroundObject,
)
from game.utils import Heading
from game.theater.theatergroup import IadsGroundGroup, TheaterUnit

BACKBONE = "Red Comms Ushuaia Backbone"
SECTORS = ("Ground-1", "Ground-2", "Ground-7", "Red EWR Ushuaia")


def test_backbone_is_loaded_as_an_ushuaia_comms_site_on_land() -> None:
    campaign = Campaign.from_file(Path("resources/campaigns/gran_polvorin.yaml"))
    theater = campaign.load_theater(True)
    placements = [
        (cp, point)
        for cp in theater.controlpoints
        for point in cp.preset_locations.iads_connection_node
        if point.original_name == BACKBONE
    ]
    assert len(placements) == 1
    base, point = placements[0]
    assert base.name == "Ushuaia"
    assert theater.is_on_land(point, ignore_exclusion=True)
    assert "iads_config" not in campaign.data


@pytest.mark.parametrize("side", [Player.RED, Player.BLUE])
@pytest.mark.parametrize("range_nm", [15, 200])
def test_backbone_links_follow_coverage_and_remain_dashed_when_destroyed(
    side: Player,
    range_nm: int,
) -> None:
    campaign = Campaign.from_file(Path("resources/campaigns/gran_polvorin.yaml"))
    template = Mission()
    template.load_file("resources/campaigns/gran_polvorin.miz")
    groups = {
        group.name: group
        for country in template.coalition["red"].countries.values()
        for group in country.static_group + country.vehicle_group
    }
    settings = Settings()
    settings.set_plugin_option("skynetiads.commsRangeNm", range_nm)
    coalition = SimpleNamespace(player=side, game=SimpleNamespace(settings=settings))
    base: Any = SimpleNamespace(
        captured=side, coalition=coalition, is_friendly=lambda player: player == side
    )
    objectives = []
    for index, name in enumerate((*SECTORS, BACKBONE), 1):
        marker = groups[name]
        location = PresetLocation(
            name, marker.position, Heading.from_degrees(marker.units[0].heading)
        )
        objective: TheaterGroundObject
        kind: type[UnitType]
        if name == BACKBONE:
            objective = IadsBuildingGroundObject(
                name, "comms", location, base, GroupTask.COMMS
            )
            role, kind = IadsRole.CONNECTION_NODE, Fortification.Comms_tower_M
        else:
            objective = SamGroundObject(name, location, base, GroupTask.MERAD)
            role, kind = IadsRole.SAM, AirDefence.S_75M_Volhov
        position = PointWithHeading.from_point(location, location.heading)
        unit = TheaterUnit(index, name, kind, position, objective)
        group = IadsGroundGroup(index, name, position, [unit], objective)
        group.iads_role = role
        objective.groups.append(group)
        objectives.append(objective)
    network = IadsNetwork(True)
    network.initialize_network(iter(objectives))
    game: Any = SimpleNamespace(
        iads_considerate_culling=lambda _: False, skynet_culled=lambda _: False
    )
    nodes = network.skynet_nodes(game)
    expected = {
        objective.groups[0].group_name
        for objective in objectives[:-1]
        if objective.position.distance_to_point(objectives[-1].position)
        <= IadsRole.CONNECTION_NODE.connection_range(settings).meters
    }
    sam_nodes = [node for node in nodes if node.iads_role is IadsRole.SAM]
    if range_nm == 200:
        assert expected
    assert len(sam_nodes) == len(SECTORS)
    for node in sam_nodes:
        assert node.connections["ConnectionNode"] == (
            [objectives[-1].groups[0].units[0].unit_name]
            if node.dcs_name in expected
            else []
        )
    links = IadsNetworkJs.from_network(network).connections
    assert len(links) == len(expected)
    assert all(link.active and link.blue == side.is_blue for link in links)
    assert {link.connected for link in links} == (
        {objectives[-1].id} if expected else set()
    )
    objectives[-1].groups[0].units[0].alive = False
    links = IadsNetworkJs.from_network(network).connections
    assert len(links) == len(expected) and all(not link.active for link in links)
