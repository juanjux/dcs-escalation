"""Ships stay off the grid ashore.

A ship makes its own power and carries its own radios, and in Escalation it sails.
Wired by range like a site ashore, it was tied to whatever plant stood on the coast
where it started and kept that link wherever it went.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.theatergroundobject import ShipGroundObject
from tests.test_iads_late_arrivals import _Group, _network, _node, _Site, _wired


def _ship(name: str, x: float) -> Any:
    """A ship's own class, which is what the network goes by, filled in like _Site."""
    ship: Any = ShipGroundObject.__new__(ShipGroundObject)
    site = _Site(name, "ship", x)
    for field in ("name", "original_name", "category", "position", "control_point"):
        setattr(ship, field, getattr(site, field))
    ship.groups = [_Group(ship, IadsRole.EWR)]
    return ship


def test_a_ship_is_not_wired_to_the_shore_by_range(monkeypatch: Any) -> None:
    """It makes its own power and carries its own radios."""
    ship = _ship("ISOPOD", 0.0)
    power = _Site("WRASSE", "power", 1000.0, IadsRole.POWER_SOURCE)
    power.is_dead = False  # type: ignore[attr-defined]
    comms = _Site("FENNEC", "comms", 2000.0, IadsRole.CONNECTION_NODE)
    network = _network(ship, power, comms)
    node = _node(network, ship)
    monkeypatch.setattr(
        IadsNetwork, "_belongs_in_the_network", staticmethod(lambda go: go is ship)
    )
    monkeypatch.setattr(IadsNetwork, "_is_friendly", lambda self, node, tgo: True)
    events: Any = SimpleNamespace(update_iads_node=lambda node: None)

    assert network.enrol_sites_that_arrived_late() == []
    network._update_network(cast(Any, power), events)

    assert _wired(node) == []


def test_a_ship_wired_by_range_is_taken_off_the_grid() -> None:
    """Saves carry the links a ship was given where it started, however far it has
    sailed since. A ship the campaign wired itself keeps what the campaign wrote."""
    ship = _ship("ISOPOD", 0.0)
    wired = _ship("Naval-9", 0.0)
    power = _Site("WRASSE", "power", 1000.0, IadsRole.POWER_SOURCE)
    network = _network(ship, wired, power)
    network.iads_config = {"Naval-9": ["WRASSE"]}
    loose, kept = _node(network, ship), _node(network, wired)
    for node in (loose, kept):
        node.add_connection_for_group(power.groups[0])
        node.add_connection_for_group(node.group)

    assert network.unwire_ships() == ["ISOPOD"]
    assert _wired(loose) == [] and len(loose.connections) == 1
    assert _wired(kept) == ["WRASSE"]
    assert network.unwire_ships() == []
