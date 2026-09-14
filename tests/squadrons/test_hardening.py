"""What the bad weeks leave behind.

Morale says how a pilot is this week; hardening says what he has already survived, and
it only ever goes up. The rules worth pinning are the asymmetries: it is earned from the
bad bands only, it softens knocks and not good news, it helps him out of a wreck, and it
costs him the speed at which he gets attached to anybody new.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.unit import Skill

from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.squadrons import hardening
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot, PilotStatus

#: A knock big enough that the arithmetic below reads at a glance.
BAD_NEWS = morale_rules.MoraleEvent("test_bad_news", -30, "something awful")
GOOD_NEWS = morale_rules.MoraleEvent("test_good_news", 30, "something fine")


def _settings(**values: Any) -> Any:
    base = {
        "live_pilots_enabled": True,
        "morale_enabled": True,
        "hardening_enabled": True,
    }
    base.update(values)
    return SimpleNamespace(**base)


def _pilot(hardened: int = 0, morale: int = morale_rules.MORALE_START) -> Pilot:
    pilot = Pilot("Rambo")
    pilot.hardened = hardened
    pilot.morale = morale
    return pilot


# --- earning it ------------------------------------------------------------------


def test_a_pilot_starts_having_survived_nothing() -> None:
    assert Pilot("New").hardened == 0


def test_a_pilot_from_an_older_save_has_survived_nothing_either() -> None:
    pilot = Pilot.__new__(Pilot)
    pilot.__setstate__({"name": "Veteran", "status": PilotStatus.Active})
    assert pilot.hardened == 0


def test_each_bad_band_is_worth_its_own_turn() -> None:
    settings = _settings()
    assert hardening.gain_for(20, settings) == 1  # Shaken
    assert hardening.gain_for(5, settings) == 2  # Shattered
    assert hardening.gain_for(-10, settings) == 3  # Broken


def test_a_good_week_teaches_him_nothing_about_a_bad_one() -> None:
    settings = _settings()
    assert hardening.gain_for(50, settings) == 0  # Normal
    assert hardening.gain_for(90, settings) == 0  # Triumphant


def test_it_goes_up_and_never_down() -> None:
    settings = _settings()
    pilot = _pilot()
    assert hardening.harden(pilot, 5, settings) == 2
    assert pilot.hardened == 2
    # A quiet turn is a rest, not an education -- and it takes nothing back.
    assert hardening.harden(pilot, 90, settings) == 0
    assert pilot.hardened == 2


def test_a_hospital_bed_is_not_a_bad_place_in_the_sense_that_matters() -> None:
    """He may be lower there than anywhere. This is earned by turning up."""
    settings = _settings()
    hurt = _pilot(morale=-10)
    hurt.wound(3, turn=1)
    assert hardening.harden(hurt, -10, settings) == 0

    away = _pilot(morale=-10)
    away.send_on_leave(2, turn=1)
    assert hardening.harden(away, -10, settings) == 0


def test_it_stops_at_the_top_of_the_ruler() -> None:
    settings = _settings(hardening_max=5)
    pilot = _pilot(hardened=4)
    assert hardening.harden(pilot, -10, settings) == 1
    assert pilot.hardened == 5


def test_the_squadron_hardens_him_on_the_state_he_spent_the_turn_in(
    monkeypatch: Any,
) -> None:
    """Wired into the turn, and reading the figure he arrived with -- the drift lifts a
    man who is merely low, so asking afterwards would read the wrong band."""
    from game.squadrons.squadron import Squadron

    squadron: Any = Squadron.__new__(Squadron)
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value
    squadron.settings = settings
    squadron.coalition = SimpleNamespace(
        player=SimpleNamespace(is_blue=True), game=SimpleNamespace(turn=6)
    )
    squadron.country = None
    squadron.name = "Zero Company"
    squadron.nickname = None
    squadron.available_pilots = []

    pilot = _pilot(morale=5)  # Shattered on arrival
    squadron.current_roster = [pilot]
    squadron.tend_morale(6)

    assert pilot.hardened == 2
    assert pilot.morale > 5  # the drift lifted him, after he was counted


# --- what it is worth ------------------------------------------------------------


def test_a_knock_lands_lighter_on_a_man_who_has_had_a_few() -> None:
    """Juanjo's worked example: 30 of 40 is 60% off, so a -30 arrives as -12."""
    settings = _settings()
    relief = hardening.morale_relief(30, settings)
    assert round(relief, 6) == 0.6
    assert morale_rules.apply(50, BAD_NEWS, CADET_SKILL, None, relief) == 38


def test_the_ruler_is_priced_from_end_to_end() -> None:
    settings = _settings()
    assert hardening.morale_relief(0, settings) == 0.0
    assert round(hardening.morale_relief(20, settings), 6) == 0.4
    assert round(hardening.morale_relief(40, settings), 6) == 0.8


def test_good_news_is_not_softened_by_anything() -> None:
    """Nobody is too hardened to be pleased about a promotion, which is the same
    asymmetry rank already has."""
    assert morale_rules.apply(50, GOOD_NEWS, CADET_SKILL, None, 0.8) == 80


def test_a_knock_always_costs_something() -> None:
    """Even at the very top of both ladders. The floor is the rule, not a rounding
    guard."""
    assert morale_rules.apply(50, BAD_NEWS, Skill.Excellent, None, 1.0) == 49


def test_it_multiplies_with_rank_rather_than_replacing_it() -> None:
    """Two separate reasons the same news lands lighter: armour he was given and
    armour he earned."""
    rank_only = morale_rules.apply(50, BAD_NEWS, Skill.Excellent)
    both = morale_rules.apply(50, BAD_NEWS, Skill.Excellent, None, 0.5)
    assert 50 > both > rank_only


def test_having_been_shot_at_before_helps_when_it_happens_again() -> None:
    settings = _settings()
    assert hardening.survival_bonus(0, settings) == 0.0
    assert round(hardening.survival_bonus(20, settings), 6) == 0.10
    assert round(hardening.survival_bonus(40, settings), 6) == 0.20


# --- what it costs ---------------------------------------------------------------


def test_he_is_slower_to_think_well_of_anybody() -> None:
    settings = _settings()
    assert hardening.feels(_pilot(0), 2.0, settings) == 2.0
    assert round(hardening.feels(_pilot(20), 2.0, settings), 6) == 1.4
    assert round(hardening.feels(_pilot(40), 2.0, settings), 6) == 0.8


def test_a_thick_skin_is_thick_both_ways() -> None:
    """He is slower to take offence as well: one skin, and it does not know which way
    the news is going."""
    settings = _settings()
    assert round(hardening.feels(_pilot(40), -3.0, settings), 6) == -1.2
    assert round(hardening.feels(_pilot(20), -3.0, settings), 6) == -2.1


def test_it_is_about_him_and_not_about_what_anybody_thinks_of_him() -> None:
    """The damping is applied per mover, so the squadron can adore the hard old
    sergeant while the sergeant keeps his distance."""
    settings = _settings()
    sergeant, rookie = _pilot(40), _pilot(0)
    assert hardening.feels(sergeant, 2.0, settings) < 2.0
    assert hardening.feels(rookie, 2.0, settings) == 2.0


# --- switched off ----------------------------------------------------------------


def test_switched_off_nobody_hardens_and_nothing_changes() -> None:
    settings = _settings(hardening_enabled=False)
    pilot = _pilot(hardened=40)
    assert hardening.harden(pilot, -10, settings) == 0
    assert hardening.morale_relief(40, settings) == 0.0
    assert hardening.survival_bonus(40, settings) == 0.0
    assert hardening.feels(pilot, 2.0, settings) == 2.0


def test_without_morale_there_is_nothing_to_be_hardened_by() -> None:
    settings = _settings(morale_enabled=False)
    assert hardening.gain_for(-10, settings) == 0
    assert hardening.morale_relief(40, settings) == 0.0
