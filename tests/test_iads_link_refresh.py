"""A change to one site redraws the links of every site touching what changed."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroup import IadsGroundGroup


class _Group(IadsGroundGroup):
    """A real IadsGroundGroup, built without its constructor so no theater is needed."""

    def __init__(self, ground_object: Any, role: IadsRole) -> None:
        self.ground_object = ground_object
        self.iads_role = role
        self.name = f"{ground_object.name} group"
        self.id = ground_object.name
        self.units = [
            cast(
                Any,
                SimpleNamespace(
                    alive=True,
                    detection_range=SimpleNamespace(meters=50_000.0),
                    unit_type=None,
                ),
            )
        ]

    __eq__ = object.__eq__
    __hash__ = object.__hash__


class _Site:
    def __init__(self, name: str, category: str, role: IadsRole, blue: bool) -> None:
        self.name = name
        self.original_name = name
        self.category = category
        self.carries_gps_jammer = False
        self.control_point = SimpleNamespace(captured=SimpleNamespace(is_blue=blue))
        self.groups = [_Group(self, role)]

    def kill(self) -> None:
        for unit in self.groups[0].units:
            unit.alive = False


class _Events:
    def __init__(self) -> None:
        self.nodes: list[IadsNetworkNode] = []

    def update_iads_node(self, node: IadsNetworkNode) -> None:
        self.nodes.append(node)

    def update_tgo(self, tgo: Any) -> None:
        pass

    def delete_iads_connection(self, connection: Any) -> None:
        pass


def _network(*sites: _Site) -> IadsNetwork:
    network = IadsNetwork.__new__(IadsNetwork)
    network.advanced_iads = True
    network.iads_config = {site.original_name: [] for site in sites}
    network.nodes = []
    network.ground_objects = {site.original_name: cast(Any, site) for site in sites}
    network._state_map = None
    return network


def _node(network: IadsNetwork, site: _Site, *links: _Site) -> IadsNetworkNode:
    node = IadsNetworkNode(site.groups[0])
    for link in links:
        node.add_connection_for_group(link.groups[0])
    network.nodes.append(node)
    return node


def _sites() -> tuple[_Site, _Site, _Site]:
    return (
        _Site("JAGUAR", "commandcenter", IadsRole.COMMAND_CENTER, blue=False),
        _Site("BADGER", "aa", IadsRole.SAM, blue=False),
        _Site("OTTER", "aa", IadsRole.SAM, blue=True),
    )


def test_a_command_centre_going_down_redraws_the_links_to_it() -> None:
    centre, sam, other_side = _sites()
    network = _network(centre, sam, other_side)
    _node(network, centre)
    reporting = _node(network, sam, centre)
    unrelated = _node(network, other_side)
    network.state_map  # the map has been drawn once already
    centre.kill()

    events = _Events()
    network.update_tgo(cast(Any, centre), cast(Any, events))

    assert reporting in events.nodes
    assert unrelated not in events.nodes


def test_bringing_it_back_redraws_them_too() -> None:
    centre, sam, other_side = _sites()
    network = _network(centre, sam, other_side)
    centre.kill()
    _node(network, centre)
    reporting = _node(network, sam, centre)
    network.state_map
    for unit in centre.groups[0].units:
        unit.alive = True

    events = _Events()
    network.update_tgo(cast(Any, centre), cast(Any, events))

    assert reporting in events.nodes
