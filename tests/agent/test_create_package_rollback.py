"""A package spec the API rejects must leave the ATO as it found it.

``plan_mission`` claims aircraft and pilots before the package is armed, and the
package joins the ATO before its loadouts, offsets and TOT are applied. A bad
loadout name therefore used to return an error AND leave the package behind: no
TOT, no rationale, and the crews still tasked, so retrying the same spec answered
"already tasked".
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from game.agent import planner, schemas, views
from game.ato.airtaaskingorder import AirTaskingOrder
from game.ato.package import Package


class _Flight:
    def __init__(self) -> None:
        self.id = "flight-1"
        self.cargo = None
        self.returned = False

    def return_pilots_and_aircraft(self) -> None:
        self.returned = True


@pytest.fixture
def flight() -> _Flight:
    return _Flight()


@pytest.fixture
def package(flight: _Flight) -> Package:
    db: Any = SimpleNamespace(remove=lambda _id: None)
    target: Any = SimpleNamespace(name="Groom Lake")
    package = Package(target=target, db=db)
    package.flights.append(flight)  # type: ignore[arg-type]
    return package


@pytest.fixture
def ato() -> AirTaskingOrder:
    return AirTaskingOrder()


@pytest.fixture
def game(ato: AirTaskingOrder) -> Any:
    return SimpleNamespace(
        conditions=SimpleNamespace(start_time=datetime(2026, 9, 10, 12, 0)),
        theater=object(),
        db=SimpleNamespace(flights=object()),
        settings=object(),
    )


@pytest.fixture(autouse=True)
def stubs(
    monkeypatch: pytest.MonkeyPatch, ato: AirTaskingOrder, package: Package
) -> None:
    """Everything create_packages reaches for outside itself."""
    coalition: Any = SimpleNamespace(ato=ato)
    monkeypatch.setattr(views, "coalition_for_side", lambda *_a: coalition)
    monkeypatch.setattr(
        planner, "resolve_target", lambda *_a: SimpleNamespace(name="Groom Lake")
    )
    monkeypatch.setattr(
        planner, "_diagnose_flights", lambda *_a: [(0, "CAS from somewhere", None)]
    )
    monkeypatch.setattr(planner, "_clamped_count", lambda *_a: 2)
    monkeypatch.setattr(planner, "_preferred_aircraft", lambda *_a: None)
    monkeypatch.setattr(
        planner,
        "PackageFulfiller",
        lambda *_a, **_k: SimpleNamespace(plan_mission=lambda *_b, **_c: package),
    )


def _spec() -> schemas.PackageSpec:
    return schemas.PackageSpec(
        target_id="Groom Lake",
        flights=[schemas.FlightSpec(task="CAS", count=2, loadout="Empty")],
        rationale="hold the ridge",
    )


def test_a_rejected_spec_leaves_no_package_behind(
    monkeypatch: pytest.MonkeyPatch, game: Any, ato: AirTaskingOrder, flight: _Flight
) -> None:
    def explode(*_a: object) -> None:
        raise ValueError("no loadout named 'Empty' for Su-27")

    monkeypatch.setattr(planner, "_apply_loadouts", explode)
    (result,) = planner.create_packages(game, "red", [_spec()])
    assert not result.ok
    assert "no loadout named" in (result.error or "")
    assert ato.packages == []
    assert flight.returned, "the crews stayed tasked, so a retry says already tasked"


def test_a_spec_that_works_is_kept(
    monkeypatch: pytest.MonkeyPatch, game: Any, ato: AirTaskingOrder, flight: _Flight
) -> None:
    for name in (
        "_apply_loadouts",
        "_apply_tot_offsets",
        "_apply_remain",
        "_apply_tot",
    ):
        monkeypatch.setattr(planner, name, lambda *_a: None)
    monkeypatch.setattr(
        views,
        "build_package",
        lambda index, _pkg: views.PackageView(
            index=index, target="Groom Lake", task="CAS", tot="12:30", flights=[]
        ),
    )
    monkeypatch.setattr(views, "idle_flyable_total", lambda *_a: 0)
    (result,) = planner.create_packages(game, "red", [_spec()])
    assert result.ok
    assert len(ato.packages) == 1
    assert not flight.returned


@pytest.mark.parametrize(
    "tot_minutes, expected",
    [
        (None, False),
        (-1065409500, False),
        (-1, False),
        (0, True),
        (60, True),
        (61, False),
    ],
)
def test_a_tot_before_the_mission_starts_is_not_within_the_window(
    tot_minutes: int | None, expected: bool
) -> None:
    assert planner._within_window(tot_minutes, 60) is expected
