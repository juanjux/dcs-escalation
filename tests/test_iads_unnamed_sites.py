"""Current air-defence sites, ships and infrastructure participate automatically."""

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


def test_infrastructure_also_belongs() -> None:
    """Infrastructure needs its own nodes to connect to other infrastructure."""
    for category in ("comms", "power"):
        assert IadsNetwork._belongs_in_the_network(
            _of(IadsBuildingGroundObject, category)
        )


def test_an_ordinary_building_does_not() -> None:
    assert not IadsNetwork._belongs_in_the_network(_of(BuildingGroundObject, "factory"))
