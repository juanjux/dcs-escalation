"""Which runway the campaign reports as active."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from dcs.terrain.afghanistan import Afghanistan

from game.ato.flightplans.alignpoint import align_waypoint
from game.runways import CALM_WIND, RunwayAssigner, RunwayData
from game.theater.controlpoint import Airfield
from game.theater.player import Player
from game.utils import Heading, knots


def _runway(name: str, heading: int, ils: bool = False) -> RunwayData:
    return RunwayData(
        "Mount Pleasant",
        runway_heading=Heading.from_degrees(heading),
        runway_name=name,
        ils=SimpleNamespace(mhz=111.9) if ils else None,  # type: ignore[arg-type]
    )


#: Mount Pleasant: two runways, with the ILS on the second.
MOUNT_PLEASANT = [
    _runway("23", 230),
    _runway("05", 50),
    _runway("10", 100),
    _runway("28", 280, ils=True),
]


def _chosen(
    monkeypatch: pytest.MonkeyPatch,
    from_degrees: int,
    mps: float,
    runways: list[RunwayData] = MOUNT_PLEASANT,
) -> str:
    """Wind in the form DCS stores it: the direction it blows towards, in m/s."""
    conditions = SimpleNamespace(
        weather=SimpleNamespace(
            wind=SimpleNamespace(
                at_0m=SimpleNamespace(
                    direction=Heading.from_degrees(from_degrees).opposite.degrees,
                    speed=mps,
                )
            )
        )
    )
    monkeypatch.setattr(
        RunwayData, "for_pydcs_airport", staticmethod(lambda *_: iter(runways))
    )
    assigner = RunwayAssigner(conditions)  # type: ignore[arg-type]
    return assigner.get_preferred_runway(None, None).runway_name  # type: ignore[arg-type]


def test_calm_air_uses_the_instrument_runway(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two knots from the north-east would otherwise select 05, which has no ILS."""
    assert _chosen(monkeypatch, from_degrees=29, mps=1.0) == "28"


def test_a_real_wind_still_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty knots down runway 05 selects it, ILS or not."""
    assert _chosen(monkeypatch, from_degrees=50, mps=10.0) == "05"


def test_the_threshold_is_where_the_wind_takes_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calm = CALM_WIND.meters_per_second
    assert _chosen(monkeypatch, from_degrees=29, mps=calm - 0.01) == "28"
    assert _chosen(monkeypatch, from_degrees=29, mps=calm) == "05"


def test_calm_air_at_a_field_with_no_aid_still_reads_the_wind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bare = [_runway("23", 230), _runway("05", 50)]

    assert _chosen(monkeypatch, from_degrees=29, mps=1.0, runways=bare) == "05"


def test_the_calm_threshold_is_five_knots() -> None:
    assert CALM_WIND == knots(5)


@pytest.mark.parametrize("from_degrees", [0, 14, 90, 194, 270, 359])
def test_zero_wind_has_no_preferred_direction(
    monkeypatch: pytest.MonkeyPatch, from_degrees: int
) -> None:
    bare = [_runway("11", 110), _runway("29", 290)]
    assert _chosen(monkeypatch, from_degrees, mps=0, runways=bare) == "11"


@pytest.mark.parametrize("from_degrees", [0, 90, 194, 270])
def test_zero_wind_keeps_ils_priority_but_not_an_arbitrary_direction(
    monkeypatch: pytest.MonkeyPatch, from_degrees: int
) -> None:
    runways = [
        _runway("11", 110),
        _runway("29", 290, ils=True),
        _runway("01", 10, ils=True),
    ]
    assert _chosen(monkeypatch, from_degrees, mps=0, runways=runways) == "29"


@pytest.mark.parametrize("direction", [0, 90, 194, 270, 359])
def test_kabul_zero_surface_wind_aligns_with_runway_11(direction: int) -> None:
    terrain = Afghanistan()
    theater: Any = SimpleNamespace(terrain=terrain)
    arrival = Airfield(terrain.airports["Kabul"], theater, Player.BLUE)
    conditions: Any = SimpleNamespace(
        weather=SimpleNamespace(
            wind=SimpleNamespace(at_0m=SimpleNamespace(direction=direction, speed=0))
        )
    )
    runway = arrival.active_runway(theater, conditions, {})
    assert runway.runway_name == "11"
    flight: Any = SimpleNamespace(
        arrival=arrival,
        is_helo=False,
        coalition=SimpleNamespace(
            game=SimpleNamespace(
                conditions=conditions,
                settings=SimpleNamespace(
                    align_before_landing=True, align_distance_nm=15
                ),
            )
        ),
    )
    waypoint = align_waypoint(flight)
    assert waypoint is not None
    assert waypoint.description == "Established on Kabul runway 11"
    approach_heading = waypoint.position.heading_between_point(arrival.position)
    assert approach_heading == pytest.approx(110)
