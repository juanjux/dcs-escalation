"""Whether closing the window would lose anything.

Quitting asked "would you like to save?" every time, including after a save and
including when the campaign had not been touched at all. A campaign of a few hundred
objectives pickles in about fifty milliseconds and to the same bytes for the same
state, so the question has an exact answer and it is cheap to ask.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from game import persistency


class Theater:
    """The landmap is unloaded before a save and put back after; both are kept here."""

    def __init__(self) -> None:
        self.landmap = "the map, which no save carries"


class Campaign:
    """As much of a Game as a fingerprint touches."""

    def __init__(self) -> None:
        self.theater = Theater()
        self.turn = 1
        self.budget = 1000


@pytest.fixture(autouse=True)
def nothing_remembered() -> Iterator[None]:
    persistency._saved_signature = None
    yield
    persistency._saved_signature = None


def test_a_campaign_that_was_never_saved_has_everything_to_lose() -> None:
    assert persistency.has_unsaved_changes(Campaign()) is True  # type: ignore[arg-type]


def test_nothing_open_is_nothing_to_save() -> None:
    assert persistency.has_unsaved_changes(None) is False


def test_a_campaign_straight_off_its_save_is_unchanged() -> None:
    campaign = Campaign()
    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]

    assert persistency.has_unsaved_changes(campaign) is False  # type: ignore[arg-type]


def test_anything_moved_since_the_save_counts() -> None:
    campaign = Campaign()
    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]

    campaign.budget -= 250

    assert persistency.has_unsaved_changes(campaign) is True  # type: ignore[arg-type]


def test_saving_again_settles_it() -> None:
    campaign = Campaign()
    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]
    campaign.turn += 1
    assert persistency.has_unsaved_changes(campaign) is True  # type: ignore[arg-type]

    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]

    assert persistency.has_unsaved_changes(campaign) is False  # type: ignore[arg-type]


def test_the_landmap_is_put_back_after_fingerprinting() -> None:
    # It is dropped before a save and restored after, and this does the same. Losing it
    # would leave the campaign unable to say where the land is.
    campaign = Campaign()
    persistency.game_signature(campaign)  # type: ignore[arg-type]

    assert campaign.theater.landmap == "the map, which no save carries"


def test_the_same_state_fingerprints_the_same_twice() -> None:
    campaign = Campaign()

    first = persistency.game_signature(campaign)  # type: ignore[arg-type]
    second = persistency.game_signature(campaign)  # type: ignore[arg-type]

    assert first == second


def test_a_campaign_that_cannot_be_fingerprinted_is_treated_as_unsaved(
    monkeypatch: Any,
) -> None:
    campaign = Campaign()
    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]

    def no(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("not picklable")

    monkeypatch.setattr(persistency.pickle, "dumps", no)

    # Being asked once too often costs a keystroke; the other mistake costs the campaign.
    assert persistency.has_unsaved_changes(campaign) is True  # type: ignore[arg-type]
