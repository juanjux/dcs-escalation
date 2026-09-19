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
        #: Settling fills every base's motorpool, which needs somewhere to look.
        self.controlpoints: list[object] = []


class MotorpoolSettings:
    motorpool_spawn_cap = 10
    motorpool_enabled = True


class Ato:
    def __init__(self) -> None:
        self.packages: list[object] = []


class Coalition:
    def __init__(self) -> None:
        self.ato = Ato()


class Campaign:
    """As much of a Game as fingerprinting one touches.

    Both sides included, empty: the campaign is settled before it is fingerprinted, and
    settling walks the flights of every package.
    """

    def __init__(self) -> None:
        self.theater = Theater()
        self.blue = Coalition()
        self.red = Coalition()
        self.settings = MotorpoolSettings()
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


def test_the_campaign_is_settled_before_it_is_fingerprinted(monkeypatch: Any) -> None:
    """Whatever the first look at the campaign builds, it is built before the print.

    A flight's plan is laid out on demand, and the first thing to ask for it is the map
    drawing itself -- so a fingerprint taken before that is of a campaign that stops
    existing a moment later, and closing an untouched campaign asks to save it.
    """
    settled = []
    monkeypatch.setattr(persistency, "settle", lambda game: settled.append(game))

    campaign = Campaign()
    persistency.remember_saved_state(campaign)  # type: ignore[arg-type]

    assert settled == [campaign]


def test_settling_fills_the_motorpools_the_map_would_have_filled() -> None:
    """A base's undeployed armour is not in the save; the map puts it there.

    Before this, loading a campaign and only looking at it left it different from its
    own save file, so closing asked whether to save something nobody had touched.
    """
    from game import persistency as under_test

    filled: list[object] = []

    class Populator:
        def __init__(self, game: Any) -> None:
            self.game = game

        def populate_control_points(self, control_points: Any) -> None:
            filled.append(control_points)

    import game.missiongenerator.motorpoolpopulator as motorpool

    original = motorpool.MotorpoolPopulator
    motorpool.MotorpoolPopulator = Populator  # type: ignore[assignment,misc]
    try:
        under_test.settle(Campaign())  # type: ignore[arg-type]
    finally:
        motorpool.MotorpoolPopulator = original  # type: ignore[misc]

    assert filled == [[]]
