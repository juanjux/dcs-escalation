"""What the High Command pays for taking an objective."""

from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

from game.ato.flighttype import FlightType
from game.data.groups import GroupTask
from game.data.units import UnitClass
from game.highcommand.objectives import Effort, Objective
from game.highcommand.prizes import (
    KINDS,
    MAX_SCORE,
    Context,
    Prize,
    PrizeKind,
    Prizes,
)


def _settings(live_pilots: bool = True, morale: bool = True) -> Any:
    return SimpleNamespace(live_pilots_enabled=live_pilots, morale_enabled=morale)


class _Aircraft:
    def __init__(self, name: str, price: int, *tasks: FlightType) -> None:
        self.display_name = name
        self.price = price
        self.task_priorities = {task: 1 for task in tasks}


class _Vehicle:
    def __init__(self, name: str, unit_class: UnitClass) -> None:
        self.variant_id = name
        self.unit_class = unit_class

    def __str__(self) -> str:
        return self.variant_id


def _faction(*bands: GroupTask) -> Any:
    return SimpleNamespace(
        aircraft={
            _Aircraft("F-5E", 10, FlightType.BARCAP),
            _Aircraft("F-16C", 20, FlightType.BARCAP, FlightType.STRIKE),
            _Aircraft("F-15E", 30, FlightType.STRIKE),
            _Aircraft("KC-135", 50, FlightType.REFUELING),
        },
        frontline_units={
            _Vehicle("M1A2", UnitClass.TANK),
            _Vehicle("M2A2", UnitClass.IFV),
            _Vehicle("M163", UnitClass.AAA),
        },
        preset_groups=[SimpleNamespace(tasks=[band]) for band in bands],
    )


def _kind(key: str) -> PrizeKind:
    return next(kind for kind in KINDS if kind.key == key)


def _prize(key: str, score: int, faction: Any = None) -> Prize:
    context = Context(
        _settings(),
        faction or _faction(GroupTask.SHORAD, GroupTask.MERAD),
        100.0,
        random.Random(1),
    )
    prize = _kind(key).prize(score, context)
    assert prize is not None
    return prize


def test_the_score_is_the_difficulty_plus_the_importance() -> None:
    objective = Objective(
        name="TURKEY",
        kind="AA Defense Site",
        targets=(),
        effort=Effort(route=0, fighters=0, size=0),
        hazards=(),
        difficulty=3,
        importance=5,
    )

    assert objective.score == 8


def test_every_kind_works_out_at_every_score_it_can_be_won_with() -> None:
    faction = _faction(GroupTask.SHORAD, GroupTask.MERAD, GroupTask.LORAD)
    for kind in KINDS:
        for score in range(kind.min_score, MAX_SCORE + 1):
            prize = _prize(kind.key, score, faction)
            assert prize.line.endswith("."), prize.line
            assert (prize.score, prize.ticket) == (score, kind.ticket)


def test_a_kind_is_drawn_only_from_its_lowest_score_up() -> None:
    prizes = Prizes(_settings(), _faction(GroupTask.SHORAD), 100.0)

    at_five = {prize.kind for s in range(300) if (prize := prizes.draw(5, s))}
    at_ten = {prize.kind for s in range(300) if (prize := prizes.draw(10, s))}

    assert not at_five & {"runway", "heal"}
    assert {"runway", "heal"} <= at_ten


def test_a_kind_the_game_cannot_give_yet_is_never_drawn() -> None:
    prizes = Prizes(_settings(), _faction(GroupTask.SHORAD), 100.0)
    cannot = {kind.key for kind in KINDS if kind.give is None}

    drawn = {prize.kind for s in range(300) if (prize := prizes.draw(10, s))}

    assert cannot and not drawn & cannot


def test_kinds_the_campaign_cannot_give_are_never_drawn() -> None:
    prizes = Prizes(_settings(live_pilots=False), _faction(GroupTask.SHORAD), 100.0)

    drawn = {prize.kind for s in range(300) if (prize := prizes.draw(10, s))}

    assert not drawn & {
        "faction-xp",
        "package-xp",
        "hospital",
        "morale",
        "ace",
        "heal",
        # No fog of war, and the enemy's plan is on the map for anyone.
        "recon",
        "sigint",
        "enemy-plan",
    }


def test_the_same_seed_draws_the_same_prize() -> None:
    prizes = Prizes(_settings(), _faction(GroupTask.SHORAD), 100.0)

    assert prizes.draw(7, "13:TURKEY") == prizes.draw(7, "13:TURKEY")


def test_the_numbers_are_worked_out_from_the_score() -> None:
    assert _prize("faction-xp", 2).line == "+1% XP for all our pilots for 1 turn."
    assert _prize("faction-xp", 7).line == "+3.5% XP for all our pilots for 4 turns."
    assert _prize("cash", 5).line == (
        "Cash worth 100% of our income per turn, about $100M today."
    )
    assert _prize("pilots", 7).line.startswith("4 extra Veteran pilots for 4 turns")
    assert _prize("pilots", 2).line.startswith("1 extra Cadet pilot for 1 turn")
    assert _prize("discount", 5).term("percent") == 35
    assert _prize("discount", 5).term("turns") == 3
    assert _prize("faster-repairs", 3).term("percent") == 30
    assert "instant" in _prize("faster-repairs", 10).line
    assert _prize("hospital", 5).term("turns") == 1
    assert _prize("hospital", 6).term("turns") == 2
    assert _prize("morale", 6).term("points") == 12
    assert _prize("enemy-income", 2).term("percent") == 18
    assert _prize("enemy-income", 10).term("percent") == 90
    assert _prize("enemy-repairs", 4).line == (
        "Enemy repairs take 40% more turns, at least one more, for 2 turns."
    )


def test_a_squadron_on_loan_is_dearer_the_higher_the_score() -> None:
    # The tanker is no combat aircraft, however dear.
    assert _prize("squadron", 2).term("type") == "F-5E"
    assert _prize("squadron", 10).line == (
        "A ticket for a squadron of 20 F-15E on loan for 5 turns."
    )


def test_a_sam_ticket_is_the_best_battery_the_faction_has_up_to_the_score() -> None:
    assert "short-range" in _prize("sam", 4).line
    assert "medium-range" in _prize("sam", 9).line
    faction = _faction(GroupTask.SHORAD, GroupTask.MERAD, GroupTask.LORAD)
    assert "long-range" in _prize("sam", 9, faction).line


def test_armour_is_armour() -> None:
    vehicles = dict(_prize("armour", 5).term("vehicles"))

    assert set(vehicles) == {"M1A2", "M2A2"}
    assert sum(vehicles.values()) == 5
