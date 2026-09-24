"""What the High Command window shows, worked out from the game before anything is
drawn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from dcs.mapping import Point

from game.highcommand.campaign import Task
from game.highcommand.orders import ENEMY, TIER_NAMES, Order, Ticket
from game.highcommand.prizes import PrizeKind, Step, kind_of
from game.highcommand.wording import counted, money
from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.highcommand.objectives import Objective

#: What each task asks of a base, as the second line of its row.
ASKED = {
    Task.AIRCRAFT: "OCA/Aircraft — destroy one on the ground",
    Task.RUNWAY: "OCA/Runway — crater the runway",
    Task.CAPTURE: "Capture — take the base",
}

#: Importance 1 carries a comical justification instead of a reason.
COMICAL_IMPORTANCE = 1


@dataclass(frozen=True)
class Headline:
    orders: int
    last_turn: int
    tickets: int
    loans: int
    turn: int
    #: The fewest turns any open order has left; None with no orders.
    soonest: Optional[int] = None


@dataclass(frozen=True)
class OrderView:
    """One open order, as its row and the detail pane show it."""

    order: Order
    name: str
    kind: str
    #: The base the objective belongs to, or the base itself for a base task.
    base: str
    #: The tier, as its chip reads: HIGH, MEDIUM or LOW with three tiers, "k/n" else.
    tier_chip: str
    #: Which of the three chip colours: "high", "medium" or "low".
    tier_colour: str
    tier_words: str
    asked: str
    prize_line: str
    ticket: bool
    turns_left: int
    lifetime: int
    difficulty: int
    importance: int
    justification: str
    taken_title: str
    taken_detail: str
    hazards: tuple[str, ...]
    #: The objective's worth by reason, the largest first, as (reason, "$393M"); a
    #: reason made of more than one thing is listed by its parts.
    worth: tuple[tuple[str, str], ...]
    position: Optional[Point]

    @property
    def last_turn(self) -> bool:
        return self.turns_left <= 1

    @property
    def last_open_turn(self) -> int:
        return self.order.expires_on - 1

    @property
    def score(self) -> int:
        return self.difficulty + self.importance

    @property
    def comical(self) -> bool:
        return self.importance == COMICAL_IMPORTANCE


def headline(game: Game) -> Headline:
    command = game.high_command
    left = [order.turns_left(game.turn) for order in command.orders]
    return Headline(
        orders=len(command.orders),
        last_turn=sum(1 for turns in left if turns <= 1),
        tickets=len(command.tickets),
        loans=len(command.loans),
        turn=game.turn,
        soonest=min(left) if left else None,
    )


def tier_chip(tier: int, count: int) -> str:
    if count == len(TIER_NAMES):
        return TIER_NAMES[tier].upper()
    return f"{tier + 1}/{count}"


def tier_colour(tier: int, count: int) -> str:
    if tier >= count - 1:
        return "high"
    if tier == 0:
        return "low"
    return "medium"


def tier_words(tier: int, count: int) -> str:
    if count == len(TIER_NAMES):
        return f"{TIER_NAMES[tier]} tier"
    return f"tier {tier + 1} of {count}"


def order_views(game: Game) -> list[OrderView]:
    """The open orders, highest tier first, as the order list keeps them."""
    orders = list(game.high_command.orders)
    if not orders:
        return []
    by_name = {objective.name: objective for objective in _objectives(game)}
    count = game.settings.high_command_orders
    return [_view(game, order, by_name.get(order.objective), count) for order in orders]


def _objectives(game: Game) -> Sequence[Objective]:
    """The enemy's objectives as they stand now, for what makes each hard and what
    it is worth. An order keeps the figures it was given with; these are current."""
    from game.highcommand.objectives import enemy_objectives

    return enemy_objectives(game)


def _view(
    game: Game, order: Order, objective: Optional[Objective], count: int
) -> OrderView:
    tgos = [tgo for tgo in game.theater.ground_objects if tgo.name == order.objective]
    motorpool = any(isinstance(tgo, MotorpoolGroundObject) for tgo in tgos)
    if order.task is not None:
        base = order.base
        name = order.base
        cp = next((cp for cp in game.theater.controlpoints if cp.name == base), None)
        position = cp.position if cp is not None else None
    else:
        base = tgos[0].control_point.name if tgos else ""
        name = order.objective
        position = tgos[0].position if tgos else None
    title, detail = taken_when(order, motorpool, _units_standing(tgos), base)
    prize = order.prize
    return OrderView(
        order=order,
        name=name,
        kind=order.kind,
        base=base,
        tier_chip=tier_chip(order.tier, count),
        tier_colour=tier_colour(order.tier, count),
        tier_words=tier_words(order.tier, count),
        asked=asked(order, motorpool),
        prize_line=prize.line if prize is not None else "No prize.",
        ticket=prize is not None and prize.ticket,
        turns_left=order.turns_left(game.turn),
        lifetime=order.expires_on - order.ordered_on,
        difficulty=order.difficulty,
        importance=order.importance,
        justification=order.justification,
        taken_title=title,
        taken_detail=detail,
        hazards=objective.hazards if objective is not None else (),
        worth=_worth(objective) if objective is not None else (),
        position=position,
    )


def _worth(objective: Objective) -> tuple[tuple[str, str], ...]:
    return tuple(
        (what, money(amount))
        for reason in objective.reasons
        for what, amount in (reason.parts or ((reason.kind, reason.worth),))
        if amount > 0
    )


def asked(order: Order, motorpool: bool) -> str:
    if order.task is not None:
        return ASKED[order.task]
    if motorpool:
        return "Destroy one of its vehicles"
    return "Destroy every unit"


def taken_when(order: Order, motorpool: bool, units: int, base: str) -> tuple[str, str]:
    """What counts as achieving the order, and a line on what that means here."""
    if order.task is Task.AIRCRAFT:
        return "One aircraft destroyed on the ground", f"at {base}"
    if order.task is Task.RUNWAY:
        return "The runway cratered", f"at {base}"
    if order.task is Task.CAPTURE:
        return "The base taken", f"{base} changes hands"
    if motorpool:
        return "One vehicle destroyed", "any of the vehicles parked there"
    return (
        "Every unit destroyed",
        f"{counted(units, 'unit')} · while the site is still the enemy's",
    )


def _units_standing(tgos: Sequence[object]) -> int:
    return sum(
        1
        for tgo in tgos
        for unit in getattr(tgo, "units", ())
        if getattr(unit, "alive", True)
    )


def enemy_side() -> str:
    return "RED" if ENEMY.is_red else "BLUE"


# --------------------------------------------------------------------- tickets

READY = "READY"
NOT_NOW = "NOT NOW"

#: What a ticket that asks nothing says it does when spent, by prize kind.
AT_ONCE = {
    "awacs": "Nothing to pick. It joins at once as a squadron on loan.",
    "tanker": "Nothing to pick. It joins at once as a squadron on loan.",
    "squadron": "Nothing to pick. It joins at once as a squadron on loan.",
}

#: What spending gives, from the labels of what was picked, by prize kind. It has to
#: say what the prize's own give says afterwards.
PREVIEWS: dict[str, Callable[[Sequence[str]], str]] = {
    "sam": lambda picked: f"{picked[1]} set up at {picked[0]}.",
    "runway": lambda picked: f"The runway at {picked[0]} is repaired.",
    "heal": lambda picked: f"{picked[0]} is back on duty.",
}


@dataclass(frozen=True)
class TicketView:
    ticket: Ticket
    #: The prize line, as the list shows it.
    line: str
    #: What spending it gives, as the spend pane's title.
    title: str
    earned: str
    #: READY, NOT NOW, or how many picks spending it asks.
    state: str

    @property
    def kind(self) -> Optional[PrizeKind]:
        return kind_of(self.ticket.prize)

    @property
    def steps(self) -> tuple[Step, ...]:
        kind = self.kind
        return kind.steps if kind is not None else ()


def ticket_views(game: Game) -> list[TicketView]:
    return [
        TicketView(
            ticket=ticket,
            line=ticket.prize.line,
            title=spending_title(ticket.prize.line),
            earned=f"earned by {ticket.earned_by} · turn {ticket.earned_on}",
            state=ticket_state(game, ticket),
        )
        for ticket in game.high_command.tickets
    ]


def ticket_state(game: Game, ticket: Ticket) -> str:
    """READY, NOT NOW when its first pick has nothing to pick from, or how many
    picks spending it asks."""
    kind = kind_of(ticket.prize)
    steps = kind.steps if kind is not None else ()
    if not steps:
        return READY
    if not steps[0].options(game, ticket.prize, ()):
        return NOT_NOW
    return f"{len(steps)} PICK" + ("S" if len(steps) > 1 else "")


def spending_title(line: str) -> str:
    """The prize line without its "A ticket for" or "A ticket to"."""
    for prefix in ("A ticket for ", "A ticket to "):
        if line.startswith(prefix):
            rest = line[len(prefix) :]
            return rest[:1].upper() + rest[1:]
    return line


def preview(kind: str, picked: Sequence[str]) -> str:
    """What spending gives, said before it is spent."""
    if kind in AT_ONCE:
        return AT_ONCE[kind]
    say = PREVIEWS.get(kind)
    return say(picked) if say is not None and picked else ""


# ----------------------------------------------------------------------- loans


@dataclass(frozen=True)
class LoanView:
    squadron: str
    aircraft: str
    #: The aircraft's DCS type id, which its banner is filed under.
    dcs_id: str
    count: int
    base: str
    #: The first turn the squadron is no longer the player's.
    until: int
    turns_left: int

    @property
    def last_turn(self) -> bool:
        return self.turns_left <= 1


def loan_views(game: Game) -> list[LoanView]:
    """The squadrons on loan, the soonest to go back first."""
    views = []
    for loan in game.high_command.loans:
        squadron = loan.squadron
        aircraft = squadron.aircraft
        views.append(
            LoanView(
                squadron=squadron.name,
                aircraft=str(aircraft),
                dcs_id=str(aircraft.dcs_unit_type.id),
                count=squadron.owned_aircraft,
                base=squadron.location.name,
                until=loan.until,
                turns_left=loan.until - game.turn,
            )
        )
    return sorted(views, key=lambda view: (view.until, view.squadron))
