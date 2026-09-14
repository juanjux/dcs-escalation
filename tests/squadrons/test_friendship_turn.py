"""The turn-end pass: who rolls against whom, and who is left out.

The rule is literal -- every pair at a base, every turn, in each direction -- so what
is worth testing is the bookkeeping around it: that a pair is rolled once rather than
twice, that a base is a base and not a coalition, and that the two people morale
deliberately skips are handled the other way round here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import patch

from game.squadrons import friendship
from game.squadrons.pilot import Pilot, PilotStatus


@dataclass(eq=False)  # compared by identity, the way the real one is looked up
class _Squadron:
    location: str
    current_roster: list[Pilot]
    pilot_pool: list[Pilot] = field(default_factory=list)


class _AirWing:
    def __init__(self, *squadrons: _Squadron) -> None:
        self._squadrons = squadrons

    def iter_squadrons(self) -> Iterator[_Squadron]:
        return iter(self._squadrons)


def _wing(*squadrons: _Squadron) -> Any:
    return cast(Any, _AirWing(*squadrons))


def _settings(**values: Any) -> Any:
    settings = {"live_pilots_enabled": True, "friendship_enabled": True}
    settings.update(values)
    return SimpleNamespace(**settings)


def _pilots(count: int, prefix: str = "P") -> list[Pilot]:
    return [Pilot(f"{prefix}{index}") for index in range(count)]


def _tend(wing: Any, roll: float = 0.99, **settings: Any) -> int:
    """Run a turn with every roll the same, and say how many rolls it took."""
    with patch(
        "game.squadrons.friendship.random.random", return_value=roll
    ) as random_roll:
        friendship.tend_friendships(wing, _settings(**settings))
    return random_roll.call_count


# --- who is in it ---------------------------------------------------------------


def test_every_pair_at_a_base_is_rolled_once_in_each_direction() -> None:
    """Both halves of a pair move, but each on its own roll -- one roll shared between
    them would move them in lockstep and the direction would be decoration."""
    crew = _pilots(5)
    assert _tend(_wing(_Squadron("Nellis", crew))) == 5 * 4


def test_nobody_meets_the_squadron_at_the_next_base() -> None:
    here = _Squadron("Nellis", _pilots(4, "H"))
    there = _Squadron("Groom Lake", _pilots(4, "T"))
    assert _tend(_wing(here, there)) == 2 * (4 * 3)


def test_a_base_with_one_man_on_it_rolls_nothing() -> None:
    assert _tend(_wing(_Squadron("Nellis", _pilots(1)))) == 0


def test_the_player_is_in_it_even_though_morale_is_not_about_him() -> None:
    """tend_morale skips him on purpose: he decides for himself whether he is up to a
    sortie. Friendship is not a judgement on him, so he is in like everybody else."""
    player = Pilot("The Player", player=True)
    mate = Pilot("Wingman")
    _tend(_wing(_Squadron("Nellis", [player, mate])), roll=0.1)
    assert friendship.feeling(player, mate) == 6.0
    assert friendship.feeling(mate, player) == 6.0


def test_the_dead_and_the_discharged_are_not_at_the_base_any_more() -> None:
    here = Pilot("Here")
    gone = Pilot("Discharged")
    gone.status = PilotStatus.Discharged
    dead = Pilot("Dead")
    dead.status = PilotStatus.Dead
    assert _tend(_wing(_Squadron("Nellis", [here, gone, dead])), roll=0.1) == 0
    assert here.friendships == {}


def test_the_wounded_and_the_men_on_leave_still_live_there() -> None:
    here = Pilot("Here")
    hurt = Pilot("Wounded")
    hurt.status = PilotStatus.Wounded
    away = Pilot("On Leave")
    away.status = PilotStatus.OnLeave
    assert _tend(_wing(_Squadron("Nellis", [here, hurt, away])), roll=0.1) == 3 * 2
    assert friendship.feeling(here, hurt) == 6.0
    assert friendship.feeling(here, away) == 6.0


# --- which table a pair rolls on -------------------------------------------------


def test_one_roll_warms_his_own_squadron_and_cools_the_one_across_the_ramp() -> None:
    """25 is inside the squadron's 35 and outside the base's 22, which is the whole
    reason the pass carries the squadron around with the pilot."""
    mine = _pilots(2, "Mine")
    theirs = _pilots(2, "Theirs")
    wing = _wing(_Squadron("Nellis", mine), _Squadron("Nellis", theirs))
    _tend(wing, roll=0.25)
    assert friendship.feeling(mine[0], mine[1]) == 6.0
    assert friendship.feeling(mine[0], theirs[0]) == 4.0
    assert friendship.feeling(theirs[0], mine[0]) == 4.0


# --- housekeeping ----------------------------------------------------------------


def test_the_pass_forgets_the_men_who_are_gone() -> None:
    here, mate = Pilot("Here"), Pilot("Mate")
    gone = Pilot("Gone")
    friendship.move(here, gone, 3.0)
    friendship.move(here, mate, 1.0)
    _tend(_wing(_Squadron("Nellis", [here, mate])))
    assert set(here.friendships) == {mate.id}


def test_a_man_waiting_to_be_called_up_is_not_forgotten() -> None:
    """He has been nobody's friend yet, but forgetting him the turn before he arrives
    would be a strange thing for the pass to do."""
    here, mate = Pilot("Here"), Pilot("Mate")
    waiting = Pilot("Waiting")
    friendship.move(here, waiting, 3.0)
    wing = _wing(_Squadron("Nellis", [here, mate], pilot_pool=[waiting]))
    _tend(wing)
    assert waiting.id in here.friendships


def test_the_pass_caps_what_a_pilot_carries() -> None:
    here = Pilot("Here")
    crowd = _pilots(6, "C")
    for index, other in enumerate(crowd):
        friendship.move(here, other, (index + 1) * 0.1)
    _tend(_wing(_Squadron("Nellis", [here] + crowd)), friendship_limit=3)
    assert len(here.friendships) == 3


def test_the_dead_keep_what_they_thought_of_everybody() -> None:
    """It is all the pilot dialog has left of them, and nothing accumulates in a
    dictionary nobody is adding to."""
    dead, gone = Pilot("Dead"), Pilot("Gone")
    friendship.move(dead, gone, 3.0)
    dead.status = PilotStatus.Dead
    _tend(_wing(_Squadron("Nellis", [dead, Pilot("A"), Pilot("B")])))
    assert gone.id in dead.friendships


# --- switched off ----------------------------------------------------------------


def test_switched_off_it_does_not_even_roll() -> None:
    crew = _pilots(4)
    assert _tend(_wing(_Squadron("Nellis", crew)), friendship_enabled=False) == 0
    assert all(pilot.friendships == {} for pilot in crew)


def test_without_live_pilots_there_is_nobody_to_have_friends() -> None:
    crew = _pilots(4)
    assert _tend(_wing(_Squadron("Nellis", crew)), live_pilots_enabled=False) == 0


# --- the bucketing ---------------------------------------------------------------


def test_pilots_are_bucketed_by_base_with_their_squadron() -> None:
    mine, theirs = _pilots(2, "Mine"), _pilots(3, "Theirs")
    far = _pilots(1, "Far")
    nellis_one = _Squadron("Nellis", mine)
    nellis_two = _Squadron("Nellis", theirs)
    groom = _Squadron("Groom Lake", far)
    bases: dict[Any, Any] = dict(
        friendship.pilots_by_base(_wing(nellis_one, nellis_two, groom))
    )
    assert set(bases) == {"Nellis", "Groom Lake"}
    assert len(bases["Nellis"]) == 5
    assert {squadron for squadron, _ in bases["Nellis"]} == {nellis_one, nellis_two}
    assert len(bases["Groom Lake"]) == 1
