"""What friendship is worth once the shooting is over.

Two effects read opposite ends of the same pair, which is the whole reason it has a
direction: a pilot learns more from a formation *he* likes, and is pulled out of a
wreck by men who like *him*. Getting either the wrong way round would look right in
every campaign until somebody looked.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.sim import missionresultsprocessor
from game.sim.missionresultsprocessor import MissionResultsProcessor
from game.squadrons import friendship
from game.squadrons import morale as morale_rules
from game.squadrons.experience import PilotOutcomes
from game.squadrons.pilot import Pilot, PilotStatus


class _Squadron:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.player = SimpleNamespace(is_blue=True)

    def pilot_skill(self, pilot: Pilot) -> Any:
        return CADET_SKILL

    def leader_of(self, crew: Any) -> Any:
        """Everybody here holds the same rank, so it is the first man in the list."""
        return next((pilot for pilot in crew if pilot is not None), None)

    def pilot_rank(self, pilot: Pilot) -> Any:
        return None

    def __str__(self) -> str:
        return "VFA-2"


def _settings(**values: Any) -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    for name, value in values.items():
        setattr(settings, name, value)
    return settings


def _processor(settings: Settings) -> MissionResultsProcessor:
    game = MagicMock()
    game.settings = settings
    game.turn = 4
    return MissionResultsProcessor(game)


def _flight(*pilots: Pilot, settings: Settings) -> Any:
    return SimpleNamespace(
        squadron=_Squadron(settings),
        unit_type="F/A-18C",
        roster=SimpleNamespace(iter_pilots=lambda: iter(pilots)),
    )


# --- experience: what he makes of the company he flew in -------------------------


def _multiplier(settings: Settings, pilot: Pilot, *mates: Pilot) -> float:
    processor = _processor(settings)
    flight = _flight(pilot, *mates, settings=settings)
    return processor._xp_multiplier(flight, flight.squadron, pilot)


def test_a_formation_he_thinks_well_of_pays_more() -> None:
    settings = _settings(morale_enabled=False)
    pilot, mate = Pilot("Vega"), Pilot("Wingman")
    alone = _multiplier(settings, pilot)
    friendship.move(pilot, mate, 4.0)  # Inseparable, +4 points
    assert _multiplier(settings, pilot, mate) == pytest.approx(alone + 0.20)


def test_a_formation_he_cannot_stand_pays_less() -> None:
    """Signed, and that is the point of it: being made to fly with a man he hates is
    worth less to him than flying on his own."""
    settings = _settings(morale_enabled=False)
    pilot, mate = Pilot("Vega"), Pilot("Wingman")
    friendship.move(pilot, mate, -4.0)
    assert _multiplier(settings, pilot, mate) == pytest.approx(0.80)


def test_it_reads_what_he_thinks_of_them_and_not_what_they_think_of_him() -> None:
    settings = _settings(morale_enabled=False)
    pilot, mate = Pilot("Vega"), Pilot("Wingman")
    friendship.move(mate, pilot, 4.0)  # she thinks the world of him; he is indifferent
    assert _multiplier(settings, pilot, mate) == pytest.approx(1.0)


def test_flying_alone_is_worth_neither_more_nor_less() -> None:
    settings = _settings(morale_enabled=False)
    assert _multiplier(settings, Pilot("Vega")) == pytest.approx(1.0)


def test_the_multiplier_never_goes_below_zero() -> None:
    """Experience does not go backwards. A hated formation can make a sortie worth
    nothing; it cannot demote him."""
    settings = _settings(morale_enabled=True, friendship_xp_per_point=25)
    pilot = Pilot("Vega")
    pilot.morale = morale_rules.MORALE_MIN
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    for mate in mates:
        friendship.move(pilot, mate, -5.0)
    assert _multiplier(settings, pilot, *mates) == 0.0


def test_switched_off_a_sortie_pays_what_it_always_did() -> None:
    settings = _settings(morale_enabled=False, friendship_enabled=False)
    pilot, mate = Pilot("Vega"), Pilot("Wingman")
    friendship.move(pilot, mate, 4.0)
    assert _multiplier(settings, pilot, mate) == pytest.approx(1.0)


# --- survival: how hard they look for him ----------------------------------------


def _fate(settings: Settings, pilot: Pilot, *mates: Pilot) -> Any:
    processor = _processor(settings)
    loss = SimpleNamespace(
        pilot=pilot, flight=_flight(pilot, *mates, settings=settings)
    )
    debriefing: Any = SimpleNamespace(
        pilot_outcomes=PilotOutcomes(),
        kill_info_by_unit_id={},
        unit_map=SimpleNamespace(flight=lambda name: None),
    )
    processor._resolve_pilot_fate(loss, debriefing)
    return debriefing.pilot_outcomes


def test_the_men_who_like_him_go_looking(monkeypatch: pytest.MonkeyPatch) -> None:
    """The roll that kills a man on his own spares one his flight thinks well of.

    Rank alone buys him 0.20 here; three men who are Inseparable with him add another
    0.15, and the roll lands in between.
    """
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.30)
    settings = _settings(live_pilots_rank_survival=True, morale_enabled=False)
    settings.live_pilots_wounded_chance = 0

    alone = Pilot("Alone")
    assert _fate(settings, alone).deaths

    liked = Pilot("Liked")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    for mate in mates:
        friendship.move(mate, liked, 5.0)
    assert _fate(settings, liked, *mates).survivors


def test_being_liked_is_not_the_same_as_liking(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other direction does nothing: what saves him is what they think of him."""
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.30)
    settings = _settings(live_pilots_rank_survival=True, morale_enabled=False)
    settings.live_pilots_wounded_chance = 0

    pilot = Pilot("Vega")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    for mate in mates:
        friendship.move(pilot, mate, 5.0)  # he adores them; they are indifferent
    assert _fate(settings, pilot, *mates).deaths


def test_being_disliked_does_not_slow_anybody_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.15)
    settings = _settings(live_pilots_rank_survival=True, morale_enabled=False)
    settings.live_pilots_wounded_chance = 0

    hated = Pilot("Hated")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    for mate in mates:
        friendship.move(mate, hated, -5.0)
    assert _fate(settings, hated, *mates).survivors  # the same 0.20 he always had


def test_the_medics_are_quicker_for_a_man_they_like(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wound roll reads the same half, and it is flat -- rank buys the first roll,
    not this one."""
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.40)
    monkeypatch.setattr(missionresultsprocessor.random, "randint", lambda lo, hi: 2)
    settings = _settings(morale_enabled=False)
    settings.live_pilots_wounded_chance = 35

    doomed = Pilot("Doomed")
    assert _fate(settings, doomed).deaths

    liked = Pilot("Liked")
    mates = [Pilot(f"Mate{index}") for index in range(3)]
    for mate in mates:
        friendship.move(mate, liked, 5.0)  # 0.35 + 0.15 clears the roll
    assert _fate(settings, liked, *mates).wounded


# --- grief: what it costs to have had a friend -----------------------------------


def _mourned(settings: Settings, mourner: Pilot, casualty: Pilot) -> int:
    processor = _processor(settings)
    flight = _flight(mourner, casualty, settings=settings)
    processor._note_flight_morale(flight, casualty, morale_rules.FLIGHT_DEATH)
    return len(processor._morale_events.get(id(mourner), []))


def test_a_friend_going_down_is_felt_more_than_a_stranger() -> None:
    settings = _settings()
    stranger, casualty = Pilot("Stranger"), Pilot("Casualty")
    assert _mourned(settings, stranger, casualty) == 1

    friend = Pilot("Friend")
    friendship.move(friend, casualty, 5.0)
    assert _mourned(settings, friend, casualty) > 1


def test_a_man_he_could_not_stand_is_still_mourned_once() -> None:
    """Whole numbers, because the event is repeated rather than scaled -- and never
    zero times: a man he hated dying in front of him is still a man dying in front of
    him."""
    settings = _settings()
    enemy, casualty = Pilot("Enemy"), Pilot("Casualty")
    friendship.move(enemy, casualty, -5.0)
    assert _mourned(settings, enemy, casualty) == 1


def test_switched_off_every_death_weighs_the_same() -> None:
    settings = _settings(friendship_enabled=False)
    friend, casualty = Pilot("Friend"), Pilot("Casualty")
    friendship.move(friend, casualty, 5.0)
    assert _mourned(settings, friend, casualty) == 1


def test_the_dead_do_not_mourn_themselves() -> None:
    settings = _settings()
    casualty = Pilot("Casualty")
    casualty.status = PilotStatus.Dead
    assert _mourned(settings, casualty, casualty) == 0
