"""Unit tests for who holds a place in a squadron.

The pilot limit is a limit on the establishment, not on who happens to be fit to fly
this turn. A wounded pilot and a pilot on leave are both coming back, so their places
are not free to recruit into; a man who is dead, deserted or discharged is gone and his
is.

Counting only the active and the wounded is how a squadron limited to sixteen reached
twenty-four with twelve men resting, and how one that merely backfilled a single absence
sat at seventeen the day he came back.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from game.settings import Settings
from game.squadrons.pilot import Pilot, PilotStatus


def _squadron(limit: int = 16, rate: int = 4) -> Any:
    from game.squadrons.squadron import Squadron

    settings = Settings()
    settings.enable_squadron_pilot_limits = True
    settings.squadron_pilot_limit = limit
    settings.squadron_replenishment_rate = rate

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.name = "Zero Company"
    squadron.current_roster = []
    squadron.coalition = SimpleNamespace(
        player=SimpleNamespace(is_blue=True), game=SimpleNamespace(turn=6)
    )
    return squadron


def _man(squadron: Any, status: PilotStatus) -> Pilot:
    pilot = Pilot(f"Pilot {len(squadron.current_roster)}")
    pilot.status = status
    squadron.current_roster.append(pilot)
    return pilot


def _fill(squadron: Any, **counts: int) -> Any:
    for name, count in counts.items():
        for _ in range(count):
            _man(squadron, PilotStatus[name])
    return squadron


@pytest.mark.parametrize(
    "status",
    [PilotStatus.Active, PilotStatus.Wounded, PilotStatus.OnLeave],
)
def test_a_man_still_on_the_books_holds_his_place(status: PilotStatus) -> None:
    """Whether he can fly this turn or not: he is coming back to it."""
    squadron = _fill(_squadron(limit=16), Active=15)
    _man(squadron, status)

    assert squadron.replenish_count == 0


@pytest.mark.parametrize(
    "status",
    [PilotStatus.Dead, PilotStatus.Deserted, PilotStatus.Discharged],
)
def test_a_man_who_is_gone_frees_his_place(status: PilotStatus) -> None:
    squadron = _fill(_squadron(limit=16), Active=15)
    _man(squadron, status)

    assert squadron.replenish_count == 1


def test_the_replenishment_rate_is_the_ceiling() -> None:
    """Eight places open, four a turn."""
    squadron = _fill(_squadron(limit=16, rate=4), Active=8)

    assert squadron.replenish_count == 4


def test_a_squadron_over_its_limit_recruits_nobody() -> None:
    """The Apache: twelve flying, twelve resting, a limit of sixteen.

    It used to read four free places and recruit into them. It comes back down on its
    own now as men are lost, rather than having anyone taken off it.
    """
    squadron = _fill(_squadron(limit=16), Active=12, OnLeave=12)

    assert squadron.replenish_count == 0


def test_being_over_the_limit_never_reads_as_a_shrinking_squadron() -> None:
    """A negative count would have told procurement the squadron was losing men."""
    squadron = _fill(_squadron(limit=16), Active=17)

    assert squadron.replenish_count == 0
    assert squadron.expected_pilots_next_turn == 17


def test_the_dead_do_not_hold_places_open_for_ever() -> None:
    """A long campaign accumulates them, and they must not squeeze the living out."""
    squadron = _fill(_squadron(limit=16), Active=10, Dead=30)

    assert squadron.replenish_count == 4


# --- coming back from leave -----------------------------------------------------
#
# The place a man on leave holds is his own. Asking for a free one before letting him
# back refused every recall in a squadron at full strength -- two aircraft on the ramp,
# one pilot fit to fly, and the man resting next door could not be called in.


def _squadron_with_a_man_on_leave(limit: int = 16) -> tuple[Any, Pilot]:
    squadron = _fill(_squadron(limit=limit), Active=limit - 1)
    squadron.available_pilots = list(squadron.current_roster)
    resting = _man(squadron, PilotStatus.Active)
    squadron.send_on_leave(resting, turns=3, turn=6)
    return squadron, resting


def test_a_squadron_at_its_limit_can_still_call_a_man_back() -> None:
    squadron, resting = _squadron_with_a_man_on_leave()
    assert not squadron.has_unfilled_pilot_slots

    squadron.cancel_leave(resting)

    assert not resting.on_leave
    assert resting in squadron.available_pilots


def test_calling_him_back_does_not_grow_the_squadron() -> None:
    squadron, resting = _squadron_with_a_man_on_leave()
    before = len(squadron.living_pilots)

    squadron.cancel_leave(resting)

    assert len(squadron.living_pilots) == before
    assert squadron.living_pilots.count(resting) == 1


def test_his_place_is_not_free_while_he_is_away() -> None:
    """Which is what makes the recall safe: nobody can have taken it."""
    squadron, _ = _squadron_with_a_man_on_leave()

    assert squadron._number_of_unfilled_pilot_slots == 0
    assert squadron.replenish_count == 0


def test_only_a_man_on_leave_can_have_it_cancelled() -> None:
    squadron = _fill(_squadron(), Active=3)
    squadron.available_pilots = list(squadron.current_roster)

    with pytest.raises(RuntimeError):
        squadron.cancel_leave(squadron.current_roster[0])
