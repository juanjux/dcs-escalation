"""A face per morale band, for the lists that have no room for the word.

The pilot selector shows seniority, rank and name, all of which look alike across a
squadron. How the man is holding up is the thing being chosen on, and it was the one
thing not there.
"""

from __future__ import annotations

from game.settings import Settings
from game.squadrons.morale import (
    MORALE_STATES,
    STATE_EMOJI,
    emoji_for,
    morale_state,
)


def test_every_band_has_a_face() -> None:
    assert {state.name for state in MORALE_STATES} == set(STATE_EMOJI)


def test_no_two_bands_share_a_face() -> None:
    assert len(set(STATE_EMOJI.values())) == len(STATE_EMOJI)


def test_the_face_follows_the_band_not_the_number() -> None:
    for morale in range(-30, 101):
        assert emoji_for(morale) == STATE_EMOJI[morale_state(morale).name]


def test_it_follows_a_campaign_that_moved_its_bands() -> None:
    """The bands are settings, so a face keyed by number would drift off them."""
    settings = Settings()
    settings.morale_state_confident = 30
    assert emoji_for(35, settings) == STATE_EMOJI["Confident"]
    assert emoji_for(35) == STATE_EMOJI["Shaken"], "unmoved, 35 is still Shaken"
