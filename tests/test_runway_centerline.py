"""Precise runway geometry from DCS localizers, including reciprocal approaches."""

import math
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from dcs.mapping import Point
from dcs.terrain.falklands import Falklands

from game.dcs.beacons import Beacon, BeaconType, Beacons
from game.runways import runway_centerline


@pytest.mark.parametrize("name, course", [("07", 76.899460), ("25", 256.899460)])
def test_ushuaia_uses_its_dcs_localizer_axis(name: str, course: float) -> None:
    terrain = Falklands()
    theater = cast(Any, SimpleNamespace(terrain=terrain))
    airport = terrain.airports["Ushuaia"]
    result = runway_centerline(theater, airport, name)
    assert result is not None
    center, heading = result
    assert heading == pytest.approx(course)
    beacon = Beacons.with_id("airfield7_0", theater)
    assert beacon.position_x is not None and beacon.position_z is not None
    # The projected center and an ALIGN point must be on the same localizer axis.
    for point in (center, center.point_from_heading((heading + 180) % 360, 27780)):
        cross = (point.x - beacon.position_x) * math.sin(math.radians(heading)) - (
            point.y - beacon.position_z
        ) * math.cos(math.radians(heading))
        assert cross == pytest.approx(0, abs=1e-7)


def _airport() -> Any:
    approach = SimpleNamespace(
        name="09L", heading=90, beacons=[SimpleNamespace(id="left")]
    )
    opposite = SimpleNamespace(name="27R", heading=270, beacons=[])
    return SimpleNamespace(
        position=Point(500, 0, cast(Any, None)),
        runways=[SimpleNamespace(main=approach, opposite=opposite)],
    )


def _localizer(**kwargs: Any) -> Beacon:
    values: dict[str, Any] = dict(
        name="Test",
        callsign="TST",
        beacon_type=BeaconType.BEACON_TYPE_ILS_LOCALIZER,
        hertz=110000000,
        channel=None,
        position_x=100,
        position_z=1000,
        direction=90,
    )
    values.update(kwargs)
    return Beacon(**values)


def test_airport_reference_is_projected_onto_the_selected_runway() -> None:
    with patch("game.runways.RunwayData._get_beacon", return_value=_localizer()):
        result = runway_centerline(
            cast(Any, SimpleNamespace(terrain=None)), _airport(), "09L"
        )
    assert result is not None
    center, heading = result
    assert center.x == pytest.approx(100)
    assert center.y == pytest.approx(0)
    assert heading == 90


@pytest.mark.parametrize(
    "changes",
    [
        {"position_x": None},
        {"position_z": None},
        {"direction": None},
        {"direction": float("nan")},
        {"direction": 0},
        {"position_x": 1000000},
        {"beacon_type": BeaconType.BEACON_TYPE_ILS_GLIDESLOPE},
    ],
)
def test_missing_or_unrelated_geometry_is_not_used(changes: dict[str, Any]) -> None:
    with patch(
        "game.runways.RunwayData._get_beacon", return_value=_localizer(**changes)
    ):
        assert (
            runway_centerline(
                cast(Any, SimpleNamespace(terrain=None)), _airport(), "09L"
            )
            is None
        )


def test_parallel_runways_are_not_matched_by_heading_alone() -> None:
    with patch("game.runways.RunwayData._get_beacon") as get_beacon:
        assert runway_centerline(cast(Any, None), _airport(), "09R") is None
    get_beacon.assert_not_called()


def test_legacy_beacon_data_has_no_geometry() -> None:
    beacon = Beacon(
        "Test", "TST", BeaconType.BEACON_TYPE_ILS_LOCALIZER, 110000000, None
    )
    assert beacon.position_x is None
    assert beacon.position_z is None
    assert beacon.direction is None
