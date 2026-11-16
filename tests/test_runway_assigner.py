"""Which runway the campaign reports as active."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from dcs.terrain.afghanistan import Afghanistan
from dcs.terrain.nevada import Nevada

from game.ato.flightplans.alignpoint import align_waypoint
from game.runways import RunwayAssigner, RunwayData, runway_centerline
from game.theater.controlpoint import Airfield
from game.theater.player import Player
from game.utils import Heading, nautical_miles


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
    airport: Any = SimpleNamespace(runways=[])
    return assigner.get_preferred_runway(None, airport).runway_name  # type: ignore[arg-type]


def test_zero_wind_uses_the_instrument_runway(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _chosen(monkeypatch, from_degrees=29, mps=0.0) == "28"


def test_a_real_wind_still_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty knots down runway 05 selects it, ILS or not."""
    assert _chosen(monkeypatch, from_degrees=50, mps=10.0) == "05"


@pytest.mark.parametrize("speed", [1.2, 2.3260408068684355, 2.58, 10.0])
def test_meaningful_headwind_wins_over_ils(
    monkeypatch: pytest.MonkeyPatch, speed: float
) -> None:
    assert _chosen(monkeypatch, from_degrees=29, mps=speed) == "05"


def test_meaningful_headwind_wins_at_an_airfield_without_ils(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bare = [_runway("23", 230), _runway("05", 50)]

    assert _chosen(monkeypatch, from_degrees=29, mps=1.2, runways=bare) == "05"


@pytest.mark.parametrize("from_degrees, speed", [(0, 0.5), (88, 15.0)])
def test_negligible_headwind_uses_the_calm_wind_preference(
    monkeypatch: pytest.MonkeyPatch, from_degrees: int, speed: float
) -> None:
    # Use a weak direct wind and a strong nearly perpendicular wind.
    runways = [_runway("36", 0), _runway("18", 180, ils=True)]
    assert _chosen(monkeypatch, from_degrees, mps=speed, runways=runways) == "18"


def test_headwind_projection_uses_the_surveyed_runway_course(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runways = [_runway("36", 0), _runway("18", 180, ils=True)]
    monkeypatch.setattr(
        "game.runways.runway_centerline",
        lambda _theater, _airport, name: (None, {"36": 20, "18": 200}[name]),
    )
    assert _chosen(monkeypatch, from_degrees=100, mps=10.0, runways=runways) == "36"


def test_instrument_runway_is_still_preferred_when_headwinds_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parallel = [_runway("09L", 90), _runway("09R", 90, ils=True)]
    assert _chosen(monkeypatch, 90, mps=4, runways=parallel) == "09R"


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


@pytest.mark.parametrize(
    "airfield, direction, speed, expected_runway",
    [
        ("Tonopah Test Range", 160, 2.3260408068684355, "32"),
        ("Groom Lake", 48, 1.5766249853798402, "32"),
        ("Groom Lake", 336, 0, "32"),
        ("Groom Lake", 336, 7, "14"),
    ],
)
def test_nevada_runway_selection_and_align(
    airfield: str, direction: int, speed: float, expected_runway: str
) -> None:
    terrain = Nevada()
    theater: Any = SimpleNamespace(terrain=terrain)
    arrival = Airfield(terrain.airports[airfield], theater, Player.BLUE)
    conditions: Any = SimpleNamespace(
        weather=SimpleNamespace(
            wind=SimpleNamespace(
                at_0m=SimpleNamespace(direction=direction, speed=speed)
            )
        )
    )
    assert arrival.active_runway(theater, conditions, {}).runway_name == expected_runway
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
    assert waypoint.description == f"Established on {airfield} runway {expected_runway}"
    axis = runway_centerline(theater, arrival.dcs_airport, expected_runway)
    assert axis is not None
    center, course = axis
    expected = center.point_from_heading(
        (course + 180) % 360, nautical_miles(15).meters
    )
    assert waypoint.position.distance_to_point(expected) < 1e-7
