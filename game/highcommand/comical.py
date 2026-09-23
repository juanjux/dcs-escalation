"""Comical justifications for the objectives too unimportant to have a serious one.

The lines are in resources/highcommand/comical.yaml, grouped by the objectives they
fit (see TAGS). An objective gets, by FAMILY_WEIGHTS, a line for what it is, a line
about one of the people there ("One of their drivers puts ketchup on steak."), or a
line that fits anything. No two objectives in one list get the same line while there
are others left, and an objective keeps its line for the whole turn.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

import yaml

from game.data.units import UnitClass
from game.highcommand.importance import ground_objects
from game.highcommand.wording import alive, unit_class
from game.theater import ControlPoint
from game.theater.theatergroundobject import (
    AirDefenceKind,
    GenericCarrierGroundObject,
    IadsGroundObject,
    MotorpoolGroundObject,
    NavalGroundObject,
    VehicleGroupGroundObject,
)

if TYPE_CHECKING:
    from game.highcommand.objectives import Objective

JOKES = Path("resources/highcommand/comical.yaml")

ANY = "any"

#: Every tag a line can be for. What each one fits is worked out by tags_of().
TAGS = frozenset(
    {
        ANY,
        "air-defence",
        "radar",
        "antenna",
        "command",
        "power",
        "factory",
        "business",
        "storage",
        "ammo",
        "fuel",
        "oil",
        "ship",
        "runway",
        "vehicles",
        "armour",
        "troops",
    }
)

#: The tags of a building, by its category.
CATEGORY_TAGS = {
    "power": {"power", "business"},
    "comms": {"antenna"},
    "commandcenter": {"command"},
    "factory": {"factory", "business"},
    "ammo": {"ammo", "storage"},
    "fuel": {"fuel", "storage", "business"},
    "ware": {"storage", "business"},
    "warehouse": {"storage", "business"},
    "oil": {"oil", "business"},
    "derrick": {"oil", "business"},
    "farp": {"runway", "troops"},
    "allycamp": {"troops"},
    "coastal": {"vehicles"},
    "missile": {"vehicles"},
}

RADAR_CLASSES = frozenset(
    {
        UnitClass.EARLY_WARNING_RADAR,
        UnitClass.SEARCH_RADAR,
        UnitClass.SEARCH_TRACK_RADAR,
        UnitClass.TRACK_RADAR,
    }
)

#: How often a line is about what the objective is, about one of the people there, or
#: one that fits anything, when there are all three to choose from.
FAMILY_WEIGHTS = {"specific": 5, "people": 2, "generic": 3}

#: How often someone at a place is one of its own people rather than anyone's.
OWN_PEOPLE = 0.7

#: What a line can name.
PLACEHOLDERS = frozenset({"name", "base"})


@dataclass(frozen=True)
class Tagged:
    """A line, or a person, and the objectives it fits."""

    text: str
    tags: frozenset[str]


@dataclass(frozen=True)
class Jokes:
    lines: tuple[Tagged, ...]
    #: Who did it, for the lines made of one of these and one of the deeds.
    people: tuple[Tagged, ...]
    deeds: tuple[str, ...]

    @staticmethod
    def parse(data: dict[str, Any]) -> Jokes:
        """The jokes in a file's contents. A tag nothing fits or a placeholder nothing
        fills is an error rather than a line nobody will ever see."""
        return Jokes(
            lines=tuple(_tagged(data.get("lines", {}))),
            people=tuple(_tagged(data.get("people", {}))),
            deeds=tuple(str(deed).strip() for deed in data.get("deeds", [])),
        )


@lru_cache(maxsize=1)
def jokes() -> Jokes:
    with JOKES.open(encoding="utf-8") as file:
        return Jokes.parse(yaml.safe_load(file))


def comical_lines(
    objectives: Sequence[Objective], seed: object, found: Optional[Jokes] = None
) -> dict[str, str]:
    """A line for each objective, by name. The same objectives and seed get the same
    lines."""
    pool = found if found is not None else jokes()
    used: set[str] = set()
    used_deeds: set[str] = set()
    lines: dict[str, str] = {}
    for objective in sorted(objectives, key=lambda o: o.name):
        rng = random.Random(f"{seed}:{objective.name}")
        line = _line(pool, tags_of(objective), rng, used, used_deeds)
        if line is not None:
            lines[objective.name] = line.format(
                name=objective.name, base=_base_name(objective)
            )
    return lines


def tags_of(objective: Objective) -> frozenset[str]:
    """What the objective is, in the tags lines are grouped by."""
    tags = {ANY}
    if isinstance(objective.targets[0], ControlPoint):
        return frozenset(tags | {"runway", "troops"})
    tgos = ground_objects(objective)
    units = alive(tgos)
    if any(unit.is_vehicle for unit in units):
        tags.add("vehicles")
    if any(unit.is_anti_air and unit.threat_range.meters > 0 for unit in units):
        tags.add("air-defence")
    if any(unit_class(unit) in RADAR_CLASSES for unit in units):
        tags.add("radar")
    for tgo in tgos:
        tags |= CATEGORY_TAGS.get(tgo.category, set())
        if isinstance(tgo, NavalGroundObject):
            tags.add("ship")
        if isinstance(tgo, GenericCarrierGroundObject):
            tags.add("runway")
        if isinstance(tgo, VehicleGroupGroundObject):
            tags |= {"armour", "troops", "vehicles"}
        if isinstance(tgo, MotorpoolGroundObject):
            tags |= {"storage", "vehicles"}
        if (
            isinstance(tgo, IadsGroundObject)
            and tgo.air_defence_kind is AirDefenceKind.JAMMER
        ):
            tags.add("antenna")
    return frozenset(tags)


def _line(
    pool: Jokes,
    tags: frozenset[str],
    rng: random.Random,
    used: set[str],
    used_deeds: set[str],
) -> Optional[str]:
    own = tags - {ANY}
    specific = [
        line.text for line in pool.lines if line.tags & own and line.text not in used
    ]
    generic = [
        line.text for line in pool.lines if ANY in line.tags and line.text not in used
    ]
    own_people = [person.text for person in pool.people if person.tags & own]
    anyone = [person.text for person in pool.people if ANY in person.tags]
    deeds = [deed for deed in pool.deeds if deed not in used_deeds]

    families: dict[str, list[str]] = {}
    if specific:
        families["specific"] = specific
    if deeds and (own_people or anyone):
        families["people"] = deeds
    if generic:
        families["generic"] = generic
    if not families:
        # Every line that fits has been given out: a repeat beats nothing.
        fitting = [line.text for line in pool.lines if line.tags & tags]
        return rng.choice(fitting) if fitting else None

    names = sorted(families)
    family = rng.choices(names, weights=[FAMILY_WEIGHTS[name] for name in names])[0]
    if family == "people":
        who = (
            own_people
            if own_people and (not anyone or rng.random() < OWN_PEOPLE)
            else anyone
        )
        deed = rng.choice(deeds)
        used_deeds.add(deed)
        return f"{rng.choice(who)} {deed}"
    text = rng.choice(families[family])
    used.add(text)
    return text


def _base_name(objective: Objective) -> str:
    target = objective.targets[0]
    if isinstance(target, ControlPoint):
        return target.name
    return ground_objects(objective)[0].control_point.name


def _tagged(groups: dict[str, Iterable[str]]) -> Iterable[Tagged]:
    for key, texts in groups.items():
        tags = frozenset(tag.strip() for tag in str(key).split(","))
        unknown = tags - TAGS
        if unknown:
            raise ValueError(f"Unknown tags in {JOKES}: {', '.join(sorted(unknown))}")
        if ANY in tags and len(tags) > 1:
            raise ValueError(f"{key!r} in {JOKES}: any already fits everything")
        for text in texts:
            text = str(text).strip()
            fields = {
                field for _, field, _, _ in string.Formatter().parse(text) if field
            }
            if fields - PLACEHOLDERS:
                raise ValueError(
                    f"{text!r} in {JOKES}: unknown {fields - PLACEHOLDERS}"
                )
            yield Tagged(text, tags)
