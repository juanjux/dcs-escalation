"""What belongs in the IADS network, whoever built it.

A campaign with an iads_config got its network from that config, and only the keys of
it became nodes. Anything the author never named -- an anonymous Ground-N or Naval-N
slot, a GPS jamming site added to the factions long after the campaign was written --
was left outside however much it belonged in one: not cued, not directed, and bombing
the power station beside it changed nothing.

Both paths now ask the same question, which is the one below.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.theatergroundobject import (
    BuildingGroundObject,
    IadsBuildingGroundObject,
    IadsGroundObject,
)


def _of(kind: Any, category: str = "aa") -> Any:
    """One of these objectives, built without running its constructor.

    The predicate looks at the class and the category and nothing else.
    """
    site = kind.__new__(kind)
    site.category = category
    return site


def test_an_air_defence_site_belongs() -> None:
    assert IadsNetwork._belongs_in_the_network(_of(IadsGroundObject))


def test_a_fleet_belongs() -> None:
    # NavalGroundObject is abstract, so this is the concrete one a campaign places.
    from game.theater.theatergroundobject import ShipGroundObject

    assert IadsNetwork._belongs_in_the_network(_of(ShipGroundObject, "ship"))


def test_a_command_centre_belongs() -> None:
    assert IadsNetwork._belongs_in_the_network(
        _of(IadsBuildingGroundObject, "commandcenter")
    )


def test_other_infrastructure_does_not() -> None:
    """Comms and power are connections of a node, never nodes themselves."""
    for category in ("comms", "power"):
        assert not IadsNetwork._belongs_in_the_network(
            _of(IadsBuildingGroundObject, category)
        )


def test_an_ordinary_building_does_not() -> None:
    assert not IadsNetwork._belongs_in_the_network(_of(BuildingGroundObject, "factory"))
