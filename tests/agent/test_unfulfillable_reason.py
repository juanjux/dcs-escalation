"""Why a package could not be planned, said so the caller can act on it.

Range and role both came back as "capable and free, but out of the auto-planner's
range", and both were answered with "pass squadron_id" -- which the caller may have
passed already, and which does nothing about the range either way. Astra hit exactly
that: she named a squadron and was told to name a squadron.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from game.agent import planner, schemas
from game.ato.flighttype import FlightType
from game.utils import nautical_miles

MUSK = "target-1"


class _Squadron:
    """Enough of a squadron for the diagnosis, and the two rules it really uses: the
    task has to be one it auto-assigns, and the target has to be inside the limit."""

    def __init__(
        self,
        name: str,
        away_nm: float,
        untasked: int = 8,
        roles: set[FlightType] | None = None,
    ) -> None:
        self.id = uuid4()
        self.name = name
        self.untasked_aircraft = untasked
        self.owned_aircraft = untasked
        self.away_nm = away_nm
        self.auto_assignable_mission_types = (
            {FlightType.DEAD} if roles is None else set(roles)
        )
        self.aircraft = SimpleNamespace(
            capable_of=lambda task: True,
            max_mission_range=nautical_miles(150),
        )
        # The target measures to the base, the way the engine does it.
        self.location = SimpleNamespace(name=f"{name} field", away_nm=away_nm)

    def capable_of(self, task: FlightType) -> bool:
        return True

    def can_auto_assign_mission(
        self,
        location: Any,
        task: FlightType,
        size: int,
        heli: bool,
        this_turn: bool,
        ignore_range: bool = False,
    ) -> bool:
        if task not in self.auto_assignable_mission_types:
            return False
        return True if ignore_range else self.away_nm <= 300


class _NeverAssigned(_Squadron):
    """Capable and free, and the planner still will not have it: a non-helicopter at
    a FARP, or a squadron with nobody left to fly."""

    def can_auto_assign_mission(self, *args: Any, **kwargs: Any) -> bool:
        return False


def _game(*squadrons: _Squadron) -> Any:
    air_wing = SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    coalition = SimpleNamespace(air_wing=air_wing)
    return SimpleNamespace(
        coalition_for=lambda _player: coalition,
        settings=SimpleNamespace(max_mission_range_planes=300),
    )


def _spec(squadron: _Squadron | None = None, ignore_range: bool = False) -> Any:
    flight: dict[str, Any] = {"task": "DEAD", "count": 2}
    if squadron is not None:
        flight["squadron_id"] = str(squadron.id)
    return schemas.PackageSpec(
        target_id=MUSK, ignore_range=ignore_range, flights=[flight]
    )


@pytest.fixture(autouse=True)
def target(monkeypatch: Any) -> Any:
    """Something to measure to. How far away it is, is the squadron's business."""
    aim = SimpleNamespace(
        name="MUSK",
        distance_to=lambda location: nautical_miles(location.away_nm).meters,
    )
    monkeypatch.setattr(planner, "resolve_target", lambda _game, _id: aim)
    return aim


def _reason(game: Any, spec: Any) -> str:
    return planner._unfulfilled_reason(game, "red", spec)


def test_a_named_squadron_is_not_told_to_name_a_squadron() -> None:
    """The report: squadron_id passed, and the answer was to pass squadron_id."""
    far = _Squadron("Fierce Dragon", away_nm=406)

    reason = _reason(_game(far), _spec(far))

    assert "squadron_id" not in reason
    assert "ignore_range:true" in reason


def test_it_says_how_far_over_the_limit_it_is() -> None:
    """406 and 300 are the two numbers that decide what to do next."""
    far = _Squadron("Fierce Dragon", away_nm=406)

    reason = _reason(_game(far), _spec(far))

    assert "406 NM to the target" in reason
    assert "limit 300 NM" in reason


def test_without_a_named_squadron_both_ways_out_are_offered() -> None:
    far = _Squadron("Fierce Dragon", away_nm=406)

    reason = _reason(_game(far), _spec())

    assert "ignore_range:true" in reason
    assert "squadron_id" in reason


def test_a_role_nobody_auto_assigns_is_not_called_a_range_problem() -> None:
    """The squadron is next door and flies the jet; it just does not take the task."""
    near = _Squadron("Fierce Dragon", away_nm=40, roles=set())

    reason = _reason(_game(near), _spec())

    assert "range" not in reason
    assert "auto-assigns DEAD" in reason
    assert "squadron_id" in reason


def test_naming_the_squadron_gets_it_the_task_it_does_not_auto_assign() -> None:
    """What squadron_id is actually for, and it still works."""
    near = _Squadron("Fierce Dragon", away_nm=40, roles=set())

    assert (
        _reason(_game(near), _spec(near))
        == "no capable aircraft were free and in range"
    )
    # ...which is the "nothing to report" fallback: the flight is fillable.


def test_a_named_squadron_that_fails_for_another_reason_says_so() -> None:
    """Its task is forced for it and it is in range, so neither is the problem."""
    near = _NeverAssigned("Fierce Dragon", away_nm=40)

    reason = _reason(_game(near), _spec(near))

    assert "range" not in reason
    assert "Fierce Dragon" in reason


def test_ignore_range_does_not_offer_ignore_range_again() -> None:
    far = _NeverAssigned("Fierce Dragon", away_nm=406)

    reason = _reason(_game(far), _spec(far, ignore_range=True))

    assert "ignore_range" not in reason
