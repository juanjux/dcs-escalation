"""The objectives the High Command orders taken.

There are as many open as the settings say, one from each tier of the enemy's
objectives ranked by score (difficulty plus importance): with three, one from the top
third, one from the middle third and one from the bottom. An order is given a lifetime
of between the shortest and the longest the settings allow, and its objective's prize,
when it is made. When the lifetime runs out,
or the objective is gone, the order closes, with nothing lost, and another objective
from the same tier takes its place. The player cannot turn an order down.

An order is achieved when what it asks is done, at the latest on its last turn:

* a ground object: every unit in it destroyed, while it is still the enemy's. A base
  taken clears what it cannot keep, and that is not destroying it;
* a motorpool: at least one of its vehicles destroyed;
* a base's aircraft: at least one of them destroyed on the ground there;
* a base's runway: cratered;
* a base: taken. A base taken on an order for its aircraft or its runway only closes
  the order.

Motorpool vehicles and a base's aircraft leave nothing behind to count afterwards, so
those two are noted from the mission's results as they come in (note_results).

An achieved order pays its prize (pay): at once, or as a ticket kept in the save for
whoever plays the campaign, to spend later (spend).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from game.highcommand.campaign import Task
from game.highcommand.loans import Loan, return_loans
from game.highcommand.prizes import Prize, kind_of
from game.squadrons.experience import SaveCompatible
from game.theater.player import Player
from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing
    from game.highcommand.objectives import Objective

#: The High Command gives its orders to the player, against the other side.
ENEMY = Player.RED

#: What the tiers are called when there are three of them, lowest first.
TIER_NAMES = ("low", "medium", "high")

#: How many entries the history keeps; the oldest go first.
HISTORY_KEPT = 200
#: What the history says a spent ticket was.
SPENT = "spent"


class Outcome(Enum):
    #: What it asked was done.
    ACHIEVED = "achieved"
    #: Its turns ran out.
    EXPIRED = "expired"
    #: It is no longer an enemy objective for some other reason: its base taken on an
    #: order that did not ask for it, or nothing left there worth attacking.
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
    #: What is asked of a base, and which base; None and empty for a ground object.
    task: Optional[Task] = None
    base: str = ""
    #: The turn a mission's results achieved it, for what the state after them
    #: cannot show.
    achieved_on: Optional[int] = None

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
class Ticket(SaveCompatible):
    """A prize kept to be spent when the player chooses."""

    prize: Prize
    #: The objective that earned it, and when.
    earned_by: str
    earned_on: int


@dataclass(frozen=True)
class HistoryEntry(SaveCompatible):
    """An order that closed or a ticket spent, and on which turn."""

    turn: int
    #: The Outcome's value, or SPENT.
    outcome: str
    #: The objective, or "Ticket spent".
    name: str
    line: str


@dataclass
class Effect(SaveCompatible):
    """A prize that lasts some turns: a discount, an experience bonus, a cut in the
    enemy's income."""

    #: The prize kind it came from.
    kind: str
    #: What it does, without how long for: "42% off SAM batteries".
    label: str
    #: The objective that earned it.
    earned_by: str
    #: The first turn it no longer applies.
    until: int

    def turns_left(self, turn: int) -> int:
        return self.until - turn


@dataclass
class HighCommand(SaveCompatible):
    """The orders open now, and the tickets earned and not yet spent."""

    orders: list[Order] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    #: The squadrons lent to the player, until each loan runs out.
    loans: list[Loan] = field(default_factory=list)
    #: What closed and what was given, oldest first.
    history: list[HistoryEntry] = field(default_factory=list)
    #: The prizes that last some turns and have not run out.
    effects: list[Effect] = field(default_factory=list)

    def note(self, turn: int, outcome: str, name: str, line: str) -> None:
        self.history.append(HistoryEntry(turn, outcome, name, line))
        del self.history[:-HISTORY_KEPT]

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

        count = game.settings.high_command_orders
        # Fewer orders set than there were: the tiers past the new count are gone.
        for order in [order for order in self.orders if order.tier >= count]:
            self.orders.remove(order)
            closed.append(Closed(order, Outcome.GONE))
        for done in closed:
            if done.outcome is Outcome.EXPIRED:
                lifetime = done.order.expires_on - done.order.ordered_on
                self.note(
                    game.turn,
                    done.outcome.value,
                    done.order.objective,
                    f"ran out after {lifetime} turn{'s' if lifetime != 1 else ''}",
                )
            elif done.outcome is Outcome.GONE:
                self.note(
                    game.turn,
                    done.outcome.value,
                    done.order.objective,
                    "no longer an objective",
                )
        shortest, longest = sorted(
            (
                game.settings.high_command_shortest_order,
                game.settings.high_command_longest_order,
            )
        )
        busy = {order.tier for order in self.orders}
        # Nor the objective an order has just closed on: its replacement is another.
        taken = {order.objective for order in self.orders} | {
            c.order.objective for c in closed
        }
        for tier, candidates in enumerate(tiers(objectives, count)):
            if tier in busy:
                continue
            choices = [o for o in candidates if o.name not in taken]
            if not choices:
                continue
            chosen = rng.choice(choices)
            taken.add(chosen.name)
            self.orders.append(
                _order(chosen, tier, game.turn, rng.randint(shortest, longest))
            )
        self.orders.sort(key=lambda order: -order.tier)
        return closed

    def pay(self, game: Game, closed: Sequence[Closed]) -> list[str]:
        """Give the prizes of the orders achieved, at once or as a ticket. What was
        given, a line each."""
        lines = []
        for done in closed:
            if done.outcome is not Outcome.ACHIEVED:
                continue
            prize = done.order.prize
            name = done.order.objective
            kind = kind_of(prize) if prize is not None else None
            if prize is None:
                given = "no prize"
            elif prize.ticket:
                self.tickets.append(Ticket(prize, name, game.turn))
                given = prize.line
                lines.append(f"{name}: {given}")
            elif kind is not None and kind.give is not None:
                given = kind.give(game, prize, ())
                lines.append(f"{name}: {given}")
            else:
                given = prize.line
            self.note(game.turn, Outcome.ACHIEVED.value, name, given)
        return lines

    def end_effects(self, game: Game) -> list[str]:
        """Drop the effects that have run out, and say which."""
        over = [effect for effect in self.effects if game.turn >= effect.until]
        for effect in over:
            self.effects.remove(effect)
        return [f"{effect.label} is over." for effect in over]

    def return_loans(self, game: Game) -> list[str]:
        """Take back the squadrons whose loan has run out, and say which."""
        return list(return_loans(game, self.loans))

    def spend(self, game: Game, ticket: Ticket, picked: tuple[str, ...]) -> str:
        """Spend a ticket on what the player picked for each of its steps, and say
        what it gave. The ticket is gone once spent; one that cannot be given now
        raises CannotGive and stays."""
        kind = kind_of(ticket.prize)
        if kind is None or kind.give is None:
            raise ValueError(f"The game cannot give {ticket.prize.kind} any more")
        line = kind.give(game, ticket.prize, picked)
        self.tickets.remove(ticket)
        self.note(game.turn, SPENT, "Ticket spent", line)
        return line

    def note_results(self, game: Game, debriefing: Debriefing) -> None:
        """Mark the orders a mission achieved that its aftermath cannot show. To be
        called before its results are committed."""
        for order in self.orders:
            if order.achieved_on is None and _achieved_by(order, game, debriefing):
                order.achieved_on = game.turn


def tiers(objectives: Sequence[Objective], count: int) -> list[list[Objective]]:
    """The objectives in ``count`` tiers of score as near equal in size as can be, the
    lowest first."""
    ranked = sorted(objectives, key=lambda o: (o.score, o.name))
    total = len(ranked)
    return [
        ranked[tier * total // count : (tier + 1) * total // count]
        for tier in range(count)
    ]


def tier_name(tier: int, count: int) -> str:
    if count == len(TIER_NAMES):
        return TIER_NAMES[tier]
    return f"tier {tier + 1} of {count}"


def _order(objective: Objective, tier: int, turn: int, lifetime: int) -> Order:
    target = objective.targets[0] if objective.targets else None
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
        task=objective.task,
        base=target.name if objective.task is not None and target else "",
    )


def _outcome(order: Order, game: Game, standing: set[str]) -> Optional[Outcome]:
    """Why the order closes this turn, if it does. What was achieved on its last turn
    counts."""
    if order.achieved_on is not None:
        return Outcome.ACHIEVED
    if order.task is None:
        tgos = [
            tgo for tgo in game.theater.ground_objects if tgo.name == order.objective
        ]
        if any(tgo.control_point.captured != ENEMY for tgo in tgos):
            return Outcome.GONE
        # A motorpool's vehicles are drawn afresh for every mission: an empty one has
        # not been destroyed. Its losses come in through note_results.
        if (
            tgos
            and not any(isinstance(tgo, MotorpoolGroundObject) for tgo in tgos)
            and all(tgo.is_dead for tgo in tgos)
        ):
            return Outcome.ACHIEVED
    else:
        base = next(
            (cp for cp in game.theater.controlpoints if cp.name == order.base), None
        )
        if base is None:
            return Outcome.GONE
        if base.captured != ENEMY:
            return Outcome.ACHIEVED if order.task is Task.CAPTURE else Outcome.GONE
        if order.task is Task.RUNWAY and not base.runway_is_operational():
            return Outcome.ACHIEVED
    if order.objective not in standing:
        return Outcome.GONE
    if game.turn >= order.expires_on:
        return Outcome.EXPIRED
    return None


def _achieved_by(order: Order, game: Game, debriefing: Debriefing) -> bool:
    """Whether the mission destroyed one of the aircraft on the ground at the order's
    base, or one of the vehicles of its motorpool."""
    if order.task is Task.AIRCRAFT:
        return any(
            loss.flight.departure.name == order.base
            and debriefing.died_on_the_ground(loss)
            for loss in debriefing.air_losses.enemy
        )
    if order.task is not None:
        return False
    motorpools = [
        tgo
        for tgo in game.theater.ground_objects
        if tgo.name == order.objective and isinstance(tgo, MotorpoolGroundObject)
    ]
    if not motorpools:
        return False
    from game.missiongenerator.motorpoolpopulator import motorpools_at

    base = motorpools[0].control_point
    if not any(
        loss.origin is base for loss in debriefing.ground_losses.enemy_motorpool
    ):
        return False
    if len(motorpools_at(base)) == 1:
        return True
    # The base's losses are its motorpools' together: which one lost the vehicle is in
    # the name DCS reports, which is the name the unit was drawn with.
    dead = set(debriefing.state_data.killed_ground_units)
    return any(unit.unit_name in dead for tgo in motorpools for unit in tgo.units)
