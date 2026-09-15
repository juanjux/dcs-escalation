"""Per-pair friendship between pilots.

The value runs 0 to 10 and starts at 5. It is directional: what A feels about B is
stored separately from what B feels about A, and the two effects read opposite
directions -- a pilot's skill bonus uses his own opinion of the formation, while the
chance of being rescued uses what the others think of him.

It changes in two ways: a small per-turn drift between everyone at the same base (a
higher chance within a squadron than across the ramp), and larger gains for flying a
sortie together. The drift alone cannot reach the bands that grant bonuses.

The constants below are defaults; each names the settings key that overrides it, as in
:mod:`game.squadrons.morale`.
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

#: Bounds of the scale and the value an unrecorded pair is treated as having. Saves
#: written before friendship existed read as 5 for every pair.
FRIENDSHIP_MIN = 0.0
FRIENDSHIP_MAX = 10.0
FRIENDSHIP_START = 5.0


@dataclass(frozen=True)
class FriendshipBand:
    """One band of the scale.

    ``floor`` is the inclusive bottom of the band. ``colour`` is what the lists paint
    it, and is None for Neutral, which is not painted. ``key`` is the setting that moves
    the floor, and is None for the bottom band.
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
    """The value as a distance from Neutral: 0..10 becomes -5..+5.

    Every effect is priced per point on this scale.
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
    """Mean of what ``pilot`` thinks of ``others``. Neutral if the list is empty.

    With a leader given, the pair that includes him is weighted
    :data:`LEADER_SPOKE_WEIGHT` times the others. Asked about the leader himself the
    weighting does not apply and this is the plain mean.
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
    """Mean of what ``others`` think of ``pilot``, weighted as :func:`mean_towards`.

    This is the direction the rescue chance reads.
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
    """Mean of both directions between ``pilot`` and ``others``.

    Used by the pilot selector, where the question is about the pair rather than about
    one direction of it.
    """
    group = [other for other in others if other is not pilot]
    if not group:
        return FRIENDSHIP_START
    return (mean_towards(pilot, group) + mean_from(pilot, group)) / 2


def synergy(
    pilots: Sequence[Pilot], leader: Optional[Pilot] = None, settings: Any = None
) -> float:
    """The formation's figure: the mean of each pilot's weighted mean of the others.

    Weighting the leader's pairs higher makes one good leader per flight worth more
    than several in the same flight.
    """
    crew = [pilot for pilot in pilots if pilot is not None]
    if len(crew) < 2:
        return FRIENDSHIP_START
    values = [mean_towards(member, crew, leader, settings) for member in crew]
    return sum(values) / len(values)


# --- writing --------------------------------------------------------------------


def move(pilot: Pilot, other: Pilot, amount: float) -> float:
    """Move one direction of one pair and return the distance actually moved.

    Only ``pilot``'s opinion of ``other``; the opposite direction is moved by its own
    call, so that a shared sortie is not credited twice.
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


def drift_step(
    same_squadron: bool,
    current: float,
    settings: Any = None,
    returned: Optional[float] = None,
) -> float:
    """One turn of drift in one direction: up, down or unchanged, on the campaign's odds.

    A rise stops at :func:`drift_ceiling`, so the bands that grant bonuses can only be
    reached by flying together. A fall is not floored.

    ``returned`` is the opposite direction's value. Where it is higher, the warming
    chance is raised by :func:`reciprocity_bonus`.
    """
    up, down = drift_odds(same_squadron, settings)
    up = min(100.0, up + reciprocity_bonus(current, returned, settings))
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

#: Added to the warming chance for each point the other man's opinion is above his
#: own. A pair four points apart rolls twenty percentage points likelier to close, on
#: top of the ordinary odds; the cooling roll is left alone.
RECIPROCITY_PER_POINT = 5.0

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
    """Whether friendship is enabled. Requires Live Pilots, and can be turned off on its
    own, in which case nothing reads or writes the graph and the turn-end pass is
    skipped.
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


def reciprocity_bonus(
    current: float, returned: Optional[float], settings: Any = None
) -> float:
    """Percentage points added to the warming chance for the difference between the two
    directions of a pair.

    Only when ``returned`` is the higher of the two, and only to the warming roll; the
    cooling roll is unaffected. Each point of difference on the 0 to 10 scale is worth
    the campaign's per-point figure.
    """
    if returned is None:
        return 0.0
    gap = returned - current
    if gap <= 0:
        return 0.0
    return gap * float(
        _setting(settings, "friendship_reciprocity_per_point", RECIPROCITY_PER_POINT)
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
    """Signed experience multiplier bonus for the formation: negative below Neutral.

    The caller floors the resulting multiplier, so experience never decreases.
    """
    per = float(_setting(settings, "friendship_xp_per_point", XP_PER_POINT))
    return round(points(mean)) * per


def survival_bonus(mean: float, settings: Any = None) -> float:
    """Bonus to the rescue chance from what the others think of him. Never negative."""
    per = _percent(settings, "friendship_survival_per_point", SURVIVAL_PER_POINT)
    cap = _percent(settings, "friendship_survival_cap", SURVIVAL_CAP)
    return min(cap, max(0.0, points(mean)) * per)


def desertion_modifier(mean: float, settings: Any = None) -> float:
    """Multiplier applied to the desertion chance, from the friendships he has."""
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
    """How many times the death event is applied to a survivor, as a whole number.

    The event is repeated rather than scaled, and the result is never below one.
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
    """Keep only the entries furthest from Neutral, capped at :data:`MAX_FRIENDSHIPS`.

    Without it a long campaign leaves every pilot holding an entry for everyone he ever
    shared a base with.
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
    """Living pilots grouped by base, each paired with the squadron he belongs to.

    One pass over the wing rather than a per-base lookup, which would be quadratic. The
    squadron is carried because the drift needs it to pick which odds table applies.
    """
    bases: dict[ControlPoint, list[tuple[Squadron, Pilot]]] = defaultdict(list)
    for squadron in air_wing.iter_squadrons():
        for pilot in squadron.current_roster:
            if pilot.alive:
                bases[squadron.location].append((squadron, pilot))
    return dict(bases)


def tend_friendships(air_wing: AirWing, settings: Any = None) -> None:
    """One turn of drift across the whole wing.

    Every pair of pilots at a base rolls twice, once per direction and with its own
    roll, so the two directions can move differently.

    The wounded, the pilots on leave and the player's own pilot are all included, which
    is where this differs from :meth:`Squadron.tend_morale`: the player's pilot has no
    morale but does have friendships.
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
                    other_squadron is squadron,
                    feeling(pilot, other),
                    settings,
                    returned=feeling(other, pilot),
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
    """Ids of every living pilot in the wing, from the pool as well as the rosters."""
    living: set[UUID] = set()
    for squadron in air_wing.iter_squadrons():
        living.update(pilot.id for pilot in squadron.current_roster if pilot.alive)
        living.update(pilot.id for pilot in squadron.pilot_pool)
    return living
