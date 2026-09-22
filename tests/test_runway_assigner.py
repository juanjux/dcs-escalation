"""Which runway the campaign reports as active."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.runways import CALM_WIND, RunwayAssigner, RunwayData
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
