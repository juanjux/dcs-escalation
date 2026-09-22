"""The theatre AEW&C station goes over land, and never twice on the same base.

Every boat is already a station. Taking the "land" pick from the fleet put the theatre
station on a hull -- an amphib is not a carrier, so it was eligible -- and a carrier
that won the pick was planned twice, two racetracks on one boat.
"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from game.utils import meters


def _cp(name: str, threat_distance: float, is_fleet: bool = False) -> Any:
    cp = MagicMock()
    cp.name = name
    cp.is_fleet = is_fleet
    cp.position = name
    cp._threat_distance = threat_distance
    return cp


def _finder(control_points: list[Any]) -> Any:
    from game.commander.objectivefinder import ObjectiveFinder

    finder = ObjectiveFinder.__new__(ObjectiveFinder)
    zones = MagicMock()
    zones.distance_to_threat = lambda pos: meters(
        next(cp._threat_distance for cp in control_points if cp.position == pos)
    )
    game = MagicMock()
    game.threat_zone_for = lambda _side: zones
    finder.game = game
    finder.is_player = MagicMock()
    finder.friendly_control_points = lambda: iter(control_points)  # type: ignore[method-assign]
    return finder


def test_the_farthest_airfield_wins() -> None:
    cps = [_cp("Incirlik", 200_000), _cp("Hatay", 40_000)]
    assert _finder(cps).farthest_friendly_airfield().name == "Incirlik"


def test_a_boat_is_never_the_land_station() -> None:
    """The amphib sat farther from the threat than any field, and took the station."""
    cps = [_cp("Tarawa", 300_000, is_fleet=True), _cp("Incirlik", 200_000)]
    assert _finder(cps).farthest_friendly_airfield().name == "Incirlik"


def test_a_carrier_only_coalition_has_no_land_station() -> None:
    """Not an error: its boats are stations already."""
    cps = [_cp("CVN-73", 300_000, is_fleet=True)]
    assert _finder(cps).farthest_friendly_airfield() is None


def test_an_off_map_spawn_is_not_a_station() -> None:
    from game.theater.controlpoint import OffMapSpawn

    off_map = MagicMock(spec=OffMapSpawn)
    off_map.is_fleet = False
    # Farther from the threat than the field, so only the isinstance check excludes it.
    off_map.position = "off map"
    off_map._threat_distance = 900_000
    cps: list[Any] = [off_map, _cp("Incirlik", 200_000)]
    assert _finder(cps).farthest_friendly_airfield().name == "Incirlik"
