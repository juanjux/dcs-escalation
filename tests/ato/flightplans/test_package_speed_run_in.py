"""The run-in from the join to the ingress is flown at the package's speed.

It was the one leg of a package's route that every flight priced on its own, so an
escort on a faster airframe arrived at the ingress ahead of the striker it was
escorting. Package speed is not combat burn, though: the fuel model must still charge
cruise until the ingress.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


def _plan(**waypoints: Any) -> Any:
    from game.ato.flightplans.formationattack import FormationAttackFlightPlan

    plan = FormationAttackFlightPlan.__new__(FormationAttackFlightPlan)
    plan.layout = SimpleNamespace(**waypoints)
    return plan


@pytest.fixture
def plan() -> Any:
    return _plan(
        join="JOIN",
        ingress="INGRESS",
        split="SPLIT",
        targets=["T1", "T2"],
    )


def test_the_run_in_is_a_package_speed_leg(plan: Any) -> None:
    assert "INGRESS" in plan.package_speed_waypoints


def test_the_join_the_split_and_the_targets_still_are(plan: Any) -> None:
    assert {"JOIN", "SPLIT", "T1", "T2"} <= plan.package_speed_waypoints


def test_the_run_in_is_not_charged_as_combat(plan: Any) -> None:
    """`fuel_rate_to_between_points` reads this set to pick combat over cruise."""
    assert "INGRESS" not in plan.combat_speed_waypoints


def test_everything_else_is_still_combat(plan: Any) -> None:
    assert plan.combat_speed_waypoints == {"JOIN", "SPLIT", "T1", "T2"}
