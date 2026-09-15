"""Pilot morale.

The value runs 0 to 100 and starts at 50. Events from the debriefing move it down (losing
an aircraft, squadron losses, a long spell without leave) or up (completed missions,
kills). Nothing here needs the mission to report anything the debriefing does not already
carry.

The constants below are defaults; each names the settings key that overrides it, as in
:mod:`game.squadrons.friendship`.
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

#: The floor is below zero so that Broken lasts more than one turn: at a floor of zero
#: a single turn of drift lifts a pilot out of the band.
MORALE_MIN = -30
MORALE_MAX = 100

#: Where a pilot starts, and the value the drift returns him to.
MORALE_START = 50


@dataclass(frozen=True)
class MoraleEvent:
    """One morale event and the amount it moves a pilot.

    ``default`` is signed: negative for events that lower morale. The settings key holds
    the same sign.

    """

    key: str
    default: int
    reason: str

    #: Overrides the campaign's figure for this copy of the event, for callers that
    #: have already scaled it (leave taken in company, for example).
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
        """The same event scaled for one pilot.

        Rounded to a whole number, so a factor that rounds to zero leaves the event as
        the campaign defined it.

        """
        return replace(self, override=round(self.amount(settings) * factor))


# --- what wears him down ----------------------------------------------------

#: The pilot survived the loss of his aircraft. The plugin does not report ejections,
#: so this covers both.
LOST_AIRCRAFT = MoraleEvent("morale_lost_aircraft", -15, "lost his aircraft")

#: He flew a strike, a CAS or a SEAD and destroyed nothing at all.
ACHIEVED_NOTHING = MoraleEvent("morale_achieved_nothing", -10, "came home empty")

#: Per pilot of his own squadron killed, scaled by
#: :func:`game.squadrons.friendship.grief_times`.
SQUADRON_DEATH = MoraleEvent("morale_squadron_death", -20, "lost a squadron mate")

#: Applied on top of the above to the pilots in the same flight.
FLIGHT_DEATH = MoraleEvent("morale_flight_death", -10, "watched his wingman go down")

#: Per turn a squadron mate will spend in hospital, up to a cap.
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

#: A squadron mate returned from hospital. The mirror of the wound event, and smaller
#: than it, so that a wound still costs something overall.
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
    """How many times a wound of this length counts against the squadron.

    Once per turn in hospital, so four turns out costs four times as much.

    """
    return max(1, turns)


#: Every value each of these has had as a default, oldest first. Read only by the
#: migrator, which moves a campaign onto the current figure where the save still holds
#: one of the old defaults, leaving a value the player set himself alone.
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


#: How far a pilot drifts back towards the middle in a turn with no events. Sized so
#: that one bad turn does not decide a campaign: 50 to 20 recovers in three turns.
DRIFT_PER_TURN = 5


def drift_per_turn(settings: Any = None) -> int:
    if settings is None:
        return DRIFT_PER_TURN
    return int(getattr(settings, "morale_drift_per_turn", DRIFT_PER_TURN))


def drift(morale: int, settings: Any = None) -> int:
    """One step back towards the middle from either side, never past it.

    Applied once a turn before any event. It applies at the bottom of the scale as
    well, though a hard turn can undo it immediately.

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
    """The fraction of a negative event a pilot of this rank actually takes.

    Negative events only; gains are unaffected.

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
    """Apply one event to a pilot, reduced if it is negative.

    Reduced twice: by rank and by ``relief`` (hardening). The two multiply, and neither
    applies to gains. A negative event always costs at least one point.

    """
    amount = event.amount(settings)
    if amount < 0:
        softened = resistance(skill) * max(0.0, 1.0 - relief)
        amount = -max(1, round(-amount * softened))
    return clamp(morale + amount)


#: The tasks that can be failed. A CAP that met no enemy has not failed; a strike that
#: destroyed nothing has.
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

#: The band that flies one rung above the pilot's rank, and the band (with everything
#: below it) that flies one rung under. Not settings: they are the bands themselves.
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
    """One step up or down the skill ladder, clamped to its ends.

    Shared by the two things that move a pilot off his own rank: morale and the
    friendship of the formation he is in.

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
    """One band of the morale scale.

    ``floor`` is the inclusive bottom of the band. ``severity`` is how the UI should
    treat it: 0 nothing, 1 worth watching, 2 needs attention. ``key`` is the setting that
    moves the floor, and is None for the bottom band.

    """

    floor: int
    name: str
    severity: int
    key: Optional[str] = None


#: The number is shown in the pilot dialog, the ledger and the API; everywhere else
#: shows the band name, as a rank stands in for a skill level.
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


#: One face per band, for lists with no room for the word. Keyed by band name, so
#: moving a band's floor cannot put the wrong face on it.
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


#: Multiplier on what a sortie pays. Each band's figure is its inclusive lower bound,
#: so a pilot exactly on a boundary gets the higher band.
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
    """Skill bonus for flying with a more experienced pilot.

    Only the best pilot in the formation counts, and only for those below him; he gains
    nothing himself. The bonus is the difference in rungs.

    """
    try:
        mine = SKILL_LADDER.index(own)
        theirs = SKILL_LADDER.index(best_in_flight)
    except ValueError:
        return 0.0
    return max(0, theirs - mine) * LEARNING_PER_RUNG


# --- how the flight behaves -------------------------------------------------

#: Below the first the flight evades threats; below the second it aborts on a serious
#: one. Both are DCS group options, so they follow the flight lead.
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


#: Default and maximum turns of leave the dialog offers.
DEFAULT_LEAVE_TURNS = 2
MAX_LEAVE_TURNS = 6

#: Turns of leave requested, by morale band. The player may grant fewer.
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


#: How many recent turns count towards a leave request, and how many are kept.
RECENT_SORTIE_WINDOW = 5
SORTIE_HISTORY_LIMIT = 20


def workload_factor(flown: int, window: int = RECENT_SORTIE_WINDOW) -> float:
    """Multiplier on the chance of asking for leave, from how much he has flown lately."""
    if window <= 0:
        return 1.0
    return 0.6 + 0.8 * (max(0, min(window, flown)) / window)


def leave_request_chance(
    morale: int,
    base_percent: int,
    flown_recently: int = 0,
    window: int = RECENT_SORTIE_WINDOW,
) -> float:
    """Chance this pilot asks for leave this turn, 0 to 1.

    Decided by his morale and by how hard he has been worked. Never zero.

    """
    factor = max(0.25, min(2.0, 2.0 - morale / (MORALE_START * 1.0)))
    factor *= workload_factor(flown_recently, window)
    return max(0.0, min(1.0, base_percent / 100.0 * factor))


def worth_reporting(before: int, after: int, settings: Any = None) -> bool:
    """Whether this change is worth a line in the debriefing.

    Only when it moved the pilot from one band to another; the figures themselves are in
    the ledger. Without this the section filled with rows reading "Normal -> Normal".

    """
    return morale_state(before, settings).name != morale_state(after, settings).name


#: Chance per turn at the bottom of the scale that the pilot deserts, one entry per
#: rung from cadet to squadron leader.
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


#: How many log entries a pilot keeps: enough for the dialog, few enough for the save.
MORALE_HISTORY_LIMIT = 60

#: At or below this he will not fly at all.
REFUSES_TO_FLY_AT = 0
