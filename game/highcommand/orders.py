"""The objectives the High Command orders taken.

There are always ORDERS of them, one from each tier of the enemy's objectives ranked
by score (difficulty plus importance): with three, one from the top third, one from the
middle third and one from the bottom. An order is given a lifetime of SHORTEST to
LONGEST turns, and its objective's prize, when it is made. When the lifetime runs out,
or the objective is gone, the order closes, with nothing lost, and another objective
from the same tier takes its place. The player cannot turn an order down.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from game.highcommand.prizes import Prize
from game.squadrons.experience import SaveCompatible
from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.highcommand.objectives import Objective

#: How many orders the High Command keeps open, each from its own tier.
ORDERS = 3

#: How many turns an order stays open, drawn when it is made.
SHORTEST = 2
LONGEST = 5

#: What the tiers are called when there are three of them, lowest first.
TIER_NAMES = ("low", "medium", "high")


class Outcome(Enum):
    #: Its turns ran out.
    EXPIRED = "expired"
    #: Everything in it was destroyed.
    DESTROYED = "destroyed"
    #: It is no longer an enemy objective for some other reason: captured, or with
    #: nothing left there worth attacking.
    GONE = "gone"


@dataclass
class Order(SaveCompatible):
    """One enemy objective the High Command has ordered taken."""

    #: The objective, by name.
    objective: str
    #: Which tier it was drawn from, 0 for the lowest.
    tier: int
    ordered_on: int
    #: The first turn it is no longer open.
    expires_on: int
    prize: Optional[Prize]
    #: What the objective was when the order was made, for whatever shows the order.
    kind: str = ""
    difficulty: int = 0
    importance: int = 0
    justification: str = ""

    @property
    def score(self) -> int:
        return self.difficulty + self.importance

    def turns_left(self, turn: int) -> int:
        return self.expires_on - turn


@dataclass(frozen=True)
class Closed:
    """An order that closed, and why."""

    order: Order
    outcome: Outcome


@dataclass
class HighCommand(SaveCompatible):
    """The orders open now."""

    orders: list[Order] = field(default_factory=list)

    def refresh(self, game: Game, rng: Optional[random.Random] = None) -> list[Closed]:
        """Close the orders that are over and make new ones for the tiers left
        without. What closed is returned, with why, for whatever pays out prizes."""
        from game.highcommand.objectives import enemy_objectives

        rng = rng or random.Random()
        objectives = enemy_objectives(game)
        standing = {o.name for o in objectives}
        closed: list[Closed] = []
        for order in list(self.orders):
            outcome = _outcome(order, game, standing)
            if outcome is not None:
                self.orders.remove(order)
                closed.append(Closed(order, outcome))

        busy = {order.tier for order in self.orders}
        # Nor the objective an order has just closed on: its replacement is another.
        taken = {order.objective for order in self.orders} | {
            c.order.objective for c in closed
        }
        for tier, candidates in enumerate(tiers(objectives, ORDERS)):
            if tier in busy:
                continue
            choices = [o for o in candidates if o.name not in taken]
            if not choices:
                continue
            chosen = rng.choice(choices)
            taken.add(chosen.name)
            self.orders.append(
                _order(chosen, tier, game.turn, rng.randint(SHORTEST, LONGEST))
            )
        self.orders.sort(key=lambda order: -order.tier)
        return closed


def tiers(objectives: Sequence[Objective], count: int) -> list[list[Objective]]:
    """The objectives in ``count`` tiers of score as near equal in size as can be, the
    lowest first."""
    ranked = sorted(objectives, key=lambda o: (o.score, o.name))
    total = len(ranked)
    return [
        ranked[tier * total // count : (tier + 1) * total // count]
        for tier in range(count)
    ]


def tier_name(tier: int, count: int = ORDERS) -> str:
    if count == len(TIER_NAMES):
        return TIER_NAMES[tier]
    return f"tier {tier + 1} of {count}"


def _order(objective: Objective, tier: int, turn: int, lifetime: int) -> Order:
    return Order(
        objective=objective.name,
        tier=tier,
        ordered_on=turn,
        expires_on=turn + lifetime,
        prize=objective.prize,
        kind=objective.kind,
        difficulty=objective.difficulty,
        importance=objective.importance,
        justification=objective.justification,
    )


def _outcome(order: Order, game: Game, standing: set[str]) -> Optional[Outcome]:
    """Why the order closes this turn, if it does. Destroying the objective counts
    even on the turn the order would have run out."""
    tgos = [tgo for tgo in game.theater.ground_objects if tgo.name == order.objective]
    # A motorpool's vehicles are drawn afresh for every mission: an empty one has not
    # been destroyed, and it closes when it is no longer worth attacking.
    if (
        tgos
        and not any(isinstance(tgo, MotorpoolGroundObject) for tgo in tgos)
        and all(tgo.is_dead for tgo in tgos)
    ):
        return Outcome.DESTROYED
    if order.objective not in standing:
        return Outcome.GONE
    if game.turn >= order.expires_on:
        return Outcome.EXPIRED
    return None
