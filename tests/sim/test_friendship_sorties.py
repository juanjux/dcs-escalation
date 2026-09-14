"""What flying together -- and shooting one of ours -- does to a pair.

Every rule here is a place the obvious implementation is wrong: a shared sortie has to
move each directed edge exactly once rather than once per man in it, the bonds must not
be spent until everything that reads them has read them, and friendly fire has to take
the worst of the applicable penalties rather than their sum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import patch

from game.game import Game
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons import friendship
from game.squadrons.pilot import Pilot


@dataclass(eq=False)
class _Roster:
    pilots: list[Pilot]

    def iter_pilots(self) -> Iterator[Pilot]:
        return iter(self.pilots)


@dataclass(eq=False)
class _Squadron:
    current_roster: list[Pilot] = field(default_factory=list)


@dataclass(eq=False)
class _Flight:
    roster: _Roster
    squadron: Any = None


@dataclass(eq=False)
class _Package:
    flights: list[_Flight]


def _flight(*pilots: Pilot, squadron: Any = None) -> _Flight:
    return _Flight(_Roster(list(pilots)), squadron)


def _processor(**settings: Any) -> MissionResultsProcessor:
    values: dict[str, Any] = {"live_pilots_enabled": True, "friendship_enabled": True}
    values.update(settings)
    return MissionResultsProcessor(
        cast(Game, SimpleNamespace(settings=SimpleNamespace(**values), turn=1))
    )


def _fly(processor: MissionResultsProcessor, package: _Package) -> None:
    """One sortie: every pilot in the package takes his own turn through the loop."""
    for flight in package.flights:
        for pilot in flight.roster.iter_pilots():
            processor._note_flying_together(package, flight, pilot)


# --- flying together -------------------------------------------------------------


def test_a_wingman_is_worth_more_than_a_man_in_the_next_flight() -> None:
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    escort = Pilot("Escort")
    package = _Package([_flight(lead, wingman), _flight(escort)])
    processor = _processor()
    _fly(processor, package)
    processor._commit_friendship()

    assert friendship.feeling(lead, wingman) == 7.0
    assert friendship.feeling(wingman, lead) == 7.0
    assert friendship.feeling(lead, escort) == 6.0
    assert friendship.feeling(escort, lead) == 6.0


def test_a_sortie_moves_each_directed_edge_exactly_once() -> None:
    """Not once per man who was in it: moving both halves while processing each pilot
    would pay the same sortie twice, and the pair would climb at double speed."""
    crew = [Pilot(f"P{index}") for index in range(4)]
    processor = _processor()
    _fly(processor, _Package([_flight(*crew)]))
    with patch("game.squadrons.friendship.move") as move:
        processor._commit_friendship()
    assert move.call_count == 4 * 3


def test_nothing_is_spent_until_everything_has_read_it() -> None:
    """The multiplier a sortie pays is worked out from what the men thought of each
    other before it. Applying a bond as it is earned would make what a pilot earns
    depend on where he happens to sit in the loop."""
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    processor = _processor()
    _fly(processor, _Package([_flight(lead, wingman)]))
    assert friendship.feeling(lead, wingman) == friendship.FRIENDSHIP_START
    processor._commit_friendship()
    assert friendship.feeling(lead, wingman) == 7.0


def test_three_sorties_in_a_turn_are_not_a_shortcut() -> None:
    """+2 a sortie with no ceiling reaches the top of the scale in a fortnight, and
    friendship stops being slow."""
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    package = _Package([_flight(lead, wingman)])
    processor = _processor()
    for _ in range(3):
        _fly(processor, package)
    processor._commit_friendship()
    assert friendship.feeling(lead, wingman) == 9.0  # 5 + the 4 a turn can carry


def test_switched_off_a_sortie_is_just_a_sortie() -> None:
    lead, wingman = Pilot("Lead"), Pilot("Wingman")
    processor = _processor(friendship_enabled=False)
    _fly(processor, _Package([_flight(lead, wingman)]))
    processor._commit_friendship()
    assert lead.friendships == {}
    assert wingman.friendships == {}


# --- friendly fire ---------------------------------------------------------------


def _shot_down_one_of_ours() -> tuple[MissionResultsProcessor, dict[str, Pilot]]:
    """A shooter, a man who only watched, a man who only heard, and a man who did both.

    Everybody starts thinking well of the shooter so the clamp at the bottom of the
    scale cannot hide the difference between the worst penalty and the sum of them.
    """
    shooter = Pilot("Shooter")
    watched = Pilot("Watched")  # in the shooter's flight
    heard = Pilot("Heard")  # in the victim's squadron
    both = Pilot("Both")  # in each
    victim = Pilot("Victim")
    for mourner in (watched, heard, both, victim):
        friendship.move(mourner, shooter, 4.0)

    squadron = _Squadron([victim, heard, both])
    killer = SimpleNamespace(pilot=shooter, flight=_flight(shooter, watched, both))
    return _processor(), {
        "shooter": shooter,
        "watched": watched,
        "heard": heard,
        "both": both,
        "victim": victim,
        "killer": cast(Pilot, killer),
        "squadron": cast(Pilot, squadron),
    }


def test_the_flight_and_the_squadron_price_it_differently() -> None:
    processor, men = _shot_down_one_of_ours()
    victim_flight = _flight(men["victim"], squadron=men["squadron"])
    processor._note_friendly_fire_event(
        men["killer"], SimpleNamespace(flight=victim_flight)
    )
    processor._commit_friendship()

    assert friendship.feeling(men["watched"], men["shooter"]) == 6.0  # 9 - 3
    assert friendship.feeling(men["heard"], men["shooter"]) == 3.0  # 9 - 6
    assert friendship.feeling(men["victim"], men["shooter"]) == 3.0


def test_a_man_in_both_rooms_does_not_think_twice_as_badly_of_him() -> None:
    """-3 and -6 is -6, never -9. He was there once."""
    processor, men = _shot_down_one_of_ours()
    victim_flight = _flight(men["victim"], squadron=men["squadron"])
    processor._note_friendly_fire_event(
        men["killer"], SimpleNamespace(flight=victim_flight)
    )
    processor._commit_friendship()
    assert friendship.feeling(men["both"], men["shooter"]) == 3.0


def test_a_man_does_not_hold_it_against_himself() -> None:
    processor, men = _shot_down_one_of_ours()
    victim_flight = _flight(men["victim"], squadron=men["squadron"])
    processor._note_friendly_fire_event(
        men["killer"], SimpleNamespace(flight=victim_flight)
    )
    processor._commit_friendship()
    assert men["shooter"].friendships == {}


def test_hitting_our_own_on_the_ground_costs_less_and_stays_in_the_flight() -> None:
    """A truck has no squadron to hear about it."""
    processor, men = _shot_down_one_of_ours()
    processor._note_friendly_fire_event(men["killer"], SimpleNamespace())
    processor._commit_friendship()

    assert friendship.feeling(men["watched"], men["shooter"]) == 7.0  # 9 - 2
    assert friendship.feeling(men["heard"], men["shooter"]) == 9.0  # heard nothing
