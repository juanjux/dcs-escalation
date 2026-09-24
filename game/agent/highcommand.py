"""GeneraLLM's High Command: the requests it has been given, its tickets, effects,
loans and history, and spending a ticket. The records the player's window reads, for
the side GeneraLLM plays."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence

from game.agent import schemas, views
from game.highcommand.describe import (
    asked,
    preview,
    taken_when,
    ticket_state,
    units_standing,
)
from game.highcommand.orders import Order, Ticket, tier_name
from game.highcommand.prizes import CannotGive, Choice, kind_of
from game.theater.theatergroundobject import MotorpoolGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.highcommand.orders import HighCommand

#: How many of the latest history entries a read returns by default.
HISTORY_SHOWN = 20


def high_command(game: Game, side: str, history: int = HISTORY_SHOWN) -> dict:
    """Everything the side's High Command holds, in one read."""
    player = views.player_for_side(side)
    command = game.high_command_for(player)
    count = game.settings.high_command_orders
    return {
        "enabled": bool(game.settings.high_command_enabled),
        "active": bool(game.opfor_high_command_active),
        "turn": game.turn,
        "requests": [_request(game, order, count) for order in command.orders],
        "tickets": [
            _ticket(game, index, ticket) for index, ticket in enumerate(command.tickets)
        ],
        "effects": [
            {
                "label": effect.label,
                "earned_by": effect.earned_by,
                "turns_left": effect.turns_left(game.turn),
            }
            for effect in command.effects
        ],
        "loans": [
            {
                "squadron": loan.squadron.name,
                "squadron_id": str(loan.squadron.id),
                "aircraft": str(loan.squadron.aircraft),
                "count": loan.squadron.owned_aircraft,
                "base": loan.squadron.location.name,
                "turns_left": loan.until - game.turn,
            }
            for loan in command.loans
        ],
        "history": [
            {
                "turn": entry.turn,
                "outcome": entry.outcome,
                "name": entry.name,
                "line": entry.line,
            }
            for entry in command.history[-max(0, history) :]
        ],
    }


def _request(game: Game, order: Order, count: int) -> dict:
    tgos = [tgo for tgo in game.theater.ground_objects if tgo.name == order.objective]
    motorpool = any(isinstance(tgo, MotorpoolGroundObject) for tgo in tgos)
    target: Any = None
    if order.task is not None:
        target = next(
            (cp for cp in game.theater.controlpoints if cp.name == order.base), None
        )
        base = order.base
    else:
        target = tgos[0] if tgos else None
        base = tgos[0].control_point.name if tgos else ""
    done, detail = taken_when(order, motorpool, units_standing(tgos), base)
    view: dict[str, Any] = {
        "objective": order.objective,
        "kind": order.kind,
        "base": base,
        "asked": asked(order, motorpool),
        "done_when": f"{done}: {detail}",
        "tier": tier_name(order.tier, count),
        "difficulty": order.difficulty,
        "importance": order.importance,
        "turns_left": order.turns_left(game.turn),
        "why": order.justification,
    }
    if order.prize is not None:
        view["prize"] = {"line": order.prize.line, "ticket": order.prize.ticket}
    if target is not None:
        # The id create_packages takes as a target, and where it is.
        view["target_id"] = str(target.id)
        latlng = target.position.latlng()
        view["pos"] = [round(latlng.lat, 5), round(latlng.lng, 5)]
    return view


def _ticket(game: Game, index: int, ticket: Ticket) -> dict:
    kind = kind_of(ticket.prize)
    return {
        "index": index,
        "line": ticket.prize.line,
        "earned_by": ticket.earned_by,
        "earned_on": ticket.earned_on,
        "state": ticket_state(game, ticket),
        "steps": [step.question for step in (kind.steps if kind else ())],
    }


def _ticket_at(command: HighCommand, index: int) -> Ticket:
    if not 0 <= index < len(command.tickets):
        raise ValueError(
            f"no ticket {index}: there are {len(command.tickets)}; read high_command "
            "again, the list shifts when one is spent"
        )
    return command.tickets[index]


def _resolve(
    game: Game, ticket: Ticket, picked: Sequence[str]
) -> tuple[list[Choice], Optional[dict]]:
    """Walk the ticket's steps with the picks given: the choices made, and the step
    still to answer when there is one (with its question and options)."""
    kind = kind_of(ticket.prize)
    if kind is None or kind.give is None:
        raise ValueError(f"the game can no longer give a {ticket.prize.kind} prize")
    made: list[Choice] = []
    for number, step in enumerate(kind.steps):
        options = step.options(game, ticket.prize, tuple(c.key for c in made))
        if number < len(picked):
            chosen = next((c for c in options if c.key == picked[number]), None)
            if chosen is None:
                raise ValueError(
                    f"step {number} ({step.question}) has no choice {picked[number]!r}"
                )
            made.append(chosen)
            continue
        if step.auto and len(options) == 1:
            made.append(options[0])
            continue
        return made, {
            "step": number,
            "question": step.question,
            "choices": [
                {"key": c.key, "label": c.label, "detail": c.detail} for c in options
            ],
            "blocked": not options,
        }
    return made, None


def ticket_choices(game: Game, side: str, ticket: int, picked: Sequence[str]) -> dict:
    """The next thing spending a ticket asks, given what has been picked so far; or,
    with every step answered, what spending it would give."""
    player = views.player_for_side(side)
    chosen = _ticket_at(game.high_command_for(player), ticket)
    made, pending = _resolve(game, chosen, picked)
    if pending is not None:
        return {"ticket": ticket, "done": False, **pending}
    return {
        "ticket": ticket,
        "done": True,
        "picked": [c.key for c in made],
        "gives": preview(chosen.prize.kind, [c.label for c in made])
        or chosen.prize.line,
    }


def spend_ticket(
    game: Game, side: str, ticket: int, picked: Sequence[str]
) -> schemas.OpResult:
    """Spend a ticket on what was picked for its steps. It is gone once spent; one the
    game cannot give now stays, with the reason."""
    try:
        player = views.player_for_side(side)
        command = game.high_command_for(player)
        chosen = _ticket_at(command, ticket)
        made, pending = _resolve(game, chosen, picked)
        if pending is not None:
            if pending["blocked"]:
                raise ValueError(
                    f"{pending['question']} has nothing to pick from now; the ticket "
                    "stays until it has"
                )
            raise ValueError(
                f"step {pending['step']} ({pending['question']}) needs a pick; ask "
                "high_command/ticket_choices for the options"
            )
        line = command.spend(game, chosen, tuple(c.key for c in made))
        return schemas.OpResult(ok=True, detail=line)
    except (CannotGive, ValueError) as exc:
        return schemas.OpResult(ok=False, error=str(exc))
