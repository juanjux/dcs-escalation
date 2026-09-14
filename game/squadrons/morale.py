"""How a pilot is holding up, and what that is worth.

Morale runs 0 to 100 and starts at 50. It moves with what the campaign does to a man --
losing his aircraft, watching his squadron die, going a long time without leave -- and it
moves back with what goes well. Everything it reads is already in the debriefing; nothing
here needs the mission to report anything new.

The numbers below are the defaults. Each one has a settings key beside it so a campaign
can be tuned without editing code, exactly as :mod:`game.squadrons.experience` does for
the survival odds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Optional

from dcs.task import OptReactOnThreat
from dcs.unit import Skill

from game.dcs.skills import SKILL_LADDER

if TYPE_CHECKING:
    from game.settings import Settings

#: Rock bottom is below zero so that being Broken lasts. At a floor of zero one quiet
#: turn of drift lifted a man straight back out of the band, whatever had put him
#: there, and Broken could not describe more than a single turn.
MORALE_MIN = -30
MORALE_MAX = 100

#: Where a pilot starts, and where he drifts back to. A campaign that has done nothing
#: to a man yet should not have an opinion about him.
MORALE_START = 50


@dataclass(frozen=True)
class MoraleEvent:
    """One thing that moves a pilot, and how far.

    ``default`` is signed: negative for the things that wear him down. The settings key
    holds the same sign, so a campaign that wants a harder war only has to make the
    numbers bigger.
    """

    key: str
    default: int
    reason: str

    #: What this copy of the event is worth, when it is worth something other than the
    #: campaign's figure -- leave taken in company, say. It wins over the settings key,
    #: because it was worked out from that figure to begin with.
    override: Optional[int] = None

    def amount(self, settings: Optional["Settings"] = None) -> int:
        if self.override is not None:
            return self.override
        if settings is None:
            return self.default
        return int(getattr(settings, self.key, self.default))

    def scaled_by(
        self, factor: float, settings: Optional["Settings"] = None
    ) -> "MoraleEvent":
        """The same event, worth more to one man than to the next.

        Whole numbers, because morale is one: a factor that rounds to nothing leaves
        the event exactly as the campaign wrote it.
        """
        return replace(self, override=round(self.amount(settings) * factor))


# --- what wears him down ----------------------------------------------------

#: He came home without the aircraft. The plugin does not report ejections, but a pilot
#: who lost his aircraft and lived is the same man in the same parachute.
LOST_AIRCRAFT = MoraleEvent("morale_lost_aircraft", -15, "lost his aircraft")

#: He flew a strike, a CAS or a SEAD and destroyed nothing at all.
ACHIEVED_NOTHING = MoraleEvent("morale_achieved_nothing", -10, "came home empty")

#: Per pilot of his own squadron killed, weighted by what he thought of the man:
#: see :func:`game.squadrons.friendship.grief_times`.
SQUADRON_DEATH = MoraleEvent("morale_squadron_death", -20, "lost a squadron mate")

#: On top of the above, for the men who were in the same flight and watched it happen.
#: The squadron hears about it; the flight saw it.
FLIGHT_DEATH = MoraleEvent("morale_flight_death", -10, "watched his wingman go down")

#: Per turn a squadron mate will be in hospital, up to a cap. A wound is not a death,
#: but a man carried out for four turns is felt more than one back next week.
SQUADRON_WOUND = MoraleEvent("morale_squadron_wound", -3, "a squadron mate was wounded")

#: And again, extra, for the flight he was in.
FLIGHT_WOUND = MoraleEvent("morale_flight_wound", -1, "a man in his flight was hit")

#: However long the medics keep him, a wound is never felt as hard as a grave.

#: A base of his coalition changed hands.
BASE_LOST = MoraleEvent("morale_base_lost", -2, "a base was lost")

#: Turns a pilot will go without leave before it starts to tell on him.
TURNS_BEFORE_LEAVE_IS_MISSED = 5

#: Per turn beyond the fifth without leave, and it keeps growing.
NO_LEAVE = MoraleEvent("morale_no_leave", -2, "no leave in a long time")

#: He asked for leave and was told no.
LEAVE_REFUSED = MoraleEvent("morale_leave_refused", -5, "leave refused")

#: He was on leave and was called back before it was up. Worse than never getting it:
#: he had it in his hand.
LEAVE_CANCELLED = MoraleEvent("morale_leave_cancelled", -8, "leave cut short")

# --- what builds him up -----------------------------------------------------

#: Per enemy aircraft shot down.
AIR_KILL = MoraleEvent("morale_air_kill", 10, "shot one down")

#: Per thing destroyed that was not what his package was sent for.
UNPLANNED_KILL = MoraleEvent("morale_unplanned_kill", 3, "took a target of opportunity")

#: He flew the sortie and brought the aircraft home.
MISSION_COMPLETE = MoraleEvent("morale_mission_complete", 10, "flew the mission")

#: His own promotion.
PROMOTED = MoraleEvent("morale_promoted", 20, "promoted")

#: Per turn of leave served.
ON_LEAVE = MoraleEvent("morale_on_leave", 15, "on leave")

#: He walked out of the hospital. The mirror of the wound: losing him for a few turns
#: cost the squadron, and having him back pays some of it in. Never all of it -- a wound
#: has to be worth avoiding.
SQUADRON_RECOVERED = MoraleEvent(
    "morale_squadron_recovered", 4, "a man came back from the hospital"
)

#: Every event, for the settings page and for tests that check nothing was forgotten.
MORALE_EVENTS: tuple[MoraleEvent, ...] = (
    LOST_AIRCRAFT,
    ACHIEVED_NOTHING,
    SQUADRON_DEATH,
    FLIGHT_DEATH,
    SQUADRON_WOUND,
    FLIGHT_WOUND,
    BASE_LOST,
    NO_LEAVE,
    LEAVE_REFUSED,
    LEAVE_CANCELLED,
    AIR_KILL,
    UNPLANNED_KILL,
    MISSION_COMPLETE,
    PROMOTED,
    ON_LEAVE,
    SQUADRON_RECOVERED,
)


def wound_is_felt_for(turns: int) -> int:
    """How many times a wound of this length is counted against a squadron.

    Every turn the medics keep him, not the first three: four turns out is four
    times the cost, which is the point of a long wound.
    """
    return max(1, turns)


#: Every value each of these has had as a default, oldest first. Only the migrator reads
#: it, to move a campaign already in progress onto the current figures -- and only where
#: the save still holds one of them, so a number the player set himself is left alone.
#: A campaign can have sat out more than one re-weighing, which is why it is a list.
PREVIOUS_DEFAULTS: dict[str, tuple[int, ...]] = {
    "morale_lost_aircraft": (-15,),
    "morale_achieved_nothing": (-10, -7),
    "morale_squadron_death": (-8, -20),
    "morale_flight_death": (-6, -10),
    "morale_squadron_wound": (-2, -3),
    "morale_flight_wound": (-2,),
    "morale_base_lost": (-6, -2),
    "morale_no_leave": (-2, -4),
    "morale_leave_refused": (-6, -5),
    "morale_leave_cancelled": (-10, -8, -7),
    "morale_air_kill": (10,),
    "morale_unplanned_kill": (3,),
    "morale_mission_complete": (4,),
    "morale_promoted": (12, 20),
    "morale_on_leave": (8,),
}


def clamp(morale: int) -> int:
    return max(MORALE_MIN, min(MORALE_MAX, morale))


#: How far a pilot settles back towards the middle in a quiet turn, when the campaign
#: has not said otherwise. Big enough that one very good or one very bad turn does not
#: decide the rest of his campaign: a man knocked from 50 to 20 is back to Normal in
#: three quiet turns, not thirty.
DRIFT_PER_TURN = 5


def drift_per_turn(settings: Any = None) -> int:
    if settings is None:
        return DRIFT_PER_TURN
    return int(getattr(settings, "morale_drift_per_turn", DRIFT_PER_TURN))


def drift(morale: int, settings: Any = None) -> int:
    """A step back towards the middle, from either side, never past it.

    Applied once a turn before anything else. Rock bottom is not exempt -- he climbs
    out of it like anyone else -- but the events of a hard turn can put him straight
    back, and every turn he is there is another roll of :func:`desertion_chance`.
    """
    step = drift_per_turn(settings)
    if morale > MORALE_START:
        return -min(step, morale - MORALE_START)
    if morale < MORALE_START:
        return min(step, MORALE_START - morale)
    return 0


#: The rungs of the ladder, and so the number of stars a pilot can wear.
RANK_LEVELS = len(SKILL_LADDER)


def rank_level(skill: Skill) -> int:
    """Which rung he stands on, 1 to 5, for the stars on his row."""
    try:
        return SKILL_LADDER.index(skill) + 1
    except ValueError:
        return 1


def resistance(skill: Skill) -> float:
    """How much of a knock a pilot of this rank actually takes.

    Rank is armour: a squadron leader has seen it before. It only softens the falls --
    nobody is too senior to be pleased about a promotion.
    """
    try:
        rung = SKILL_LADDER.index(skill)
    except ValueError:
        rung = 0
    return 1.0 - 0.15 * rung


def apply(
    morale: int,
    event: MoraleEvent,
    skill: Skill,
    settings: Any = None,
    relief: float = 0.0,
) -> int:
    """Move a pilot by one event, softened if it is a knock.

    Twice over: by his rank, which is armour he was given, and by ``relief`` -- what he
    has already been through, which is armour he earned. The two multiply, because they
    are separate reasons the same news lands lighter, and neither applies to good news.

    A knock never costs nothing, however hard the man: the floor of one point is the
    rule rather than a rounding guard.
    """
    amount = event.amount(settings)
    if amount < 0:
        softened = resistance(skill) * max(0.0, 1.0 - relief)
        amount = -max(1, round(-amount * softened))
    return clamp(morale + amount)


#: The tasks a pilot can come home from having failed. A CAP that saw nobody has not
#: failed at anything; a strike that dropped on nothing has.
STRIKE_TASKS: frozenset[str] = frozenset(
    {
        "CAS",
        "BAI",
        "STRIKE",
        "DEAD",
        "SEAD",
        "SEAD_SWEEP",
        "OCA_RUNWAY",
        "OCA_AIRCRAFT",
        "ANTISHIP",
        "ARMED_RECON",
    }
)


# --- what it does -----------------------------------------------------------

#: The state a pilot flies a rung above his rank in, and the one he drops a rung
#: below it at -- and everything worse than it, so Broken is not steadier than
#: Shattered. There is nothing to set here: they are the bands themselves.
SKILL_SHIFT_UP_STATE = "Triumphant"
SKILL_SHIFT_DOWN_STATE = "Shattered"


def skill_shift(morale: int, settings: Any = None) -> int:
    """-1, 0 or +1 rungs, from how he is holding up.

    A pilot flying Triumphant is a rung above the rank he holds; one who has fallen
    to Shattered -- or below it -- is a rung below it.
    """
    if morale >= state_named(SKILL_SHIFT_UP_STATE, settings).floor:
        return 1
    if morale < band_ceiling(SKILL_SHIFT_DOWN_STATE, settings):
        return -1
    return 0


def band_ceiling(name: str, settings: Any = None) -> int:
    """One past the top of this band: the floor of the one sitting on it."""
    states = morale_states(settings)
    for above, state in zip(states, states[1:]):
        if state.name == name:
            return above.floor
    return MORALE_MAX + 1


def bumped_skill(skill: Skill, rungs: int) -> Skill:
    """A rung up or down the ladder, clamped to its ends.

    Shared by the two things that move a pilot off his rank: how he is holding up, and
    whether the formation around him is one he gets on with.
    """
    if not rungs:
        return skill
    try:
        rung = SKILL_LADDER.index(skill)
    except ValueError:
        return skill
    return SKILL_LADDER[max(0, min(len(SKILL_LADDER) - 1, rung + rungs))]


def shifted_skill(skill: Skill, morale: int, settings: Any = None) -> Skill:
    """The rung he will actually fly at, clamped to the ladder."""
    return bumped_skill(skill, skill_shift(morale, settings))


@dataclass(frozen=True)
class MoraleState:
    """What a squadron commander would be told, rather than a number.

    ``floor`` is the bottom of the band, taken inclusively. ``severity`` is what the
    player should read into it: 0 nothing, 1 worth an eye, 2 do something about it now.
    ``key`` is the setting that moves the floor; Broken has none because it is the
    bottom of the scale.
    """

    floor: int
    name: str
    severity: int
    key: Optional[str] = None


#: The figure itself is for the pilot dialog, the ledger and the API. Everywhere the
#: player looks he gets the name, exactly as a rank stands in for a skill level.
MORALE_STATES: tuple[MoraleState, ...] = (
    MoraleState(85, "Triumphant", 0, "morale_state_triumphant"),
    MoraleState(60, "Confident", 0, "morale_state_confident"),
    MoraleState(40, "Normal", 0, "morale_state_normal"),
    MoraleState(15, "Shaken", 1, "morale_state_shaken"),
    MoraleState(1, "Shattered", 2, "morale_state_shattered"),
    MoraleState(MORALE_MIN, "Broken", 2),
)


def morale_states(settings: Any = None) -> tuple[MoraleState, ...]:
    """The bands as this campaign has them set, top down."""
    if settings is None:
        return MORALE_STATES
    return tuple(
        (
            state
            if state.key is None
            else replace(state, floor=int(getattr(settings, state.key, state.floor)))
        )
        for state in MORALE_STATES
    )


def morale_state(morale: int, settings: Any = None) -> MoraleState:
    for state in morale_states(settings):
        if morale >= state.floor:
            return state
    return MORALE_STATES[-1]


#: One face per band, for the lists with no room for the word -- the pilot selector
#: above all, where every name looks alike and the man's state is the thing you are
#: choosing on. Keyed by state NAME, so a campaign that moves a band's floor cannot
#: end up with the wrong face on it.
STATE_EMOJI: dict[str, str] = {
    "Triumphant": "😄",
    "Confident": "🙂",
    "Normal": "😐",
    "Shaken": "😟",
    "Shattered": "😢",
    "Broken": "😭",
}


def emoji_for(morale: int, settings: Any = None) -> str:
    """The band's face, or nothing for a band nobody has given one."""
    return STATE_EMOJI.get(morale_state(morale, settings).name, "")


def state_named(name: str, settings: Any = None) -> MoraleState:
    for state in morale_states(settings):
        if state.name == name:
            return state
    raise ValueError(f"no morale state named {name}")


#: Multiplier on everything a sortie pays. A band's number is its lower bound, taken
#: inclusively, so a pilot sitting exactly on a boundary gets the better of the two.
XP_MULTIPLIER_BANDS: tuple[tuple[int, float], ...] = (
    (81, 1.5),  # above 80
    (60, 1.2),
    (40, 1.0),
    (10, 0.8),
    (MORALE_MIN, 0.5),
)


def xp_multiplier(morale: int) -> float:
    """What a sortie is worth to a man in this state."""
    for floor, multiplier in XP_MULTIPLIER_BANDS:
        if morale >= floor:
            return multiplier
    return 1.0


#: What each rung of difference to the best pilot in the flight is worth to the others.
LEARNING_PER_RUNG = 0.1


def learning_bonus(own: Skill, best_in_flight: Skill) -> float:
    """Flying with somebody better than you is worth something.

    Only the best man in the formation counts, and only for the ones below him: he gets
    nothing out of it himself. A cadet on an Excellent's wing is four rungs down, so he
    learns four rungs' worth.
    """
    try:
        mine = SKILL_LADDER.index(own)
        theirs = SKILL_LADDER.index(best_in_flight)
    except ValueError:
        return 0.0
    return max(0, theirs - mine) * LEARNING_PER_RUNG


# --- how the flight behaves -------------------------------------------------

#: Below this the flight routes around what frightens it; below the second it turns for
#: home when the threat is serious. These are group options, so they follow the lead.
SHAKEN_BELOW = 20
BROKEN_BELOW = 10


def threat_reaction(morale: int) -> OptReactOnThreat.Values:
    """What the lead will let his flight do about a threat."""
    if morale < BROKEN_BELOW:
        return OptReactOnThreat.Values.AllowAbortMission
    if morale < SHAKEN_BELOW:
        return OptReactOnThreat.Values.ByPassAndEscape
    return OptReactOnThreat.Values.EvadeFire


def rtb_on_bingo(morale: int) -> bool:
    """The shaken flight goes home at bingo; the confident one presses on."""
    return morale < SHAKEN_BELOW


# --- the rest ---------------------------------------------------------------


#: A wound keeps a hollow man out longer and a cheerful one less.
def recovery_turns(turns: int, morale: int, settings: Any = None) -> int:
    if morale < SHAKEN_BELOW:
        return turns + 1
    if morale >= state_named(SKILL_SHIFT_UP_STATE, settings).floor:
        return max(1, turns - 1)
    return turns


#: How much morale moves the survival roll, as a fraction added to the rank's chance.
def survival_modifier(morale: int) -> float:
    """The steady man gets out of the aircraft; the hollow one does not."""
    return (morale - MORALE_START) / 500.0  # +/- 10 points at the extremes


#: The turns of leave the dialog offers when a pilot has not named a number, and the
#: most the player can ever grant at once.
DEFAULT_LEAVE_TURNS = 2
MAX_LEAVE_TURNS = 6

#: How long a man asks for, by how he is holding up. Nobody asks for leave in the
#: abstract: he asks for a morning, a day, a week. The player can then grant less.
LEAVE_ASKED_FOR: tuple[tuple[int, int, int], ...] = (
    (40, 1, 2),  # Normal and better: a couple of days
    (15, 2, 3),  # Shaken
    (MORALE_MIN, 3, 4),  # Shattered or Broken: he wants out for a while
)


def requested_leave_turns(morale: int, roll: Optional[float] = None) -> int:
    """The number of turns this pilot asks for."""
    for floor, low, high in LEAVE_ASKED_FOR:
        if morale >= floor:
            span = high - low
            if roll is None:
                roll = random.random()
            return min(MAX_LEAVE_TURNS, low + int(roll * (span + 1)))
    return DEFAULT_LEAVE_TURNS


#: The window that counts as "lately" when deciding whether a man has had enough, and
#: how many turns of his flying is worth keeping to work it out.
RECENT_SORTIE_WINDOW = 5
SORTIE_HISTORY_LIMIT = 20


def workload_factor(flown: int, window: int = RECENT_SORTIE_WINDOW) -> float:
    """How hard he has been worked lately, as a multiplier on wanting a rest.

    A man who has flown every turn of the last five asks far more readily than one who
    has sat on the ground throughout -- and the one who flew twice sits between them.
    """
    if window <= 0:
        return 1.0
    return 0.6 + 0.8 * (max(0, min(window, flown)) / window)


def leave_request_chance(
    morale: int,
    base_percent: int,
    flown_recently: int = 0,
    window: int = RECENT_SORTIE_WINDOW,
) -> float:
    """How likely this pilot is to ask for leave this turn, 0 to 1.

    Two things decide it: how he is holding up, and how hard he has been worked. Never
    zero -- a contented, idle man still wants a week off now and then, he just does not
    need one.
    """
    factor = max(0.25, min(2.0, 2.0 - morale / (MORALE_START * 1.0)))
    factor *= workload_factor(flown_recently, window)
    return max(0.0, min(1.0, base_percent / 100.0 * factor))


def worth_reporting(before: int, after: int, settings: Any = None) -> bool:
    """Whether this movement earns a line in the debriefing.

    When it moved the pilot from one state to another, and only then. The row says
    what he was and what he is, so a movement that leaves him where he was has
    nothing to show -- and flying the mission moves everyone who came home, which
    used to fill the section with rows reading "Normal -> Normal". The figures
    themselves are in the ledger.
    """
    return morale_state(before, settings).name != morale_state(after, settings).name


#: The chance, per turn spent at rock bottom, that a pilot simply stops coming --
#: one entry per rung of the ladder, from cadet to squadron leader. Rank is what keeps
#: a man in his seat when nothing else does, so the veteran is the last to go.
DESERTION_CHANCE_BY_RUNG: tuple[float, ...] = (0.09, 0.07, 0.05, 0.03, 0.01)


def desertion_chance(skill: Skill) -> float:
    """How likely this pilot is to walk away this turn, 0 to 1."""
    try:
        rung = SKILL_LADDER.index(skill)
    except ValueError:
        rung = 0
    return DESERTION_CHANCE_BY_RUNG[min(rung, len(DESERTION_CHANCE_BY_RUNG) - 1)]


@dataclass(frozen=True)
class MoraleLogEntry:
    """One thing that moved a pilot, kept so it can be shown back to the player.

    The pilot dialog is where this is read; nothing in the campaign depends on it.
    """

    turn: int
    amount: int
    reason: str
    morale_after: int


#: How many entries a pilot carries. Enough for the dialog to show a campaign's worth
#: of a man's ups and downs without the roll of them bloating every save.
MORALE_HISTORY_LIMIT = 60

#: At or below this he will not fly at all.
REFUSES_TO_FLY_AT = 0
