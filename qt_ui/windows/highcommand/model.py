"""What the High Command window shows, worked out from the game before anything is
drawn."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Sequence

from dcs.mapping import Point

from game.highcommand.campaign import Task
from game.highcommand.describe import (  # noqa: F401 - the window's names for them
    ASKED,
    AT_ONCE,
    NOT_NOW,
    PREVIEWS,
    READY,
    asked,
    preview,
    spending_title,
    taken_when,
    ticket_state,
)
from game.highcommand.describe import units_standing as _units_standing
from game.highcommand.orders import TIER_NAMES, HighCommand, Order, Ticket
from game.highcommand.prizes import PrizeKind, Step, kind_of
from game.highcommand.wording import counted, money
from game.theater.player import Player
from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.highcommand.objectives import Objective

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
    #: Whose objective it is: RED for the player's requests, BLUE for the enemy's.
    owner: str = "RED"

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


def command_for(game: Game, side: Player) -> HighCommand:
    """The High Command of this side: the player's, or GeneraLLM's."""
    return game.high_command if side.is_blue else game.opfor_high_command


def headline(game: Game, side: Player = Player.BLUE) -> Headline:
    command = command_for(game, side)
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


def order_views(game: Game, side: Player = Player.BLUE) -> list[OrderView]:
    """The open orders, highest tier first, as the order list keeps them."""
    orders = list(command_for(game, side).orders)
    if not orders:
        return []
    by_name = {objective.name: objective for objective in _objectives(game, side)}
    count = game.settings.high_command_orders
    owner = side.opponent.value.upper()
    return [
        _view(game, order, by_name.get(order.objective), count, owner)
        for order in orders
    ]


def _objectives(game: Game, side: Player = Player.BLUE) -> Sequence[Objective]:
    """The other side's objectives as they stand now, for what makes each hard and
    what it is worth. An order keeps the figures it was given with; these are current.
    """
    from game.highcommand.objectives import enemy_objectives

    return enemy_objectives(game, side)


def _view(
    game: Game,
    order: Order,
    objective: Optional[Objective],
    count: int,
    owner: str = "RED",
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
        owner=owner,
    )


def _worth(objective: Objective) -> tuple[tuple[str, str], ...]:
    return tuple(
        (what, money(amount))
        for reason in objective.reasons
        for what, amount in (reason.parts or ((reason.kind, reason.worth),))
        if amount > 0
    )


# --------------------------------------------------------------------- tickets


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


def ticket_views(game: Game, side: Player = Player.BLUE) -> list[TicketView]:
    return [
        TicketView(
            ticket=ticket,
            line=ticket.prize.line,
            title=spending_title(ticket.prize.line),
            earned=f"earned by {ticket.earned_by} · turn {ticket.earned_on}",
            state=ticket_state(game, ticket),
        )
        for ticket in command_for(game, side).tickets
    ]


# --------------------------------------------------------------------- effects


@dataclass(frozen=True)
class EffectView:
    label: str
    earned_by: str
    until: int
    turns_left: int

    @property
    def last_turn(self) -> bool:
        return self.turns_left <= 1


def effect_views(game: Game, side: Player = Player.BLUE) -> list[EffectView]:
    """The effects running, the soonest to end first."""
    views = [
        EffectView(
            label=effect.label,
            earned_by=effect.earned_by,
            until=effect.until,
            turns_left=effect.turns_left(game.turn),
        )
        for effect in command_for(game, side).effects
    ]
    return sorted(views, key=lambda view: (view.until, view.label))


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


def loan_views(game: Game, side: Player = Player.BLUE) -> list[LoanView]:
    """The squadrons on loan, the soonest to go back first."""
    views = []
    for loan in command_for(game, side).loans:
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
