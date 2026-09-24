"""A request and a ticket in words: what a request asks, what counts as achieving it,
whether a ticket can be spent now and what spending it gives. Shared by the player's
window and GeneraLLM's API, so both say the same."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

from game.highcommand.campaign import Task
from game.highcommand.orders import TIER_NAMES
from game.highcommand.prizes import kind_of
from game.highcommand.wording import counted

if TYPE_CHECKING:
    from game import Game
    from game.highcommand.orders import Order, Ticket

#: What each task asks of a base.
ASKED = {
    Task.AIRCRAFT: "OCA/Aircraft — destroy one on the ground",
    Task.RUNWAY: "OCA/Runway — crater the runway",
    Task.CAPTURE: "Capture — take the base",
}

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


def tier_words(tier: int, count: int) -> str:
    if count == len(TIER_NAMES) and tier < count:
        return f"{TIER_NAMES[tier]} tier"
    return f"tier {tier + 1} of {count}"


def asked(order: Order, motorpool: bool) -> str:
    if order.task is not None:
        return ASKED[order.task]
    if motorpool:
        return "Destroy one of its vehicles"
    return "Destroy every unit"


def taken_when(order: Order, motorpool: bool, units: int, base: str) -> tuple[str, str]:
    """What counts as achieving the request, and a line on what that means here."""
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


def units_standing(tgos: Sequence[object]) -> int:
    return sum(
        1
        for tgo in tgos
        for unit in getattr(tgo, "units", ())
        if getattr(unit, "alive", True)
    )


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
