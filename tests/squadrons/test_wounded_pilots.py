"""Pilots the medics reach in time.

A loss that is not survived outright gets one more roll: instead of dying, the pilot
spends a few turns in hospital. Flat odds, deliberately -- rank buys the first roll,
not the second.
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
from game.squadrons.experience import PilotOutcomes, WOUNDED_TURNS, XP_WOUNDED
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


def _settings(*, survival: bool = False, wounded: int = 0) -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.live_pilots_rank_survival = survival
    settings.live_pilots_wounded_chance = wounded
    return settings


def _fate(settings: Settings, pilot: Pilot) -> Any:
    game = MagicMock()
    game.settings = settings
    processor = MissionResultsProcessor(game)
    loss = SimpleNamespace(
        pilot=pilot,
        flight=SimpleNamespace(
            squadron=_Squadron(settings),
            unit_type="F/A-18C",
            # The flight is asked who else was up there, to take it harder than the
            # rest of the squadron.
            roster=SimpleNamespace(iter_pilots=lambda: []),
        ),
    )
    debriefing: Any = SimpleNamespace(
        pilot_outcomes=PilotOutcomes(),
        kill_info_by_unit_id={},
        unit_map=SimpleNamespace(flight=lambda name: None),
    )
    processor._resolve_pilot_fate(loss, debriefing)
    return debriefing.pilot_outcomes


def test_the_medics_reach_him(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.0)
    monkeypatch.setattr(missionresultsprocessor.random, "randint", lambda lo, hi: 3)
    pilot = Pilot("Lt Vega")

    outcomes = _fate(_settings(wounded=35), pilot)

    assert pilot.status is PilotStatus.Wounded
    assert pilot.wounded_turns == 3
    assert not outcomes.deaths
    assert [(w.pilot_name, w.turns) for w in outcomes.wounded] == [("Lt Vega", 3)]


def test_they_do_not_reach_him(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.99)
    pilot = Pilot("Lt Vega")

    outcomes = _fate(_settings(wounded=35), pilot)

    assert pilot.status is PilotStatus.Dead
    assert not outcomes.wounded
    assert [d.pilot_name for d in outcomes.deaths] == ["Lt Vega"]


def test_walking_away_is_settled_before_the_medics_are_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pilot who survives outright is not also wounded."""
    monkeypatch.setattr(missionresultsprocessor.random, "random", lambda: 0.0)
    pilot = Pilot("Lt Vega")

    outcomes = _fate(_settings(survival=True, wounded=100), pilot)

    assert pilot.status is PilotStatus.Active
    assert outcomes.survivors and not outcomes.wounded and not outcomes.deaths


def test_however_it_ends_he_did_not_bring_the_aircraft_home() -> None:
    for settings in (_settings(), _settings(wounded=100)):
        pilot = Pilot("Lt Vega")
        outcomes = _fate(settings, pilot)
        assert outcomes.lost_aircraft == {id(pilot)}


def test_with_live_pilots_off_a_loss_is_still_a_death() -> None:
    settings = _settings(wounded=100)
    settings.live_pilots_enabled = False
    pilot = Pilot("Lt Vega")

    outcomes = _fate(settings, pilot)

    assert pilot.status is PilotStatus.Dead
    assert not outcomes.wounded


# --- the hospital -----------------------------------------------------------


def test_a_wound_is_served_a_turn_at_a_time() -> None:
    pilot = Pilot("Lt Vega")
    pilot.wound(2, turn=5)

    # Sampled rather than asserted in place: mypy keeps the narrowing it took from
    # the first assert and calls everything after the second one unreachable.
    pilot.serve_a_turn_wounded(6)
    after_one = (pilot.wounded, pilot.wounded_turns)
    pilot.serve_a_turn_wounded(7)
    after_two = (pilot.wounded, pilot.wounded_turns)

    assert after_one == (True, 1)
    assert after_two == (False, 0)


def test_the_turn_he_was_hurt_in_does_not_count() -> None:
    """Wounds land while a turn is closing and the squadron serves them at that close.

    Counting it had the debriefing promise four turns and the Air Wing show three.
    """
    pilot = Pilot("Lt Vega")
    pilot.wound(4, turn=5)

    pilot.serve_a_turn_wounded(5)  # the same turn, still being closed

    assert pilot.wounded_turns == 4


def test_recovery_never_runs_past_zero() -> None:
    pilot = Pilot("Lt Vega")
    pilot.wound(1, turn=5)
    for turn in range(6, 9):
        pilot.serve_a_turn_wounded(turn)
    assert pilot.wounded_turns == 0
    assert not pilot.wounded


def test_a_wound_lasts_between_one_and_four_turns() -> None:
    assert WOUNDED_TURNS == (1, 4)


def test_a_wound_is_worth_less_than_a_sortie_flown() -> None:
    """Being shot down must never be the better outcome."""
    from game.squadrons.experience import XP_MISSION_COMPLETE

    assert 0 < XP_WOUNDED < XP_MISSION_COMPLETE


def test_the_default_odds_are_a_third() -> None:
    assert Settings().live_pilots_wounded_chance == 35


def test_a_pilot_from_an_older_save_carries_no_wound() -> None:
    pilot = Pilot.__new__(Pilot)
    pilot.__setstate__({"name": "Lt Vega", "status": PilotStatus.Active})
    assert pilot.wounded_turns == 0
    assert pilot.wounded_on_turn == -1
    assert not pilot.wounded


def test_dying_of_the_wound_clears_the_counter() -> None:
    pilot = Pilot("Lt Vega")
    pilot.wound(4, turn=5)
    pilot.kill()
    assert pilot.status is PilotStatus.Dead
    assert pilot.wounded_turns == 0


# --- what the squadron does about it -----------------------------------------


def _squadron_with(roster: list[Pilot], limit: int = 4, turn: int = 6) -> Any:
    from game.squadrons.squadron import Squadron

    settings = Settings()
    settings.squadron_pilot_limit = limit
    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.current_roster = roster
    squadron.coalition = SimpleNamespace(game=SimpleNamespace(turn=turn))
    return squadron


def test_the_wounded_keep_their_place_on_the_books() -> None:
    """Otherwise the squadron backfills every casualty and overflows when they return."""
    fit, hurt = Pilot("Fit"), Pilot("Hurt")
    hurt.wound(2, turn=5)
    squadron = _squadron_with([fit, hurt], limit=4)

    assert squadron.wounded_pilots == [hurt]
    # Four seats, one flying and one in hospital: two to recruit into, not three.
    assert squadron._number_of_unfilled_pilot_slots == 2


def test_a_turn_of_the_squadron_is_a_turn_of_every_wound() -> None:
    hurt, nearly_better = Pilot("Hurt"), Pilot("Nearly")
    hurt.wound(3, turn=5)
    nearly_better.wound(1, turn=5)
    squadron = _squadron_with([Pilot("Fit"), hurt, nearly_better], turn=6)

    squadron.tend_the_wounded()

    assert hurt.wounded_turns == 2 and hurt.wounded
    assert not nearly_better.wounded
    assert squadron.wounded_pilots == [hurt]


def test_a_single_turn_is_not_pluralised() -> None:
    from game.squadrons.experience import turns_phrase

    assert turns_phrase(1) == "1 turn"
    assert turns_phrase(3) == "3 turns"


def test_the_ledger_names_the_rank_rather_than_reprs_it() -> None:
    """It was printing Rank(abbreviation='1stLt', name='First Lieutenant')."""
    from game.squadrons import xplog
    from game.squadrons.pilotranks import Rank

    log = xplog.XpLog(6)
    log.fate(
        SimpleNamespace(name="Lt Vega"),
        "VFA-2",
        "F/A-18C",
        Rank("1stLt", "First Lieutenant"),
        0.35,
        "wounded, out for 3 turns",
    )
    (line,) = log._lines
    assert "as 1stLt" in line
    assert "Rank(" not in line
    assert line.endswith("wounded, out for 3 turns")
