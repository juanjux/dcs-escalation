"""What a pilot thinks of the man next to him.

Friendship runs 0 to 10 and starts at 5: morale's shape on a shorter ruler. It is
**directional** -- what A feels about B is not what B feels about A -- which is not
decoration. The two effects that read it read opposite ends: a pilot flies better with
men *he* likes, and is pulled out of a wreck by men who like *him*.

It moves two ways. Slowly, every turn, with everyone at his base: the squadron he sees
daily warms faster than the squadron across the ramp. And in the air, where a shared
sortie is worth more than a month of drift -- which is deliberate, because the bands
that pay for anything are the ones the drift alone cannot reach.

The numbers below are defaults. Each carries the settings key that overrides it, exactly
as :mod:`game.squadrons.morale` does, so a campaign can be re-weighed without editing
code.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence
from uuid import UUID

from game.squadrons import hardening

if TYPE_CHECKING:
    from game.squadrons.airwing import AirWing
    from game.squadrons.pilot import Pilot
    from game.squadrons.squadron import Squadron
    from game.theater import ControlPoint

#: The ends of the ruler, and the middle a pair starts on. A campaign that has not put
#: two men in the same aircraft has no opinion about how they get on, which is what 5
#: means -- and it is what a pilot from a save written before friendship reads for
#: everybody.
FRIENDSHIP_MIN = 0.0
FRIENDSHIP_MAX = 10.0
FRIENDSHIP_START = 5.0


@dataclass(frozen=True)
class FriendshipBand:
    """One level of the ladder, and what a squadron commander would call it.

    ``floor`` is the bottom of the level, taken inclusively. ``colour`` is what the
    lists paint it; Neutral has none, because nothing is drawn for two pilots nobody
    needs to think about. ``key`` is the setting that moves the floor -- Bad blood has
    none, because it is the bottom of the scale.
    """

    floor: float
    name: str
    colour: Optional[str] = None
    key: Optional[str] = None


#: Highest first, so the first match wins.
#:
#: Neutral is symmetric about the five every pair starts on, and it has to be: drift
#: moves by a whole point, so one quiet turn leaves a pair on four or on six, and a
#: band that holds one of those and not the other paints half of an even walk as
#: going sour.
FRIENDSHIP_BANDS: tuple[FriendshipBand, ...] = (
    FriendshipBand(9.1, "Inseparable", "#8FC3F0", "friendship_band_inseparable"),
    FriendshipBand(7.1, "Close", "#86C39A", "friendship_band_close"),
    FriendshipBand(6.1, "Friendly", "#A9C99A", "friendship_band_friendly"),
    FriendshipBand(4.0, "Neutral", None, "friendship_band_neutral"),
    FriendshipBand(3.0, "Frosty", "#E0A86B", "friendship_band_frosty"),
    FriendshipBand(1.1, "Hostile", "#D97B4F", "friendship_band_hostile"),
    FriendshipBand(FRIENDSHIP_MIN, "Bad blood", "#D9645E"),
)


def bands(settings: Any = None) -> tuple[FriendshipBand, ...]:
    """The levels as this campaign has them set, highest first."""
    if settings is None:
        return FRIENDSHIP_BANDS
    return tuple(
        (
            level
            if level.key is None
            else replace(level, floor=float(getattr(settings, level.key, level.floor)))
        )
        for level in FRIENDSHIP_BANDS
    )


#: The top of the band a quiet turn can carry a pair into. Above this is earned in the
#: air: see :func:`drift_step`.
DRIFT_CEILING = 7.0


def clamp(value: float) -> float:
    return max(FRIENDSHIP_MIN, min(FRIENDSHIP_MAX, value))


def points(value: float) -> float:
    """The distance from Neutral, which is what every effect is priced in.

    0 to 10 becomes -5 to +5, so "per point of friendship" means the same thing
    wherever it is written down.
    """
    return value - FRIENDSHIP_START


def band(value: float, settings: Any = None) -> FriendshipBand:
    for candidate in bands(settings):
        if value >= candidate.floor:
            return candidate
    return FRIENDSHIP_BANDS[-1]


def band_name(value: float, settings: Any = None) -> str:
    return band(value, settings).name


def _floor_of(name: str, settings: Any = None) -> float:
    for candidate in bands(settings):
        if candidate.name == name:
            return candidate.floor
    raise KeyError(name)


def is_close(value: float, settings: Any = None) -> bool:
    """Close or better: a man he is glad to have around on a bad week."""
    return value >= _floor_of("Close", settings)


def is_hostile(value: float, settings: Any = None) -> bool:
    """Hostile or worse: below the bottom of Frosty, where it stops being coolness."""
    return value < _floor_of("Frosty", settings)


# --- reading --------------------------------------------------------------------


def feeling(pilot: Pilot, other: Pilot) -> float:
    """What ``pilot`` thinks of ``other``. Neutral until something has happened."""
    if pilot is other:
        return FRIENDSHIP_START
    return pilot.friendships.get(other.id, FRIENDSHIP_START)


def mean_towards(
    pilot: Pilot,
    others: Iterable[Pilot],
    leader: Optional[Pilot] = None,
    settings: Any = None,
) -> float:
    """What he thinks of them, averaged. Neutral when there is nobody.

    With a leader named, the spoke that touches him is worth
    :data:`LEADER_SPOKE_WEIGHT` of each of the others: a formation is the man in front
    and the men who follow him, and in a four-ship that puts half of what each wingman
    feels about the formation on the one man leading it. Asked about the leader
    himself, it is the plain mean -- from where he sits there is nobody in front.
    """
    weight = leader_spoke_weight(settings)
    total = 0.0
    divisor = 0.0
    for other in others:
        if other is pilot:
            continue
        share = weight if other is leader else 1.0
        total += feeling(pilot, other) * share
        divisor += share
    return total / divisor if divisor else FRIENDSHIP_START


def mean_from(
    pilot: Pilot,
    others: Iterable[Pilot],
    leader: Optional[Pilot] = None,
    settings: Any = None,
) -> float:
    """What they think of him, averaged. The half that decides who looks for him.

    Weighted the same way: the man running the formation counts for more than the
    wingman, which is as true of who organises a search as of anything else.
    """
    weight = leader_spoke_weight(settings)
    total = 0.0
    divisor = 0.0
    for other in others:
        if other is pilot:
            continue
        share = weight if other is leader else 1.0
        total += feeling(other, pilot) * share
        divisor += share
    return total / divisor if divisor else FRIENDSHIP_START


def group_affinity(pilot: Pilot, others: Iterable[Pilot]) -> float:
    """How well he and they would get on: both directions, averaged.

    What the pilot picker paints, because the question there is about the group rather
    than about one man's opinion of it.
    """
    group = [other for other in others if other is not pilot]
    if not group:
        return FRIENDSHIP_START
    return (mean_towards(pilot, group) + mean_from(pilot, group)) / 2


def synergy(
    pilots: Sequence[Pilot], leader: Optional[Pilot] = None, settings: Any = None
) -> float:
    """How well a whole formation gets on, as the men in it experience it.

    Each man's own weighted mean of the others -- the one in front counting double --
    and the formation's figure is the mean of those. Pricing it that way is what makes
    spreading senior pilots one to a flight worth more than stacking them in one: four
    flights with a leader their crews would follow beats one flight of veterans and
    three of strangers.
    """
    crew = [pilot for pilot in pilots if pilot is not None]
    if len(crew) < 2:
        return FRIENDSHIP_START
    values = [mean_towards(member, crew, leader, settings) for member in crew]
    return sum(values) / len(values)


# --- writing --------------------------------------------------------------------


def move(pilot: Pilot, other: Pilot, amount: float) -> float:
    """Move one direction of one pair. Returns how far it actually went.

    Only ``pilot``'s own opinion: the other half is somebody else's to move, and moving
    both from one place is how a shared sortie ends up paid twice.
    """
    if pilot is other or not amount:
        return 0.0
    before = feeling(pilot, other)
    after = clamp(before + amount)
    if after == FRIENDSHIP_START:
        # Back where it started is back to carrying nothing: a graph of every pair at
        # every base is a lot of dictionary for a campaign to drag around.
        pilot.friendships.pop(other.id, None)
    else:
        pilot.friendships[other.id] = after
    return after - before


def drift_step(same_squadron: bool, current: float, settings: Any = None) -> float:
    """One turn of ordinary acquaintance, in one direction.

    Warmer, cooler or neither, on the odds the campaign sets. A rise stops at the top of
    Friendly: the bands that pay for synergy and for being looked for are earned in the
    air, not by sharing a ramp for long enough. A fall has no such floor -- losing touch
    with somebody needs nothing but time.
    """
    up, down = drift_odds(same_squadron, settings)
    roll = random.random() * 100
    step = drift_step_size(settings)
    ceiling = drift_ceiling(settings)
    if roll < up:
        if current >= ceiling:
            return 0.0
        return min(step, ceiling - current)
    if roll < up + down:
        return -step
    return 0.0


# --- the numbers ----------------------------------------------------------------

#: Per turn, per direction, as percentages. The remainder is "no change", so moving
#: these two is all the tuning a campaign needs.
DRIFT_SAME_SQUADRON_UP = 35
DRIFT_SAME_SQUADRON_DOWN = 20
DRIFT_SAME_BASE_UP = 22
DRIFT_SAME_BASE_DOWN = 10

#: How far one turn of drift moves a pair. A tenth of the scale, so this is the
#: fastest-moving number in the feature.
DRIFT_STEP = 1.0

#: What one sortie in the same formation is worth, and what one in the same package but
#: a different formation is worth. Deliberately larger than the drift: time at a base
#: makes acquaintances, and the rest is earned where it is dangerous.
FLEW_TOGETHER = 2.0
SAME_PACKAGE = 1.0

#: The most a pair can gain in one turn however many sorties they share. Without it,
#: three flights a turn with the same four men reaches the ceiling in a fortnight and
#: friendship stops being slow.
MAX_GAIN_PER_TURN = 4.0

#: What everyone else thinks of a man who shot down one of his own. The flight sees it
#: happen; the victim's squadron hears about it. A man in both takes the larger, never
#: the sum.
FRIENDLY_FIRE_AIR_FLIGHT = -3.0
FRIENDLY_FIRE_AIR_SQUADRON = -6.0
FRIENDLY_FIRE_GROUND = -2.0

#: Everything from here to the grief cap is a **percentage**, which is the unit the
#: settings page shows and the one the rest of the campaign is written in. The getters
#: below divide by a hundred, so nothing outside this section has to remember which of
#: the two it is holding.

#: What the spoke that touches the leader is worth, against one for everybody else.
#: At two, in a four-ship, half of what a wingman makes of the formation is what he
#: makes of the man leading it. Not a percentage: a weight, so it lives outside the
#: block below.
LEADER_SPOKE_WEIGHT = 2.0

#: Added straight to the experience multiplier, so it is a fraction rather than a
#: percentage -- which is what the settings page shows, and what it means.
XP_PER_POINT = 0.05

#: The rest of this block is percentages.
SURVIVAL_PER_POINT = 3
SURVIVAL_CAP = 20
DESERTION_PER_POINT = 5
DESERTION_CAP = 50
LEAVE_TOGETHER_PER_POINT = 8
LEAVE_TOGETHER_CAP = 50
DRIFT_HELP_PER_FRIEND = 5
DRIFT_HELP_CAP = 30

#: Both of these are multipliers rather than percentages: what one point adds to how
#: many times a death is felt, and the most it can come to.
GRIEF_PER_POINT = 0.33
GRIEF_CAP = 4.0

#: The band a formation has to reach before it flies a rung above its rank.
SYNERGY_FLOOR = 7.1

#: How many entries a pilot carries. The graph does not stay sparse -- the drift pins
#: pairs away from Neutral within a few turns -- and the dead, the deserted and the
#: transferred would otherwise stay in everyone's dictionary for the rest of the
#: campaign.
FRIENDSHIP_LIMIT = 120


def _setting(settings: Any, key: str, default: Any) -> Any:
    return default if settings is None else getattr(settings, key, default)


def in_play(settings: Any) -> bool:
    """Whether any of this is switched on.

    Friendship rides on Live Pilots and can be refused on its own. Refused, nothing
    reads the graph and nothing writes to it, which is the only way to hand back the
    whole cost of it -- the turn-end pass included.
    """
    return bool(_setting(settings, "live_pilots_enabled", True)) and bool(
        _setting(settings, "friendship_enabled", True)
    )


def _percent(settings: Any, key: str, default: Any) -> float:
    """One of the percentages above, as the fraction every caller actually wants."""
    return float(_setting(settings, key, default)) / 100.0


def drift_ceiling(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_drift_ceiling", DRIFT_CEILING))


def leader_spoke_weight(settings: Any = None) -> float:
    return float(
        _setting(settings, "friendship_leader_spoke_weight", LEADER_SPOKE_WEIGHT)
    )


def drift_odds(same_squadron: bool, settings: Any = None) -> tuple[float, float]:
    if same_squadron:
        return (
            float(
                _setting(
                    settings, "friendship_drift_squadron_up", DRIFT_SAME_SQUADRON_UP
                )
            ),
            float(
                _setting(
                    settings, "friendship_drift_squadron_down", DRIFT_SAME_SQUADRON_DOWN
                )
            ),
        )
    return (
        float(_setting(settings, "friendship_drift_base_up", DRIFT_SAME_BASE_UP)),
        float(_setting(settings, "friendship_drift_base_down", DRIFT_SAME_BASE_DOWN)),
    )


def drift_step_size(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_drift_step", DRIFT_STEP))


def flew_together(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_flew_together", FLEW_TOGETHER))


def same_package(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_same_package", SAME_PACKAGE))


def max_gain_per_turn(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_max_gain_per_turn", MAX_GAIN_PER_TURN))


def friendly_fire_penalties(settings: Any = None) -> tuple[float, float, float]:
    """Flight, victim's squadron, ground. All negative."""
    return (
        -abs(
            float(
                _setting(settings, "friendship_ff_air_flight", FRIENDLY_FIRE_AIR_FLIGHT)
            )
        ),
        -abs(
            float(
                _setting(
                    settings, "friendship_ff_air_squadron", FRIENDLY_FIRE_AIR_SQUADRON
                )
            )
        ),
        -abs(float(_setting(settings, "friendship_ff_ground", FRIENDLY_FIRE_GROUND))),
    )


# --- what it is worth -----------------------------------------------------------


def xp_bonus(mean: float, settings: Any = None) -> float:
    """What the company he flew in adds to his multiplier.

    Signed: a formation he cannot stand is worth less than flying alone, and that is the
    point of it. The multiplier itself is floored by the caller -- experience never goes
    backwards.
    """
    per = float(_setting(settings, "friendship_xp_per_point", XP_PER_POINT))
    return round(points(mean)) * per


def survival_bonus(mean: float, settings: Any = None) -> float:
    """How much harder they look for a man they like.

    Positive only. Being disliked does not make anybody slower to reach a burning
    cockpit; they are pilots, not murderers.
    """
    per = _percent(settings, "friendship_survival_per_point", SURVIVAL_PER_POINT)
    cap = _percent(settings, "friendship_survival_cap", SURVIVAL_CAP)
    return min(cap, max(0.0, points(mean)) * per)


def desertion_modifier(mean: float, settings: Any = None) -> float:
    """What is left of his chance of walking away, as a fraction of it.

    Rank is what held him there until now. The man in the next bunk is the better half
    of the story.
    """
    per = _percent(settings, "friendship_desertion_per_point", DESERTION_PER_POINT)
    cap = _percent(settings, "friendship_desertion_cap", DESERTION_CAP)
    return 1.0 - min(cap, max(0.0, points(mean)) * per)


def leave_multiplier(mean: float, settings: Any = None) -> float:
    """How much more a week off is worth when it is taken with the others.

    1.0 when he is away on his own, which is what the mean of nobody comes to.
    """
    per = _percent(
        settings, "friendship_leave_together_per_point", LEAVE_TOGETHER_PER_POINT
    )
    cap = _percent(settings, "friendship_leave_together_cap", LEAVE_TOGETHER_CAP)
    return 1.0 + min(cap, max(0.0, points(mean)) * per)


def drift_help(friends: int, settings: Any = None) -> float:
    """How much faster a man in trouble comes home for each friend around him."""
    per = _percent(settings, "friendship_drift_help_per_friend", DRIFT_HELP_PER_FRIEND)
    cap = _percent(settings, "friendship_drift_help_cap", DRIFT_HELP_CAP)
    return 1.0 + min(cap, max(0, friends) * per)


def grief_times(times: int, value: float, settings: Any = None) -> int:
    """How many times a death lands on the man who was flying beside him.

    A whole number, because the event is repeated rather than scaled -- and never below
    one. An enemy mourns once: a man he hated dying in front of him is still a man dying
    in front of him.
    """
    per = float(_setting(settings, "friendship_grief_per_point", GRIEF_PER_POINT))
    cap = float(_setting(settings, "friendship_grief_cap", GRIEF_CAP))
    scale = min(cap, 1.0 + max(0.0, points(value)) * per)
    return max(1, round(times * scale))


def synergy_floor(settings: Any = None) -> float:
    return float(_setting(settings, "friendship_synergy_floor", SYNERGY_FLOOR))


def flies_a_rung_better(value: float, settings: Any = None) -> bool:
    """Whether a formation this close flies above the rank it holds."""
    return value >= synergy_floor(settings)


# --- housekeeping ---------------------------------------------------------------


def trim(pilot: Pilot, settings: Any = None) -> None:
    """Keep only the opinions he holds most strongly.

    A campaign fought over a hundred turns would otherwise have every survivor carrying
    an entry for every man he ever shared a base with, alive or dead.
    """
    limit = int(_setting(settings, "friendship_limit", FRIENDSHIP_LIMIT))
    if len(pilot.friendships) <= limit:
        return
    strongest = sorted(
        pilot.friendships.items(), key=lambda item: abs(points(item[1])), reverse=True
    )[:limit]
    pilot.friendships = dict(strongest)


def prune(pilot: Pilot, living: set[UUID]) -> None:
    """Forget the men who are no longer anywhere."""
    gone = [other for other in pilot.friendships if other not in living]
    for other in gone:
        del pilot.friendships[other]


# --- a turn of it ----------------------------------------------------------------


def pilots_by_base(
    air_wing: AirWing,
) -> dict[ControlPoint, list[tuple[Squadron, Pilot]]]:
    """Everybody living at each base, each with the squadron he belongs to.

    One bucketing pass over the wing rather than a property on ControlPoint: asking a
    base for its squadrons is itself a scan of every squadron in the wing, so a call
    per base would be quadratic -- and the drift wants the squadron beside the pilot
    anyway, to know which of the two tables a pair rolls on.
    """
    bases: dict[ControlPoint, list[tuple[Squadron, Pilot]]] = defaultdict(list)
    for squadron in air_wing.iter_squadrons():
        for pilot in squadron.current_roster:
            if pilot.alive:
                bases[squadron.location].append((squadron, pilot))
    return dict(bases)


def tend_friendships(air_wing: AirWing, settings: Any = None) -> None:
    """One turn of ordinary acquaintance across a whole wing.

    Every pair of pilots at a base rolls twice, once in each direction, each with its
    own roll: one roll shared between the two halves would move them in lockstep and
    the direction would be decoration.

    Who is at the base is taken literally. The wounded and the men on leave are
    included -- a man in the infirmary is still somebody they see -- and so is the
    player's own pilot, which is the one place this differs from
    :meth:`Squadron.tend_morale`. He has no morale, because a figure moved behind his
    back could only get in his way, but he does have friends.
    """
    if not in_play(settings):
        return

    for crowd in pilots_by_base(air_wing).values():
        if len(crowd) < 2:
            continue
        for squadron, pilot in crowd:
            for other_squadron, other in crowd:
                if other is pilot:
                    continue
                step = drift_step(
                    other_squadron is squadron, feeling(pilot, other), settings
                )
                # A man who has watched enough people go down feels less of any of
                # it, warming and cooling alike.
                step = hardening.feels(pilot, step, settings)
                if step:
                    move(pilot, other, step)

    living = living_ids(air_wing)
    for squadron in air_wing.iter_squadrons():
        for pilot in squadron.current_roster:
            if not pilot.alive:
                # The dead keep what they thought of everyone, which is all the pilot
                # dialog has left of them. Only the living accumulate.
                continue
            prune(pilot, living)
            trim(pilot, settings)


def living_ids(air_wing: AirWing) -> set[UUID]:
    """Everyone in the wing a friendship can still be about.

    The pool as well as the roster: a man waiting to be called up has been nobody's
    friend yet, but he will be, and forgetting him a turn before he arrives would be
    a strange thing for the pass to do.
    """
    living: set[UUID] = set()
    for squadron in air_wing.iter_squadrons():
        living.update(pilot.id for pilot in squadron.current_roster if pilot.alive)
        living.update(pilot.id for pilot in squadron.pilot_pool)
    return living
