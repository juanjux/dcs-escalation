"""A site that arrived after the network was built.

Saves carry their IADS network pickled, and the rebuild that enrols the sites a
campaign never named runs once. New objectives are registered into a save after that
-- the GPS jamming site every faction gained is the case that showed it -- so one
arriving later sat in the theater with nothing cueing it and no plant to bomb: the
map drew it with no grid link at all.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroup import IadsGroundGroup


class _Group(IadsGroundGroup):
    """A real IadsGroundGroup: the network checks the class before it will take a
    connection, built without its constructor so no theater is needed."""

    def __init__(self, ground_object: Any, role: IadsRole) -> None:
        self.ground_object = ground_object
        self.iads_role = role
        self.name = f"{ground_object.name} group"
        self.id = ground_object.name
        self.units = [cast(Any, SimpleNamespace(alive=True))]

    # The network finds a node by comparing groups, and the dataclass equality reads
    # fields this double does not have.
    __eq__ = object.__eq__
    __hash__ = object.__hash__


class _Site:
    """As much of an objective as the network touches."""

    def __init__(
        self, name: str, category: str, x: float, role: IadsRole = IadsRole.NO_BEHAVIOR
    ) -> None:
        self.name = name
        self.original_name = name
        self.category = category
        self.position = SimpleNamespace(
            distance_to_point=lambda other, mine=x: abs(other.x - mine), x=x
        )
        self.groups = [_Group(self, role)]
        # The network reaches the campaign's settings through the objective, and a
        # double that stops short of a game gets the defaults.
        self.control_point = SimpleNamespace(coalition=None)


def _network(*sites: _Site) -> IadsNetwork:
    network = IadsNetwork.__new__(IadsNetwork)
    network.advanced_iads = True
    network.iads_config = {}
    network.nodes = []
    network.ground_objects = {site.original_name: cast(Any, site) for site in sites}
    network._state_map = None
    return network


def _node(network: IadsNetwork, site: _Site) -> IadsNetworkNode:
    node = IadsNetworkNode(site.groups[0])
    network.nodes.append(node)
    return node


def _wired(node: IadsNetworkNode) -> list[str]:
    return sorted(
        group.ground_object.name
        for group in node.connections.values()
        if group.iads_role.is_comms_or_power
    )


def test_a_site_with_no_grid_is_wired_to_what_is_in_range(monkeypatch: Any) -> None:
    jammer = _Site("GUPPY", "ewr", 0.0)
    power = _Site("RAGDOLL", "power", 1000.0, IadsRole.POWER_SOURCE)
    comms = _Site("PIRANHA", "comms", 2000.0, IadsRole.CONNECTION_NODE)
    network = _network(jammer, power, comms)
    node = _node(network, jammer)
    monkeypatch.setattr(
        IadsNetwork, "_belongs_in_the_network", staticmethod(lambda go: go is jammer)
    )
    monkeypatch.setattr(IadsNetwork, "_is_friendly", lambda self, node, tgo: True)

    assert network.enrol_sites_that_arrived_late() == ["GUPPY"]
    assert _wired(node) == ["PIRANHA", "RAGDOLL"]


def test_calling_it_again_wires_nothing_twice(monkeypatch: Any) -> None:
    """It runs on every load, so a second pass has to be a no-op."""
    jammer = _Site("GUPPY", "ewr", 0.0)
    power = _Site("RAGDOLL", "power", 1000.0, IadsRole.POWER_SOURCE)
    network = _network(jammer, power)
    node = _node(network, jammer)
    monkeypatch.setattr(
        IadsNetwork, "_belongs_in_the_network", staticmethod(lambda go: go is jammer)
    )
    monkeypatch.setattr(IadsNetwork, "_is_friendly", lambda self, node, tgo: True)

    network.enrol_sites_that_arrived_late()
    before = len(node.connections)

    assert network.enrol_sites_that_arrived_late() == []
    assert len(node.connections) == before


def test_a_site_the_campaign_named_is_left_to_its_config(monkeypatch: Any) -> None:
    """What the author wrote is the author's. A named site with a deliberately empty
    dependency list is not a site to go wiring by range."""
    site = _Site("Ground-15", "ewr", 0.0)
    power = _Site("RAGDOLL", "power", 1000.0, IadsRole.POWER_SOURCE)
    network = _network(site, power)
    network.iads_config = {"Ground-15": []}
    node = _node(network, site)
    monkeypatch.setattr(
        IadsNetwork, "_belongs_in_the_network", staticmethod(lambda go: go is site)
    )

    assert network.enrol_sites_that_arrived_late() == []
    assert _wired(node) == []


def test_a_site_that_only_points_at_itself_counts_as_unwired() -> None:
    """Its own point defence is not a grid link, and it is what the map drew as a
    connection going nowhere."""
    site = _Site("GUPPY", "ewr", 0.0, IadsRole.POINT_DEFENSE)
    node = IadsNetworkNode(site.groups[0])
    node.add_connection_for_group(site.groups[0])

    assert IadsNetwork._has_grid(node) is False


def test_a_site_already_on_the_grid_is_left_alone() -> None:
    site = _Site("ORYX", "ewr", 0.0)
    power = _Site("RAGDOLL", "power", 1000.0, IadsRole.POWER_SOURCE)
    node = IadsNetworkNode(site.groups[0])
    node.add_connection_for_group(power.groups[0])

    assert IadsNetwork._has_grid(node) is True


def test_a_site_the_campaign_did_not_name_keeps_its_grid_when_it_changes(
    monkeypatch: Any,
) -> None:
    """A unit dying or being repaired rebuilds the site's node. Rebuilt from a config
    that never named the site, it came back with no power station and no comms tower,
    and bombing both left it running."""
    site = _Site("TURKEY", "aa", 0.0, IadsRole.SAM_AS_EWR)
    power = _Site("MOA", "power", 1000.0, IadsRole.POWER_SOURCE)
    comms = _Site("IMPALA", "comms", 2000.0, IadsRole.CONNECTION_NODE)
    named = _Site("Ground-7", "aa", 900000.0, IadsRole.SAM)
    network = _network(site, power, comms, named)
    network.iads_config = {"Ground-7": ["MOA"]}
    monkeypatch.setattr(
        IadsNetwork,
        "_belongs_in_the_network",
        staticmethod(lambda go: go in (site, named)),
    )
    monkeypatch.setattr(IadsNetwork, "_is_friendly", lambda self, node, tgo: True)
    _node(network, site)
    network.enrol_sites_that_arrived_late()
    events: Any = SimpleNamespace(
        delete_iads_connection=lambda cid: None, update_iads_node=lambda node: None
    )

    network._update_tgo(cast(Any, site), events)
    network._update_tgo(cast(Any, named), events)

    [turkey] = [n for n in network.nodes if n.group.ground_object is site]
    [ground_7] = [n for n in network.nodes if n.group.ground_object is named]
    assert _wired(turkey) == ["IMPALA", "MOA"]
    # A site the campaign named still gets what the campaign wrote, however far.
    assert _wired(ground_7) == ["MOA"]
