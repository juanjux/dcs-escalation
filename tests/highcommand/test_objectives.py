"""The High Command's list of enemy objectives: how hard each is, how much it
matters, and the line that goes with it."""

from __future__ import annotations

from typing import Any

import pytest

from game.highcommand.approach import Release, Ring
from game.highcommand.campaign import RING_WEIGHT, STANDOFF_PENALTY
from game.highcommand.importance import Reason
from game.highcommand.objectives import (
    COMICAL,
    ROUTE_MILES_PER_POINT,
    Effort,
    Objective,
    _effort,
    ranked,
)
from game.mfd import Band
from game.theater import Player
from tests.highcommand.stubs import NM, Base, at, campaign, launcher, sam


def _objective(name: str, effort: float = 0.0, worth: float = 0.0) -> Objective:
    return Objective(
        name=name,
        kind="Factory",
        targets=(),
        effort=Effort(route=effort, fighters=0, size=0),
        hazards=(),
        reasons=(Reason("income", worth, f"{name} earns."),),
    )


def _ring(site: Any) -> Ring:
    return Ring(
        site,
        site.position.x,
        site.position.y,
        site.max_threat_range().meters,
        RING_WEIGHT[Band.LONG],
    )


# ---------------------------------------------------------------- the levels


def test_difficulty_is_the_fifth_the_effort_falls_in() -> None:
    objectives = ranked([_objective(str(n), effort=float(n)) for n in range(10)])

    assert [o.difficulty for o in objectives] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_equal_efforts_share_a_difficulty() -> None:
    efforts = [1.0, 2.0, 2.0, 2.0, 2.0, 9.0]

    difficulties = [
        o.difficulty for o in ranked([_objective("x", effort=e) for e in efforts])
    ]

    assert difficulties[1] == difficulties[2] == difficulties[3] == difficulties[4]
    assert difficulties[0] == 1
    assert difficulties[-1] == 5


def test_importance_is_the_fifth_the_worth_falls_in() -> None:
    objectives = ranked([_objective(str(n), worth=float(n)) for n in range(10)])

    assert [o.importance for o in objectives] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_the_line_is_the_reason_worth_most_but_not_for_the_least_important() -> None:
    worth_most = Reason("cover", 90.0, "Covers a lot.")
    objective = Objective(
        name="GRUMBLE",
        kind="AA Defense Site",
        targets=(),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        reasons=(worth_most, Reason("rebuild", 10.0, "Costs a little.")),
    )
    cheap = [_objective(str(n), worth=float(n)) for n in range(4)]

    ranked_ = {o.name: o for o in ranked([objective, *cheap])}

    assert ranked_["GRUMBLE"].justification == "Covers a lot."
    assert ranked_["0"].justification == COMICAL


# ---------------------------------------------------------------- the effort


def test_effort_adds_the_route_the_fighters_and_the_size() -> None:
    enemy_field = Base("Kutaisi", 50)
    measured = campaign(
        our_bases=[Base("Batumi", 300, Player.BLUE)],
        fighters={enemy_field: 24},
        points=[at(10)],
    )

    effort, hazards = _effort(measured, "FACTORY", at(10), units=16, at_sea=False)

    # Bombs from 10 nm out: 280 nm from Batumi, all of it in the open.
    assert effort.route == pytest.approx(280 / ROUTE_MILES_PER_POINT)
    assert effort.fighters == 2.0
    assert effort.size == 1.0
    assert hazards == (
        "280 nm from Batumi",
        "24 fighters within 150 nm",
        "16 units to destroy",
    )


def test_the_rings_that_make_an_objective_hard_are_named() -> None:
    battery = sam("GRUMBLE", 100, [launcher("SAM SA-10 LN", 40)])
    measured = campaign(
        rings=[_ring(battery)],
        our_bases=[Base("Batumi", 300, Player.BLUE)],
        points=[at(100), at(100, 5)],
    )

    _, own = _effort(measured, "GRUMBLE", at(100), units=0, at_sea=False)
    # Too close to the battery to reach from anywhere outside its ring.
    _, covered = _effort(measured, "DEPOT", at(100, 5), units=0, at_sea=False)

    assert own[0] == "its own SA-10"
    assert covered[0] == "SA-10 at GRUMBLE"


def test_a_stand_off_weapon_costs_its_penalty_and_names_no_weapon() -> None:
    battery = sam("GRUMBLE", 100, [launcher("SAM SA-10 LN", 40)])
    measured = campaign(
        rings=[_ring(battery)],
        our_bases=[Base("Batumi", 300, Player.BLUE)],
        points=[at(100)],
    )
    close_in, _ = _effort(measured, "GRUMBLE", at(100), units=0, at_sea=False)
    measured.land_releases.append(Release(60 * NM, STANDOFF_PENALTY))

    effort, hazards = _effort(measured, "GRUMBLE", at(100), units=0, at_sea=False)

    assert effort.route < close_in.route
    # The weapon's flight over the ring costs something, too little to name.
    assert effort.route > (140 + STANDOFF_PENALTY) / ROUTE_MILES_PER_POINT
    assert hazards == ("140 nm from Batumi",)
