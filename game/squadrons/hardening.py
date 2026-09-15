"""Pilot hardening: a permanent counter earned by serving turns at low morale.

A pilot gains 1 to 3 points per turn spent Shaken, Shattered or Broken, and the counter
never decreases. Points reduce the morale hit he takes from events, raise his chance of
surviving a loss, and damp friendship changes in both directions.

Nothing is gained while wounded or on leave: only turns on duty count.

The constants below are defaults; each names the settings key that overrides it, as in
:mod:`game.squadrons.morale` and :mod:`game.squadrons.friendship`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from game.squadrons import morale as morale_rules

if TYPE_CHECKING:
    from game.squadrons.pilot import Pilot

#: Bounds of the counter. It only ever increases.
HARDENING_MIN = 0
HARDENING_MAX = 40

#: Points gained per turn, by the morale state the pilot started the turn in. States
#: above Shaken gain nothing.
SHAKEN = 1
SHATTERED = 2
BROKEN = 3

#: Which state each of those belongs to, and the settings key that sizes it.
HARDENING_BY_STATE: tuple[tuple[str, str, int], ...] = (
    ("Shaken", "hardening_shaken", SHAKEN),
    ("Shattered", "hardening_shattered", SHATTERED),
    ("Broken", "hardening_broken", BROKEN),
)

#: What one point is worth for each effect, as a percentage. Per point rather than per
#: full counter so the arithmetic is simple: 30 points takes 30 x 2 = 60% off a morale
#: hit.
MORALE_RELIEF_PER_POINT = 2.0
SURVIVAL_PER_POINT = 0.5
FRIENDSHIP_DAMPING_PER_POINT = 1.5


def _setting(settings: Any, key: str, default: Any) -> Any:
    return default if settings is None else getattr(settings, key, default)


def _percent(settings: Any, key: str, default: Any) -> float:
    return float(_setting(settings, key, default)) / 100.0


def in_play(settings: Any) -> bool:
    """Whether hardening is enabled.

    Requires morale as well as Live Pilots: points are earned from the morale bands and
    most of the effects apply to morale.
    """
    return (
        bool(_setting(settings, "live_pilots_enabled", True))
        and bool(_setting(settings, "morale_enabled", True))
        and bool(_setting(settings, "hardening_enabled", True))
    )


def ceiling(settings: Any = None) -> int:
    return int(_setting(settings, "hardening_max", HARDENING_MAX))


def _worth(hardened: int, settings: Any, key: str, default: float) -> float:
    """One effect at this many points, capped at 1.0."""
    return min(1.0, max(0, hardened) * _percent(settings, key, default))


# --- earning it ------------------------------------------------------------------


def gain_for(morale: int, settings: Any = None) -> int:
    """Points for one turn spent at this morale, or 0 above the Shaken band."""
    if not in_play(settings):
        return 0
    state = morale_rules.morale_state(morale, settings).name
    for name, key, default in HARDENING_BY_STATE:
        if name == state:
            return int(_setting(settings, key, default))
    return 0


def harden(pilot: Pilot, morale: int, settings: Any = None) -> int:
    """Apply one turn of hardening and return the points gained.

    ``morale`` is the value the pilot started the turn with, not the one he ends it
    with, matching how the desertion roll is judged. A pilot who is wounded or on leave
    gains nothing.
    """
    if pilot.wounded or pilot.on_leave:
        return 0
    gained = gain_for(morale, settings)
    if not gained:
        return 0
    before = pilot.hardened
    pilot.hardened = min(ceiling(settings), before + gained)
    return pilot.hardened - before


# --- what it is worth ------------------------------------------------------------


def morale_relief(hardened: int, settings: Any = None) -> float:
    """Fraction of a negative morale event the pilot does not feel.

    Negative events only; gains are unaffected, as with
    :func:`game.squadrons.morale.resistance`.
    """
    if not in_play(settings):
        return 0.0
    return _worth(
        hardened, settings, "hardening_morale_relief_per_point", MORALE_RELIEF_PER_POINT
    )


def survival_bonus(hardened: int, settings: Any = None) -> float:
    """Added to the ejection roll and to the roll for surviving a wound."""
    if not in_play(settings):
        return 0.0
    return _worth(
        hardened, settings, "hardening_survival_per_point", SURVIVAL_PER_POINT
    )


def friendship_damping(hardened: int, settings: Any = None) -> float:
    """Fraction by which friendship changes are reduced, in both directions."""
    if not in_play(settings):
        return 0.0
    return _worth(
        hardened,
        settings,
        "hardening_friendship_damping_per_point",
        FRIENDSHIP_DAMPING_PER_POINT,
    )


def feels(pilot: Pilot, amount: float, settings: Any = None) -> float:
    """Apply this pilot's damping to a friendship change.

    Only to changes in his own opinion of others; what they think of him is unaffected.
    Warming and cooling are damped alike.
    """
    if not amount:
        return amount
    return amount * (1.0 - friendship_damping(pilot.hardened, settings))
