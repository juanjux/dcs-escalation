"""Filling a flight tries to keep a crew together.

The player's preference about who flies still decides who is eligible; friendship only
orders the men who already matched it. Everything here is about not disturbing that,
because crewing is the one part of the turn that must never surprise anybody.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.unit import Skill

from game.settings import AutoAtoBehavior, Settings
from game.squadrons import friendship
from game.squadrons.pilot import Pilot
from game.theater.player import Player


def _squadron(settings: Settings, pilots: list[Pilot], blue: bool = True) -> Any:
    from game.squadrons.squadron import Squadron

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.coalition = SimpleNamespace(
        player=Player.BLUE if blue else Player.RED,
        game=SimpleNamespace(turn=6),
    )
    squadron.available_pilots = list(pilots)
    squadron.current_roster = list(pilots)
    # The first seat is chosen on rank, so the fake has to be able to answer for one.
    # base_skill is a property and comes off the settings above.
    squadron.country = SimpleNamespace(name="USA")
    return squadron


def _settings(**values: Any) -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value
    settings.enable_squadron_pilot_limits = False
    for name, value in values.items():
        setattr(settings, name, value)
    return settings


def test_the_second_seat_goes_to_somebody_the_first_gets_on_with() -> None:
    lead, friend, stranger = Pilot("Lead"), Pilot("Friend"), Pilot("Stranger")
    friendship.move(lead, friend, 4.0)
    friendship.move(friend, lead, 4.0)
    squadron = _squadron(_settings(), [friend, stranger])

    assert squadron.claim_available_pilot([lead]) is friend
    assert friend not in squadron.available_pilots


def test_a_man_the_crew_cannot_stand_is_the_last_one_taken() -> None:
    lead, enemy, stranger = Pilot("Lead"), Pilot("Enemy"), Pilot("Stranger")
    friendship.move(lead, enemy, -4.0)
    friendship.move(enemy, lead, -4.0)
    squadron = _squadron(_settings(), [enemy, stranger])

    assert squadron.claim_available_pilot([lead]) is stranger


def _veteran(name: str, xp: int) -> Pilot:
    pilot = Pilot(name)
    pilot.record.xp = xp
    return pilot


def test_the_first_seat_goes_to_the_senior_man() -> None:
    """Seat zero is the flight lead: DCS takes the group's options from the man in
    front, and the friendship rules weigh what each wingman thinks of him double."""
    cadet, major = Pilot("Cadet"), _veteran("Major", 8000)
    squadron = _squadron(_settings(), [major, cadet])

    assert squadron.claim_available_pilot() is major
    assert major not in squadron.available_pilots


def test_the_first_seat_is_filled_the_way_it_always_was_when_nobody_outranks() -> None:
    """Rank only gets to break the tie it can see. Two men on the same rung leave the
    list deciding, exactly as it did before any of this existed."""
    first, second = Pilot("First"), Pilot("Second")
    squadron = _squadron(_settings(), [first, second])
    assert squadron.claim_available_pilot() is second  # off the end, as ever


def test_rank_does_not_choose_the_lead_with_live_pilots_off() -> None:
    """rank_order is constant then, so there is no rank to lead by and the list has
    to decide as it always did."""
    cadet, major = Pilot("Cadet"), _veteran("Major", 8000)
    squadron = _squadron(_settings(live_pilots_enabled=False), [major, cadet])
    assert squadron.claim_available_pilot() is cadet


def test_the_lead_is_the_senior_man_the_preference_allows() -> None:
    """Rank orders the men who matched the player's preference; it does not overrule
    it, any more than friendship does."""
    human, major = Pilot("Human", player=True), _veteran("Major", 8000)
    settings = _settings(auto_ato_behavior=AutoAtoBehavior.Prefer)
    squadron = _squadron(settings, [major, human])
    assert squadron.claim_available_pilot() is human


def test_the_seats_after_the_lead_are_still_chosen_on_friendship() -> None:
    """Rank picks the man in front and stops there: a crew is grouped around him, not
    filled by seniority down the roster."""
    lead = Pilot("Lead")
    friend, major = Pilot("Friend"), _veteran("Major", 8000)
    friendship.move(lead, friend, 4.0)
    friendship.move(friend, lead, 4.0)
    squadron = _squadron(_settings(), [major, friend])

    assert squadron.claim_available_pilot([lead]) is friend


def test_switched_off_friendship_does_not_touch_the_order() -> None:
    lead, friend, stranger = Pilot("Lead"), Pilot("Friend"), Pilot("Stranger")
    friendship.move(lead, friend, 4.0)
    friendship.move(friend, lead, 4.0)
    squadron = _squadron(_settings(friendship_enabled=False), [friend, stranger])
    assert squadron.claim_available_pilot([lead]) is stranger


def test_a_crew_of_strangers_is_no_reason_to_reorder_anything() -> None:
    first, second = Pilot("First"), Pilot("Second")
    squadron = _squadron(_settings(), [first, second])
    assert squadron.claim_available_pilot([Pilot("Lead")]) is second


def test_the_preference_about_players_still_decides_who_is_eligible() -> None:
    """Friendship orders the men who matched it. It does not get to overrule it."""
    lead = Pilot("Lead")
    human = Pilot("Human", player=True)
    friend = Pilot("Friend")
    friendship.move(lead, friend, 4.0)
    friendship.move(friend, lead, 4.0)

    settings = _settings(auto_ato_behavior=AutoAtoBehavior.Prefer)
    squadron = _squadron(settings, [friend, human])
    assert squadron.claim_available_pilot([lead]) is human


def test_red_groups_its_crews_too() -> None:
    """Red goes straight to the pool, so without this it would be the only side whose
    pilots never get to know each other beyond the drift."""
    lead, friend, stranger = Pilot("Lead"), Pilot("Friend"), Pilot("Stranger")
    friendship.move(lead, friend, 4.0)
    friendship.move(friend, lead, 4.0)
    squadron = _squadron(_settings(), [friend, stranger], blue=False)
    assert squadron.claim_available_pilot([lead]) is friend
