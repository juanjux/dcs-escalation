"""Empty emplacements retain inactive IADS links without spawning equipment."""

from types import SimpleNamespace
from typing import Any

import pytest
from dcs import Point
from dcs.terrain import Caucasus

from game.data.groups import GroupTask
from game.server.iadsnetwork.models import IadsConnectionJs
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsexplain import describe
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import IadsBuildingGroundObject, SamGroundObject
from game.theater.theatergroup import IadsGroundGroup
from tests.test_iads_state import _unit


def site(name: str, category: str = "aa", x: float = 0) -> Any:
    cp: Any = SimpleNamespace(captured=Player.RED, coalition=None)
    cp.is_friendly = lambda player: player == cp.captured
    if category == "comms":
        return IadsBuildingGroundObject(
            name,
            category,
            PresetLocation(name, Point(x, 0, Caucasus())),
            cp,
            GroupTask.COMMS,
        )
    obj = SamGroundObject(
        name, PresetLocation(name, Point(x, 0, Caucasus())), cp, GroupTask.LORAD
    )
    obj.category = category
    return obj


def deploy(obj: Any, role: IadsRole = IadsRole.SAM) -> None:
    group = IadsGroundGroup(1, obj.name, obj.position, [_unit()], obj)
    group.iads_role = role
    obj.groups = [group]


@pytest.mark.parametrize("configured", [True, False])
def test_capture_keeps_links_and_redeployment_reactivates(configured: bool) -> None:
    sam, tower = site("BATTERY"), site("TOWER", "comms", 1000)
    deploy(sam)
    deploy(tower, IadsRole.CONNECTION_NODE)
    network = IadsNetwork(True, [{"BATTERY": ["TOWER"]}] if configured else [])
    network.initialize_network(iter([sam, tower]))
    old_node = network.node_for_tgo(sam)
    assert old_node is not None
    assert IadsConnectionJs.connections_for_node(old_node, network)[0].active

    # Capture clears mobile units but retains the site's infrastructure.
    sam.clear()
    sam.control_point.captured = tower.control_point.captured = Player.BLUE
    events = GameUpdateEvents()
    network.update_tgo(sam, events)
    node = network.node_for_tgo(sam)
    assert node is not None and node.is_empty_site
    assert not sam.groups
    assert node in events.updated_iads
    links = IadsConnectionJs.connections_for_node(node, network)
    assert len(links) == 1 and not links[0].active and links[0].blue
    assert links[0].connected == tower.id
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is IadsState.DESTROYED
    assert "Empty site" in status.reason
    picture = describe(sam, network)
    assert picture.off is None
    assert picture.gets[0].title == "TOWER"
    assert picture.gets[0].chip == "INACTIVE"
    assert describe(tower, network).gives[0].places[0].objective is sam
    assert not network.renew_stale_nodes()
    fake_game: Any = SimpleNamespace(
        iads_considerate_culling=lambda obj: False, skynet_culled=lambda obj: False
    )
    assert not network.skynet_nodes(fake_game)

    deploy(sam)
    network.update_tgo(sam, GameUpdateEvents())
    node = network.node_for_tgo(sam)
    assert node is not None and not node.is_empty_site
    assert len(network.nodes) == 1
    assert IadsConnectionJs.connections_for_node(node, network)[0].active


@pytest.mark.parametrize("category", ["aa", "ewr"])
def test_existing_save_restores_empty_sites_once(category: str) -> None:
    sam, tower = site("BATTERY", category), site("TOWER", "comms", 1000)
    deploy(tower, IadsRole.CONNECTION_NODE)
    network = IadsNetwork(True, [{"BATTERY": ["TOWER"]}])
    network.ground_objects = {s.original_name: s for s in (sam, tower)}
    assert network.restore_empty_sites() == ["BATTERY"]
    node = network.nodes[0]
    connections = dict(node.connections)
    assert network.restore_empty_sites() == []
    assert node.connections == connections
    assert network.renew_stale_nodes() == []
    assert not sam.groups
    assert node.group.iads_role is (IadsRole.EWR if category == "ewr" else IadsRole.SAM)


def test_empty_site_does_not_draw_links_to_enemy_infrastructure() -> None:
    sam, tower = site("BATTERY"), site("TOWER", "comms", 1000)
    sam.control_point.captured = Player.BLUE
    deploy(tower, IadsRole.CONNECTION_NODE)
    network = IadsNetwork(True, [{"BATTERY": ["TOWER"]}])
    network.initialize_network(iter([sam, tower]))
    assert not IadsConnectionJs.connections_for_node(network.nodes[0], network)
    assert not describe(sam, network).gets
