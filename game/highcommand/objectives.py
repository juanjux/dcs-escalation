"""The enemy objectives the High Command can order attacked: how hard each one is to
get at, how much it matters, one line on why it is worth attacking, and what taking it
pays.

What getting at an objective takes, its effort, adds up three things, each in points:

* the route, which weighs the most: the cheapest way from one of our bases to a point
  a weapon can reach the objective from, a mile inside an enemy ring costing more than
  a mile outside, and more the further that site reaches and the closer the route
  passes to it (``approach.py``). Our aircraft release bombs and Mavericks close in,
  and whatever longer-reaching weapon they carry from further out, so a battery on the
  coast is hit from outside its ring, and an objective behind two rings costs the
  detour or the rings;
* the enemy fighters based within reach of it;
* how much of it there is to destroy.

What losing it costs the enemy, its worth, is in ``importance.py``.

Difficulty and importance, from 1 to 5, are where the effort and the worth fall among
all of the enemy's objectives, in fifths: 1 for the easiest or least important fifth,
5 for the hardest or most important. A campaign where a long-range SAM covers
everything would otherwise rate nearly everything the same; the effort and the worth
themselves stay on the objective for whatever needs a number that means the same in
every campaign.

The line is the objective's reason worth the most. The least important fifth gets a
comical one instead (``comical.py``).

The prize is drawn for the objective's score, its difficulty plus its importance
(``prizes.py``).
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Optional, Sequence

from dcs import Point

from game.data.units import UnitClass
from game.highcommand.campaign import Campaign, Task
from game.highcommand.comical import comical_lines
from game.highcommand.importance import Reason, Worth, by_worth
from game.highcommand.prizes import Prize, Prizes
from game.highcommand.wording import alive, system_name
from game.theater import Airfield, MissionTarget, Player
from game.theater.theatergroundobject import (
    NAME_BY_CATEGORY,
    AirDefenceKind,
    GenericCarrierGroundObject,
    IadsGroundObject,
    NavalGroundObject,
    TheaterGroundObject,
)
from game.utils import nautical_miles

if TYPE_CHECKING:
    from game import Game

#: The justification of an objective too unimportant to have a serious one, until
#: a comical line is picked for it.
COMICAL = "XXX comical"

#: Miles of route, counted outside every ring, that make a point of effort. Low
#: enough for the route to outweigh the fighters and the size: how far an objective is
#: and what stands in the way decide most of how hard it is.
ROUTE_MILES_PER_POINT = 60.0

#: A ring adding less than this to a route, in miles, is not named among what makes an
#: objective hard.
NAMED_RING_COST = 50.0

#: A route shorter than this is not worth naming either.
NAMED_LENGTH = 100.0

#: Fighters based this close to an objective can be over it before a package is.
FIGHTER_REACH = nautical_miles(150)
FIGHTERS_PER_POINT = 12
MAX_FIGHTER_POINTS = 2.0

#: What one flight takes care of, and how many units more make a point. A warship
#: counts as several.
FREE_UNITS = 4
UNITS_PER_POINT = 12
WARSHIP_UNITS = 3
MAX_SIZE_POINTS = 1.0

#: How many difficulties and importances there are.
LEVELS = 5

UNIT_CLASSES_AT_SEA = frozenset(
    {
        UnitClass.AIRCRAFT_CARRIER,
        UnitClass.HELICOPTER_CARRIER,
        UnitClass.LANDING_SHIP,
        UnitClass.CRUISER,
        UnitClass.DESTROYER,
        UnitClass.FRIGATE,
        UnitClass.SUBMARINE,
    }
)


@dataclass(frozen=True)
class Effort:
    """What getting at an objective takes, in points."""

    route: float
    fighters: float
    size: float

    @property
    def total(self) -> float:
        return self.route + self.fighters + self.size


@dataclass(frozen=True)
class Objective:
    """One enemy objective the High Command can order attacked."""

    name: str
    #: What it is, as the map calls it.
    kind: str
    #: Its ground objects, or the base itself for an airfield.
    targets: tuple[MissionTarget, ...]
    effort: Effort
    #: What makes it as hard as it is, the worst first.
    hazards: tuple[str, ...]
    #: What makes it worth attacking, the one worth the most first.
    reasons: tuple[Reason, ...] = ()
    #: From 1 to 5, against the rest of the enemy's objectives.
    difficulty: int = 0
    importance: int = 0
    #: Why it is worth attacking, in one line, or COMICAL.
    justification: str = ""
    #: What taking it pays; None when no prize fits.
    prize: Optional[Prize] = None
    #: What is asked of a base; None for a ground object.
    task: Optional[Task] = None

    @property
    def position(self) -> Point:
        return self.targets[0].position

    @property
    def score(self) -> int:
        """What the prize is worked out for, from 2 to 10."""
        return self.difficulty + self.importance

    @property
    def worth(self) -> float:
        """What losing it costs the enemy, in millions."""
        return sum(reason.worth for reason in self.reasons)


def enemy_objectives(game: Game, player: Player = Player.BLUE) -> list[Objective]:
    """Every objective of ``player``'s enemy still standing, easiest first."""
    campaign = Campaign(game, player)
    worth = Worth(campaign)
    found: list[Objective] = []
    for name, tgos in campaign.groups.items():
        at_sea = isinstance(tgos[0], NavalGroundObject)
        effort, hazards = _effort(campaign, name, tgos[0].position, _size(tgos), at_sea)
        found.append(
            Objective(
                name=name,
                kind=_kind(tgos[0]),
                targets=tuple(tgos),
                effort=effort,
                hazards=hazards,
                reasons=worth.own(tgos),
            )
        )
    for cp in campaign.enemy_bases():
        for task in campaign.tasks_at(cp):
            name = base_objective_name(cp.name, task)
            effort, hazards = _effort(
                campaign, name, cp.position, campaign.defenders(cp, task), False
            )
            found.append(
                Objective(
                    name=name,
                    kind="Airfield" if isinstance(cp, Airfield) else "FOB",
                    targets=(cp,),
                    effort=effort,
                    hazards=hazards,
                    reasons=worth.own_base(cp, task),
                    task=task,
                )
            )
    shared = worth.shared(found)
    found = ranked(
        [
            replace(o, reasons=by_worth([*o.reasons, *shared.get(o.name, ())]))
            for o in found
        ]
    )
    comical = comical_lines([o for o in found if o.importance == 1], seed=game.turn)
    prizes = Prizes.of(game, player)
    found = [
        replace(
            o,
            justification=comical.get(o.name, o.justification),
            prize=prizes.draw(o.score, seed=f"{game.turn}:{o.name}"),
        )
        for o in found
    ]
    return sorted(found, key=lambda o: (o.effort.total, o.name))


def base_objective_name(base: str, task: Task) -> str:
    """A base is an objective once for each thing asked of it."""
    return f"{base} ({task.value})"


def ranked(objectives: Sequence[Objective]) -> list[Objective]:
    """The objectives with their difficulty and importance, and the line that goes
    with the importance."""
    difficulties = fifths([o.effort.total for o in objectives])
    importances = fifths([o.worth for o in objectives])
    return [
        replace(
            o,
            difficulty=difficulty,
            importance=importance,
            justification=(
                o.reasons[0].line if importance > 1 and o.reasons else COMICAL
            ),
        )
        for o, difficulty, importance in zip(objectives, difficulties, importances)
    ]


def fifths(values: Sequence[float]) -> list[int]:
    """The fifth each value falls in among all of them, from 1 to 5.

    Equal values get the same level, whichever side of a fifth they would otherwise
    straddle.
    """
    ordered = sorted(values)
    count = len(ordered)
    return [
        1 + min(LEVELS - 1, LEVELS * bisect_left(ordered, value) // count)
        for value in values
    ]


def _effort(
    campaign: Campaign, name: str, position: Point, units: int, at_sea: bool
) -> tuple[Effort, tuple[str, ...]]:
    hazards: list[str] = []

    route_points = 0.0
    if campaign.approach is not None:
        route = campaign.approach.route(
            position, campaign.sea_releases if at_sea else campaign.land_releases
        )
        route_points = (route.cost + route.release.penalty) / ROUTE_MILES_PER_POINT
        for cost, ring in route.rings[:2]:
            if cost < NAMED_RING_COST:
                break
            system = system_name(ring.site)
            site = ring.site.name
            hazards.append(
                f"its own {system}" if site == name else f"{system} at {site}"
            )
        if route.base is not None and route.length >= NAMED_LENGTH:
            hazards.append(f"{route.length:.0f} nm from {route.base.name}")

    fighters = sum(
        count
        for cp, count in campaign.fighters.items()
        if cp.position.distance_to_point(position) <= FIGHTER_REACH.meters
    )
    if fighters:
        hazards.append(
            f"{fighters} fighters within {FIGHTER_REACH.nautical_miles:.0f} nm"
        )

    size_points = min(MAX_SIZE_POINTS, max(0.0, (units - FREE_UNITS) / UNITS_PER_POINT))
    if size_points >= 0.5:
        hazards.append(f"{units} units to destroy")

    effort = Effort(
        route=route_points,
        fighters=min(MAX_FIGHTER_POINTS, fighters / FIGHTERS_PER_POINT),
        size=size_points,
    )
    return effort, tuple(hazards)


def _size(tgos: Sequence[TheaterGroundObject]) -> int:
    """How many things there are to destroy, a warship counting as several."""
    return sum(
        (
            WARSHIP_UNITS
            if getattr(unit.unit_type, "unit_class", None) in UNIT_CLASSES_AT_SEA
            else 1
        )
        for unit in alive(tgos)
    )


def _kind(tgo: TheaterGroundObject) -> str:
    if isinstance(tgo, GenericCarrierGroundObject):
        return "Carrier group"
    if isinstance(tgo, IadsGroundObject):
        kind = tgo.air_defence_kind
        if kind is AirDefenceKind.JAMMER:
            return "GPS jammer"
        if kind is AirDefenceKind.RADAR:
            return NAME_BY_CATEGORY["ewr"]
        return NAME_BY_CATEGORY["aa"]
    return NAME_BY_CATEGORY.get(tgo.category, tgo.category)
