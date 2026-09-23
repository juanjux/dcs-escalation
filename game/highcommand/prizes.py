"""What the High Command pays for taking an objective.

An objective's score is its difficulty plus its importance, from 2 to 10. Each kind of
prize (KINDS) says what it takes to be offered: the lowest score it can be won with,
which for most of them is any, and whatever the campaign must have for it, such as
pilots with morale. An objective's prize is drawn among the kinds its score reaches and
worked out to that score when the objective is marked, so the player knows what taking
it pays before trying.

Most prizes take effect when the objective falls. A ticket is kept instead, and spent
whenever the player chooses, on what its steps ask the player to pick. How a kind is
given is registered with it (``_gives``), and a kind the game cannot give yet is not
drawn.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Callable, Optional

from game.ato.flighttype import FlightType
from game.data.groups import GroupTask
from game.data.units import UnitClass
from game.highcommand.wording import counted, joined, money
from game.income import Income
from game.squadrons.experience import SaveCompatible
from game.squadrons.morale import clamp
from game.squadrons.pilot import PilotStatus
from game.theater import Airfield, Player

if TYPE_CHECKING:
    from game import Game
    from game.factions.faction import Faction
    from game.squadrons.pilot import Pilot

MIN_SCORE = 2
MAX_SCORE = 10

#: Who the prizes are for: the side the High Command gives its orders to.
PLAYER = Player.BLUE

#: The five rungs of pilot skill, as the mission editor names them.
RUNGS = ("Cadet", "Rookie", "Trained", "Veteran", "Ace")

#: What a price cut can be on, one of them a prize.
DISCOUNTS = ("aircraft", "SAM batteries", "building repairs", "ground units")

#: What a repair-time cut can be on, one of them a prize.
REPAIRS = ("units", "buildings")

#: A SAM battery's reach, by the lowest score that earns it.
SAM_BANDS = (
    (8, GroupTask.LORAD, "long-range"),
    (5, GroupTask.MERAD, "medium-range"),
    (MIN_SCORE, GroupTask.SHORAD, "short-range"),
)

#: What an aircraft on loan has to be able to do.
COMBAT_TASKS = frozenset(
    {
        FlightType.BARCAP,
        FlightType.STRIKE,
        FlightType.CAS,
        FlightType.BAI,
        FlightType.SEAD,
        FlightType.DEAD,
        FlightType.ANTISHIP,
    }
)

#: How many kinds of vehicle a prize of armour comes in, at most, and of what classes:
#: armour, not the air defence and trucks that also drive to the front.
ARMOUR_TYPES = 3
ARMOUR_CLASSES = frozenset(
    {
        UnitClass.TANK,
        UnitClass.IFV,
        UnitClass.APC,
        UnitClass.ATGM,
        UnitClass.ARTILLERY,
        UnitClass.RECON,
    }
)


@dataclass(frozen=True)
class Prize(SaveCompatible):
    """A prize as worked out for one objective. Kept in the save with its order."""

    #: Which of KINDS it is, by key.
    kind: str
    score: int
    #: Kept to be spent when the player chooses, rather than given when the objective
    #: falls.
    ticket: bool
    #: What it is, in a line for the player.
    line: str
    #: The numbers it was worked out to, by name, for whatever gives it.
    terms: tuple[tuple[str, Any], ...] = ()

    def term(self, name: str) -> Any:
        return dict(self.terms)[name]


@dataclass(frozen=True)
class Context:
    """What working out a prize can look at: the player's side of the campaign."""

    settings: Any
    faction: Faction
    #: The player's income per turn, in millions.
    income: float
    rng: random.Random


#: A prize's line and terms at a score, or None when it cannot be given at that score.
Worked = Optional[tuple[str, dict[str, Any]]]
WorkOut = Callable[[int, Context], Worked]


@dataclass(frozen=True)
class Choice:
    """One thing a ticket can be spent on."""

    #: What the prize reads back when it is given.
    key: str
    #: What the player sees.
    label: str
    detail: str = ""


#: The options for a step, given the keys picked in the steps before it.
Options = Callable[["Game", Prize, tuple[str, ...]], list[Choice]]


@dataclass(frozen=True)
class Step:
    """One thing a ticket asks the player to pick before it is spent. With nothing to
    pick from, the ticket cannot be spent yet."""

    question: str
    options: Options


#: Gives a prize, with what was picked for each of its steps, and says what it gave.
Give = Callable[["Game", Prize, tuple[str, ...]], str]


def _always(settings: Any) -> bool:
    return True


@dataclass(frozen=True)
class PrizeKind:
    """One kind of prize: when it can be offered, and what it is worth at a score."""

    key: str
    work_out: WorkOut
    #: The lowest score it can be won with.
    min_score: int = MIN_SCORE
    ticket: bool = False
    #: Whether a campaign's settings have what it needs.
    needs: Callable[[Any], bool] = _always
    #: How it is given; None while the game cannot give it, and it is not drawn.
    give: Optional[Give] = None
    #: What spending it asks the player to pick, in order.
    steps: tuple[Step, ...] = ()

    def prize(self, score: int, context: Context) -> Optional[Prize]:
        worked = self.work_out(score, context)
        if worked is None:
            return None
        line, terms = worked
        return Prize(self.key, score, self.ticket, line, tuple(sorted(terms.items())))


KINDS: list[PrizeKind] = []


def _kind(
    key: str,
    *,
    min_score: int = MIN_SCORE,
    ticket: bool = False,
    needs: Callable[[Any], bool] = _always,
) -> Callable[[WorkOut], WorkOut]:
    def register(work_out: WorkOut) -> WorkOut:
        KINDS.append(PrizeKind(key, work_out, min_score, ticket, needs))
        return work_out

    return register


def _gives(key: str, *steps: Step) -> Callable[[Give], Give]:
    """How the kind registered as ``key`` is given, and what spending it asks first."""

    def register(give: Give) -> Give:
        at = next(n for n, kind in enumerate(KINDS) if kind.key == key)
        KINDS[at] = replace(KINDS[at], give=give, steps=steps)
        return give

    return register


def kind_of(prize: Prize) -> Optional[PrizeKind]:
    """The kind a prize was drawn as; None if the game no longer has it."""
    return next((kind for kind in KINDS if kind.key == prize.kind), None)


class Prizes:
    """Draws the prizes of one side's objectives."""

    def __init__(self, settings: Any, faction: Faction, income: float) -> None:
        self.settings = settings
        self.faction = faction
        self.income = income

    @classmethod
    def of(cls, game: Game, player: Player) -> Prizes:
        return cls(
            game.settings,
            game.coalition_for(player).faction,
            Income(game, player).total,
        )

    def draw(self, score: int, seed: object) -> Optional[Prize]:
        """A prize for an objective of this score. The same seed draws the same one."""
        rng = random.Random(str(seed))
        kinds = [
            kind
            for kind in KINDS
            if kind.min_score <= score
            and kind.needs(self.settings)
            and kind.give is not None
        ]
        rng.shuffle(kinds)
        context = Context(self.settings, self.faction, self.income, rng)
        for kind in kinds:
            prize = kind.prize(score, context)
            if prize is not None:
                return prize
        return None


def half_up(score: int) -> int:
    """Half the score, rounded up: the turns most prizes last."""
    return max(1, math.ceil(score / 2))


def _turns(turns: int) -> str:
    return counted(turns, "turn")


# ------------------------------------------------------------ what they need


def _live_pilots(settings: Any) -> bool:
    return bool(settings.live_pilots_enabled)


def _morale(settings: Any) -> bool:
    return _live_pilots(settings) and bool(settings.morale_enabled)


def _fog_of_war(settings: Any) -> bool:
    """The game has no fog of war yet: every site is on both sides' maps, and there is
    nothing to reconnoitre."""
    return False


def _hidden_enemy_plan(settings: Any) -> bool:
    """The enemy's packages are on the map for anyone to see: its plan is worth nothing
    as a prize until it is not."""
    return False


# ------------------------------------------------------------------ the kinds


@_kind("faction-xp", needs=_live_pilots)
def _faction_xp(score: int, context: Context) -> Worked:
    percent = max(1.0, score / 2)
    turns = half_up(score)
    return (
        f"+{percent:g}% XP for all our pilots for {_turns(turns)}.",
        {"percent": percent, "turns": turns},
    )


@_kind("package-xp", needs=_live_pilots)
def _package_xp(score: int, context: Context) -> Worked:
    return (
        f"+{score}% XP for the pilots of the package that destroys it.",
        {"percent": score},
    )


@_kind("cash")
def _cash(score: int, context: Context) -> Worked:
    # Paid out of the income when the objective falls; today's is an estimate.
    share = score / 5
    return (
        f"Cash worth {share:.0%} of our income per turn, about "
        f"{money(context.income * share)} today.",
        {"income_share": share},
    )


@_kind("pilots")
def _pilots(score: int, context: Context) -> Worked:
    count = half_up(score)
    rung = RUNGS[min(len(RUNGS), half_up(score)) - 1]
    turns = half_up(score)
    return (
        f"{counted(count, f'extra {rung} pilot')} for {_turns(turns)}, over a "
        "squadron's limit, so that others can rest.",
        {"pilots": count, "skill": rung, "turns": turns},
    )


@_kind("discount")
def _discount(score: int, context: Context) -> Worked:
    percent = 7 * score
    turns = half_up(score)
    what = context.rng.choice(DISCOUNTS)
    return (
        f"{percent}% off {what} for {_turns(turns)}.",
        {"percent": percent, "on": what, "turns": turns},
    )


@_kind("faster-repairs")
def _faster_repairs(score: int, context: Context) -> Worked:
    percent = min(100, 10 * score)
    turns = half_up(score)
    what = context.rng.choice(REPAIRS)
    if percent >= 100:
        line = f"Repairs to our {what} are instant for {_turns(turns)}."
    else:
        line = (
            f"Repairs to our {what} take {percent}% fewer turns, at least one fewer, "
            f"for {_turns(turns)}."
        )
    return line, {"percent": percent, "on": what, "turns": turns}


@_kind("hospital", needs=_live_pilots)
def _hospital(score: int, context: Context) -> Worked:
    turns = 1 if score <= 5 else 2
    return (
        f"Our wounded pilots leave hospital {_turns(turns)} early.",
        {"turns": turns},
    )


@_kind("morale", needs=_morale)
def _morale_boost(score: int, context: Context) -> Worked:
    points = 2 * score
    return f"+{points} morale for all our pilots.", {"points": points}


@_kind("aircraft")
def _aircraft(score: int, context: Context) -> Worked:
    return (
        f"{score} new aircraft for a squadron of our choice, up to its limit.",
        {"aircraft": score},
    )


@_kind("loaned-aircraft")
def _loaned_aircraft(score: int, context: Context) -> Worked:
    turns = half_up(score)
    return (
        f"{score} aircraft on loan to a squadron of our choice for {_turns(turns)}, "
        "over its limit.",
        {"aircraft": score, "turns": turns},
    )


@_kind("sam", ticket=True)
def _sam(score: int, context: Context) -> Worked:
    has = {task for group in context.faction.preset_groups for task in group.tasks}
    for lowest, task, reach in SAM_BANDS:
        if score >= lowest and task in has:
            return (
                f"A ticket for a {reach} SAM battery where we choose, or one of ours "
                "rebuilt or converted for free.",
                {"band": task.name},
            )
    return None


@_kind("armour")
def _armour(score: int, context: Context) -> Worked:
    types = sorted(
        (
            unit
            for unit in context.faction.frontline_units
            if unit.unit_class in ARMOUR_CLASSES
        ),
        key=lambda unit: unit.variant_id,
    )
    if not types:
        return None
    chosen = context.rng.sample(types, min(ARMOUR_TYPES, len(types)))
    counts = [score // len(chosen)] * len(chosen)
    for n in range(score % len(chosen)):
        counts[n] += 1
    parts = [(str(unit), n) for unit, n in zip(chosen, counts) if n]
    return (
        f"{score} armoured vehicles ({joined([f'{n} {name}' for name, n in parts])}) "
        "for the front or a base of our choice.",
        {"vehicles": tuple(parts)},
    )


@_kind("runway", min_score=8, ticket=True)
def _runway(score: int, context: Context) -> Worked:
    return "A ticket for an instant repair of one of our runways.", {}


@_kind("squadron", ticket=True)
def _squadron(score: int, context: Context) -> Worked:
    fleet = sorted(
        (
            aircraft
            for aircraft in context.faction.aircraft
            if COMBAT_TASKS & set(aircraft.task_priorities)
        ),
        key=lambda aircraft: (aircraft.price, aircraft.display_name),
    )
    if not fleet:
        return None
    # The better the score, the dearer the aircraft.
    pick = round((score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE) * (len(fleet) - 1))
    aircraft = fleet[pick]
    count = 2 * score
    turns = half_up(score)
    return (
        f"A ticket for a squadron of {count} {aircraft.display_name} on loan for "
        f"{_turns(turns)}.",
        {"aircraft": count, "type": aircraft.display_name, "turns": turns},
    )


@_kind("ace", min_score=7, needs=_live_pilots)
def _ace(score: int, context: Context) -> Worked:
    return (
        "An Ace joins a squadron of our choice. A full squadron retires one of its "
        "pilots to make room.",
        {},
    )


@_kind("awacs", ticket=True)
def _awacs(score: int, context: Context) -> Worked:
    turns = half_up(score)
    return f"A ticket for an extra AWACS for {_turns(turns)}.", {"turns": turns}


@_kind("tanker", ticket=True)
def _tanker(score: int, context: Context) -> Worked:
    turns = half_up(score)
    return f"A ticket for an extra tanker for {_turns(turns)}.", {"turns": turns}


@_kind("heal", min_score=6, ticket=True, needs=_live_pilots)
def _heal(score: int, context: Context) -> Worked:
    return (
        "A ticket to put one wounded pilot of our choice back on duty at once.",
        {},
    )


@_kind("pilot-limit")
def _pilot_limit(score: int, context: Context) -> Worked:
    return (
        f"A squadron of our choice takes {score} more pilots, for good.",
        {"pilots": score},
    )


@_kind("aircraft-limit")
def _aircraft_limit(score: int, context: Context) -> Worked:
    return (
        f"A squadron of our choice takes {score} more aircraft, for good.",
        {"aircraft": score},
    )


@_kind("recon", needs=_fog_of_war)
def _recon(score: int, context: Context) -> Worked:
    return (
        f"Reconnaissance of {counted(score, 'site')} of our choice.",
        {"sites": score},
    )


@_kind("sigint", min_score=8, needs=_fog_of_war)
def _sigint(score: int, context: Context) -> Worked:
    return "SIGINT reveals the enemy's whole air defence network.", {}


@_kind("enemy-plan", needs=_hidden_enemy_plan)
def _enemy_plan(score: int, context: Context) -> Worked:
    if score >= MAX_SCORE:
        return "The enemy's whole plan for next turn.", {"packages": None}
    return (
        f"{counted(score, 'package')} of the enemy's plan for next turn.",
        {"packages": score},
    )


@_kind("enemy-income")
def _enemy_income(score: int, context: Context) -> Worked:
    # A point takes an eleventh: ten points leave the enemy a tenth of its income.
    percent = math.floor(100 * score / 11)
    turns = half_up(score)
    return (
        f"The enemy's income cut by {percent}% for {_turns(turns)}.",
        {"percent": percent, "turns": turns},
    )


@_kind("enemy-repairs")
def _enemy_repairs(score: int, context: Context) -> Worked:
    percent = 10 * score
    turns = half_up(score)
    return (
        f"Enemy repairs take {percent}% more turns, at least one more, for "
        f"{_turns(turns)}.",
        {"percent": percent, "turns": turns},
    )


# ---------------------------------------------------------------- giving them


def _our_pilots(game: Game) -> list[tuple[Any, Pilot]]:
    """Every pilot of ours still in the war, with his squadron."""
    gone = (PilotStatus.Dead, PilotStatus.Deserted, PilotStatus.Discharged)
    return [
        (squadron, pilot)
        for squadron in game.coalition_for(PLAYER).air_wing.iter_squadrons()
        for pilot in squadron.current_roster
        if pilot.status not in gone
    ]


def _broken_runways(game: Game, prize: Prize, picked: tuple[str, ...]) -> list[Choice]:
    return [
        Choice(cp.name, cp.name, str(cp.runway_status))
        for cp in game.theater.controlpoints
        if cp.captured == PLAYER
        and isinstance(cp, Airfield)
        and cp.runway_status.damaged
    ]


def _wounded_pilots(game: Game, prize: Prize, picked: tuple[str, ...]) -> list[Choice]:
    return [
        Choice(
            str(pilot.id),
            pilot.name,
            f"{squadron.name}, {squadron.aircraft}: "
            f"{_turns(pilot.wounded_turns)} in hospital",
        )
        for squadron, pilot in _our_pilots(game)
        if pilot.status is PilotStatus.Wounded
    ]


@_gives("cash")
def _give_cash(game: Game, prize: Prize, picked: tuple[str, ...]) -> str:
    amount = Income(game, PLAYER).total * prize.term("income_share")
    game.coalition_for(PLAYER).adjust_budget(amount)
    return f"{money(amount)} added to our budget."


@_gives("morale")
def _give_morale(game: Game, prize: Prize, picked: tuple[str, ...]) -> str:
    points = prize.term("points")
    pilots = _our_pilots(game)
    for _, pilot in pilots:
        pilot.morale = clamp(pilot.morale + points)
    return f"+{points} morale for our {counted(len(pilots), 'pilot')}."


@_gives("hospital")
def _give_hospital(game: Game, prize: Prize, picked: tuple[str, ...]) -> str:
    turns = prize.term("turns")
    wounded = [p for _, p in _our_pilots(game) if p.status is PilotStatus.Wounded]
    if not wounded:
        return "None of our pilots was in hospital."
    for pilot in wounded:
        pilot.wounded_turns -= turns
        if pilot.wounded_turns <= 0:
            pilot.recover()
    back = sum(1 for pilot in wounded if pilot.status is PilotStatus.Active)
    return (
        f"{counted(len(wounded), 'wounded pilot')} out of hospital {_turns(turns)} "
        f"early, {back} of them at once."
    )


@_gives("runway", Step("Which runway?", _broken_runways))
def _give_runway(game: Game, prize: Prize, picked: tuple[str, ...]) -> str:
    base = next(cp for cp in game.theater.controlpoints if cp.name == picked[0])
    base.runway_status.repair()
    return f"The runway at {base.name} is repaired."


@_gives("heal", Step("Which pilot?", _wounded_pilots))
def _give_heal(game: Game, prize: Prize, picked: tuple[str, ...]) -> str:
    squadron, pilot = next(
        (squadron, pilot)
        for squadron, pilot in _our_pilots(game)
        if str(pilot.id) == picked[0]
    )
    pilot.recover()
    return f"{pilot.name}, of {squadron.name}, is back on duty."
