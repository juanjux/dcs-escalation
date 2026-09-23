"""What a sortie is worth, and what it costs to be promoted.

Experience is awarded from the debriefing rather than from a counter, so a pilot is paid
for what he did: who he shot down, what he destroyed, and whether he brought the aircraft
home. The rank that buys is defined in :mod:`game.dcs.skills`.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields
from typing import Any, TYPE_CHECKING, Optional

from dcs.unit import Skill

from game.config import REWARDS
from game.dcs.skills import SKILL_LADDER

if TYPE_CHECKING:
    from game.settings import Settings

#: An enemy aircraft.
XP_AIR_KILL = 500

#: Flying the sortie and coming back from it. Losing the aircraft forfeits this.
XP_MISSION_COMPLETE = 500

#: A vehicle: a tank, a SAM launcher, a convoy truck, a front line gun.
XP_GROUND_KILL = 200

#: A hull. Flat, because 91 of the 110 ships shipped with Escalation are priced at zero
#: -- a Ticonderoga is worth nothing to `unit_type.price`, so value would score it as
#: nothing. Pricing the fleet properly is a separate job.
XP_SHIP_KILL = 300

#: Buildings are paid by what they are worth. REWARDS is income per turn per element, in
#: millions, so an oil platform at 10 pays 500 and a warehouse at 2 pays 100.
XP_PER_BUILDING_MILLION = 50

#: Something destroyed that has no entry anywhere: still worth flying out for.
XP_UNKNOWN_KILL = 100

#: Coming back in a stretcher rather than a box. Less than a sortie flown, because
#: nobody should be better off for having been shot down -- a pilot who loses the
#: aircraft forfeits XP_MISSION_COMPLETE, so a wound is a consolation, not a windfall.
XP_WOUNDED = 200

#: How long a wound keeps a pilot off the roster, in turns, inclusive.
WOUNDED_TURNS = (1, 4)

#: What hitting something is worth, as a share of destroying it. DCS reports who hit
#: what, so unlike a shared kill this is a real assist rather than a guess: a pilot who
#: leaves a destroyer burning and does not finish it off is paid a quarter of the hull.
#: Once per target, however many rounds he put into it, and never on top of the kill.
XP_DAMAGE_SHARE = 0.25


def building_xp(category: Optional[str]) -> int:
    """What one element of a ``category`` objective is worth."""
    if category is None:
        return XP_UNKNOWN_KILL
    reward = REWARDS.get(category)
    if reward is None:
        return XP_UNKNOWN_KILL
    return max(1, round(reward * XP_PER_BUILDING_MILLION))


#: How likely a pilot is to walk away from a combat loss, by the rung he flies at. A cadet
#: usually does not; a squadron leader usually does.
SURVIVAL_BY_SKILL: dict[Skill, float] = {
    Skill.Average: 0.35,
    Skill.Good: 0.50,
    Skill.High: 0.65,
    Skill.Excellent: 0.80,
}

#: Cadet is injected into pydcs' enum at import time, so it cannot be a literal above.
SURVIVAL_CADET = 0.20


#: The player's own odds, one per rung, in the same order as SKILL_LADDER. The defaults
#: match the table above; the settings page lets them be tuned.
SURVIVAL_SETTINGS: tuple[str, ...] = (
    "live_pilots_survival_cadet",
    "live_pilots_survival_average",
    "live_pilots_survival_good",
    "live_pilots_survival_high",
    "live_pilots_survival_excellent",
)


def survival_chance(skill: Skill, settings: Optional["Settings"] = None) -> float:
    """How likely a pilot of this rank is to walk away from losing his aircraft.

    Without settings this is the default ladder, which is what the tests measure and
    what the table documents.
    """
    if settings is None:
        return SURVIVAL_BY_SKILL.get(skill, SURVIVAL_CADET)
    try:
        rung = SKILL_LADDER.index(skill)
    except ValueError:
        rung = 0
    return getattr(settings, SURVIVAL_SETTINGS[rung]) / 100


class SaveCompatible:
    """A record that is pickled into a save and may outlive its own field list.

    Pickle restores ``__dict__`` verbatim, so a field added after a save was written is
    simply absent from the object it rebuilds and the first read of it raises
    AttributeError -- which is what a debriefing from an older save did the day it
    gained its experience awards. Filling the dataclass defaults on the way in means a
    new field only has to have a default, which every field in this module does.
    """

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        for member in fields(self):  # type: ignore[arg-type]
            if member.name in state:
                continue
            if member.default_factory is not MISSING:
                setattr(self, member.name, member.default_factory())
            elif member.default is not MISSING:
                setattr(self, member.name, member.default)


@dataclass
class PilotDeath(SaveCompatible):
    """A pilot who did not come back, and what is known about who did it."""

    pilot_name: str
    squadron: str
    aircraft: str
    #: His rank, abbreviated, as the debriefing addresses him, and the rung it stands
    #: on so the same five stars can be drawn.
    rank: str = ""
    level: int = 0
    #: Which side he flew for, so a campaign can choose not to be told about theirs.
    blue: bool = True
    #: Already-formatted attribution: a roster pilot, a human's name, an airframe type,
    #: "a crash", or a friendly-fire note. None when nothing at all is known.
    killed_by: Optional[str] = None
    friendly_fire: bool = False


def turns_phrase(turns: int) -> str:
    """``1 turn``/``3 turns``. Counted out in three places and wrong in all of them."""
    return f"{turns} turn" if turns == 1 else f"{turns} turns"


@dataclass
class PilotWound(SaveCompatible):
    """A pilot the medics reached in time, and for how long they keep him."""

    pilot_name: str
    squadron: str
    turns: int
    aircraft: str = ""
    rank: str = ""
    level: int = 0
    #: Who put him in the hospital, formatted the same way a death's is.
    killed_by: Optional[str] = None
    friendly_fire: bool = False
    blue: bool = True


@dataclass
class PilotPromotion(SaveCompatible):
    pilot_name: str
    squadron: str
    from_rank: str
    to_rank: str

    #: The full name of the new rank, for anything with room to spell it out.
    to_rank_full: str = ""

    #: The rungs either side of it, so a promotion can be drawn as the transition it is.
    from_level: int = 0
    to_level: int = 0

    blue: bool = True

    #: Whether this is a pilot the human flies himself, who is told about it.
    player: bool = False

    aircraft: str = ""


@dataclass
class MoraleShift(SaveCompatible):
    """A pilot the turn moved a long way, in either direction."""

    pilot_name: str
    squadron: str
    before: int
    after: int
    reasons: list[str]
    aircraft: str = ""
    rank: str = ""
    level: int = 0
    blue: bool = True
    #: What he was and what he is, named at the time. Recorded rather than worked out
    #: again later, because the campaign's own band thresholds are a setting and the
    #: debriefing is a record of the turn, not a view of the current rules.
    before_state: str = ""
    after_state: str = ""

    @property
    def reason(self) -> str:
        """The one line of it, for a column with room for a phrase and not a list.

        Repeats are counted rather than repeated: three dead squadron mates is one
        thing that happened three times, not three things.
        """
        tally: dict[str, int] = {}
        for reason in self.reasons:
            tally[reason] = tally.get(reason, 0) + 1
        parts = [
            reason if count == 1 else f"{reason} x{count}"
            for reason, count in tally.items()
        ]
        return ", ".join(parts)


#: The reason labels an award is broken into, in the order a debriefing reads them:
#: what he shot at first, then what the sortie itself was worth, then what the company
#: he kept made of it.
XP_AIR = "Air kills"
XP_GROUND = "Ground kills"
XP_SHIPS = "Ships"
XP_BUILDINGS = "Structures"
XP_DAMAGE = "Damage dealt"
XP_MISSION = "Mission complete"
XP_WOUND = "Wounded"
XP_MORALE = "Morale"
XP_LEARNING = "Flew with better pilots"
XP_COMPANY = "Flew with friends"
XP_HELD_BACK = "Held back"

#: The order the reasons are shown in, whatever order they were collected in.
XP_REASON_ORDER = (
    XP_AIR,
    XP_GROUND,
    XP_SHIPS,
    XP_BUILDINGS,
    XP_DAMAGE,
    XP_MISSION,
    XP_WOUND,
    XP_MORALE,
    XP_LEARNING,
    XP_COMPANY,
    XP_HELD_BACK,
)


@dataclass
class XpAward(SaveCompatible):
    """What one pilot was paid this mission, and for what.

    The reasons are the point: a number on its own says a pilot gained 1,400 and
    nothing about whether that was two MiGs or a long list of trucks, and the
    multipliers are invisible in a total. Held as a mapping so a reason can be added
    from wherever it is decided, and read back in a fixed order.
    """

    pilot_name: str
    squadron: str
    aircraft: str = ""
    rank: str = ""
    level: int = 0
    blue: bool = True
    #: What he held before the mission and what he holds now. The difference is what
    #: the reasons add up to, except where a promotion was held back.
    before: int = 0
    after: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def add(self, reason: str, xp: int) -> None:
        """Fold another award in. Zero is not a reason and is dropped."""
        if not xp:
            return
        self.reasons[reason] = self.reasons.get(reason, 0) + xp

    @property
    def gained(self) -> int:
        return self.after - self.before

    @property
    def ordered_reasons(self) -> list[tuple[str, int]]:
        """The reasons in reading order, the ones that moved nothing left out."""
        return [
            (reason, self.reasons[reason])
            for reason in XP_REASON_ORDER
            if self.reasons.get(reason)
        ]

    @property
    def summary(self) -> str:
        """The reasons on one line, for anything without room for a list."""
        return ", ".join(f"{reason} {xp:+,}" for reason, xp in self.ordered_reasons)


@dataclass
class PilotOutcomes(SaveCompatible):
    """What became of the aircrew this mission, for the debriefing to read.

    Built where the decisions are made -- promotions as experience is awarded, the other
    two as losses are committed -- and carried on the Debriefing, which the results
    processor always finishes with before the window is shown.
    """

    promotions: list[PilotPromotion] = field(default_factory=list)
    survivors: list[PilotDeath] = field(default_factory=list)
    wounded: list[PilotWound] = field(default_factory=list)
    deaths: list[PilotDeath] = field(default_factory=list)
    morale_shifts: list[MoraleShift] = field(default_factory=list)
    xp_awards: list[XpAward] = field(default_factory=list)

    #: ``id()`` of every pilot who lost his aircraft, however it ended for him. He did
    #: not complete the mission, so he is not paid for completing it.
    lost_aircraft: set[int] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not (
            self.promotions
            or self.survivors
            or self.wounded
            or self.deaths
            or self.morale_shifts
            or self.xp_awards
        )
