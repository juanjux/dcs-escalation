"""Offensive DEAD goes after the detectors before the SAMs they cover.

A Skynet-held SAM stays dark until its target is inside its kill zone, and the DCS AI
fires a HARM only at an emitter, so a DEAD flight sent at a covered site arrives with
nothing to shoot at. Killing the EWR first makes Skynet run the site autonomous and
live, which the next DEAD can service. A SAM that threatens a planned strike is not
affected: it is offered before either tier.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from game.commander.tasks.compound.degradeiads import DegradeIads
from game.commander.tasks.primitive.dead import PlanDead
from game.data.groups import GroupTask
from game.theater.theatergroundobject import IadsGroundObject


def _tgo(name: str, task: GroupTask, threat_range: float = 40_000) -> Any:
    tgo = MagicMock(spec=IadsGroundObject)
    tgo.name = name
    tgo.task = task
    tgo.max_threat_range.return_value = MagicMock(meters=threat_range)
    return tgo


def _state(threatening: list[Any], prioritized: list[Any], detectors: list[Any]) -> Any:
    state = MagicMock()
    state.threatening_air_defenses = threatening
    state.enemy_air_defenses = prioritized
    state.detecting_air_defenses = detectors
    state.priority_cp = None
    return state


def _order(state: Any) -> list[str]:
    names = []
    for method in DegradeIads().each_valid_method(state):
        task = method[0]
        assert isinstance(task, PlanDead)
        names.append(task.target.name)
    return names


@pytest.fixture
def ewr() -> Any:
    return _tgo("EWR 1L13", GroupTask.EARLY_WARNING_RADAR)


@pytest.fixture
def sam() -> Any:
    return _tgo("SA-11", GroupTask.MERAD)


def test_the_detector_is_offered_before_the_sam(ewr: Any, sam: Any) -> None:
    order = _order(_state([], [sam], [ewr]))
    assert order.index("EWR 1L13") < order.index("SA-11")


def test_a_threatening_sam_still_comes_first(ewr: Any, sam: Any) -> None:
    """The reactive tier is unchanged: it answers a SAM over a planned strike."""
    urgent = _tgo("SA-10 over the target", GroupTask.LORAD)
    order = _order(_state([urgent], [sam], [ewr]))
    assert order[0] == "SA-10 over the target"


def test_nothing_is_dropped(ewr: Any, sam: Any) -> None:
    order = _order(_state([], [sam], [ewr]))
    assert sorted(order) == ["EWR 1L13", "SA-11"]


def test_with_no_detector_the_sam_tier_is_unchanged(sam: Any) -> None:
    other = _tgo("SA-6", GroupTask.MERAD, threat_range=25_000)
    assert _order(_state([], [sam, other], [])) == ["SA-11", "SA-6"]
