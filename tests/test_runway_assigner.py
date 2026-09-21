"""Which runway the campaign calls the active one.

Two knots of breeze used to be enough to send everybody to a bare strip at a field
whose instrument runway was sitting there unused -- and at a field with more than one
strip, to the one the airfield's own reference point is not on, which is what the
approach course of a flight plan gets drawn through.
"""

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


#: Mount Pleasant: two strips, and the instrument aid is on the second one.
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
    """Wind as DCS gives it: the direction it blows towards, in m/s."""
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
    """Two knots from the north-east would otherwise pick 05, which has nothing."""
    assert _chosen(monkeypatch, from_degrees=29, mps=1.0) == "28"


def test_a_real_wind_still_decides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Twenty knots down the 05 is a reason to use it, aid or no aid."""
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


def test_the_calm_threshold_is_a_breeze_and_not_a_gale() -> None:
    assert CALM_WIND == knots(5)
