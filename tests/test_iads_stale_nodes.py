"""A site whose groups were replaced gets its IADS node renewed.

GeneraLLM's rebuild replaced a site's groups and left its node on the old one: Skynet
was handed a group the mission does not contain, and the map read the site as standing
and autonomous with every unit of the new battery dead and under repair.
"""

from __future__ import annotations

from typing import Any

from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
from game.theater.iadsnetwork.iadsrole import IadsRole
from tests.test_iads_late_arrivals import _Group, _network, _node, _Site


def test_a_node_on_a_group_its_site_no_longer_has_is_renewed(monkeypatch: Any) -> None:
    rebuilt = _Site("HIPPO", "aa", 0.0, IadsRole.SAM)
    untouched = _Site("MAVERICK", "aa", 50000.0, IadsRole.SAM)
    network = _network(rebuilt, untouched)
    # The group the site had before it was rebuilt, which the node still points at.
    network.nodes.append(IadsNetworkNode(_Group(rebuilt, IadsRole.SAM)))
    _node(network, untouched)
    renewed: list[Any] = []
    monkeypatch.setattr(
        IadsNetwork, "update_tgo", lambda self, tgo, events: renewed.append(tgo)
    )

    assert network.renew_stale_nodes() == ["HIPPO"]
    assert renewed == [rebuilt]
