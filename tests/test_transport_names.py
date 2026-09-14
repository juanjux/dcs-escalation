"""A convoy keeps its name while it travels, so no two may share one.

The counter behind the name is class state that no save carries -- the save holds the
generator, which is a class, and pickle stores a class by reference. A campaign loaded
with a convoy still on the road used to mint its name a second time for the next one.
"""

from __future__ import annotations

import pytest

from game.naming import NameGenerator, _highest_numbered


@pytest.fixture(autouse=True)
def counters_back_to_zero() -> None:
    NameGenerator.convoy_number = 0
    NameGenerator.cargo_ship_number = 0


def test_the_next_convoy_comes_after_the_ones_on_the_road() -> None:
    NameGenerator.resume_after(["Convoy 001", "Convoy 002"])
    assert NameGenerator.next_convoy_name() == "Convoy 003"


def test_a_reload_does_not_name_a_second_convoy_001() -> None:
    first = NameGenerator.next_convoy_name()
    second = NameGenerator.next_convoy_name()

    # The process ends and the campaign is loaded again, with both still travelling.
    NameGenerator.convoy_number = 0
    NameGenerator.resume_after([first, second])

    assert NameGenerator.next_convoy_name() not in {first, second}


def test_convoys_and_cargo_ships_are_counted_apart() -> None:
    NameGenerator.resume_after(["Convoy 007", "Cargo Ship 002"])
    assert NameGenerator.next_convoy_name() == "Convoy 008"
    assert NameGenerator.next_cargo_ship_name() == "Cargo Ship 003"


def test_a_campaign_with_nothing_on_the_road_starts_at_one() -> None:
    NameGenerator.resume_after([])
    assert NameGenerator.next_convoy_name() == "Convoy 001"


def test_the_counter_is_never_wound_backwards() -> None:
    NameGenerator.convoy_number = 9
    NameGenerator.resume_after(["Convoy 002"])
    assert NameGenerator.next_convoy_name() == "Convoy 010"


@pytest.mark.parametrize(
    "name",
    [
        "Convoy",  # no number
        "Convoy 001 Unit #1",  # a unit of one, not the transport
        "convoy 001",  # the prefix is part of the name
        "Cargo Ship 001",  # somebody else's counter
    ],
)
def test_only_a_transport_of_its_own_kind_counts(name: str) -> None:
    assert _highest_numbered([name], "Convoy") == 0


def test_a_loaded_campaign_heals_a_pair_that_already_shares_a_name() -> None:
    """The save nobody can fix by hand: two columns on the road, one name."""
    from types import SimpleNamespace

    from game.game import Game

    def transport(name: str) -> SimpleNamespace:
        return SimpleNamespace(name=name)

    first, second = transport("Convoy 001"), transport("Convoy 001")
    coalition = SimpleNamespace(
        transfers=SimpleNamespace(convoys=[first, second], cargo_ships=[])
    )
    campaign = SimpleNamespace(
        blue=coalition,
        red=SimpleNamespace(transfers=SimpleNamespace(convoys=[], cargo_ships=[])),
    )

    Game._resume_transport_names(campaign)  # type: ignore[arg-type]

    assert first.name == "Convoy 001"
    assert second.name == "Convoy 002"
    assert NameGenerator.next_convoy_name() == "Convoy 003"
