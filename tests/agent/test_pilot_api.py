"""The LLM can see and choose its pilots, the way the player can.

Parity gap found by the OPFOR agent: it could read a flight's uncrewed count and nothing
else -- no ranks, no experience, no wounds, and no way to put a chosen pilot in a seat.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.agent import planner
from game.dcs.skills import CADET_SKILL
from game.settings import Settings
from game.squadrons.pilot import Pilot


class _Rank:
    def __init__(self, abbreviation: str, name: str) -> None:
        self.abbreviation = abbreviation
        self.name = name


class _Squadron:
    def __init__(self, pilots: list[Pilot]) -> None:
        self.current_roster = pilots
        self.available_pilots = list(pilots)

    def pilot_skill(self, pilot: Pilot) -> Any:
        return CADET_SKILL

    def pilot_rank(self, pilot: Pilot) -> Any:
        return _Rank("2ndLt", "Second Lieutenant")

    def claim_pilot(self, pilot: Pilot) -> None:
        if pilot not in self.available_pilots:
            raise ValueError(f"Cannot assign {pilot} because they are not available")
        self.available_pilots.remove(pilot)

    def return_pilot(self, pilot: Pilot) -> None:
        self.available_pilots.append(pilot)

    def __str__(self) -> str:
        return "Capullos de Alien"


class _Roster:
    def __init__(self, squadron: _Squadron, size: int) -> None:
        self.squadron = squadron
        self.seats: list[Pilot | None] = [None] * size

    @property
    def max_size(self) -> int:
        return len(self.seats)

    def iter_pilots(self) -> Any:
        return iter(self.seats)

    def pilot_at(self, idx: int) -> Pilot | None:
        return self.seats[idx]

    def set_pilot(self, idx: int, pilot: Pilot | None) -> None:
        if pilot is not None:
            self.squadron.claim_pilot(pilot)
        if (current := self.seats[idx]) is not None:
            self.squadron.return_pilot(current)
        self.seats[idx] = pilot


#: The functions take a Game only to reach the ATO; these stubs never touch it.
NO_GAME: Any = SimpleNamespace()


@pytest.fixture
def flight(monkeypatch: pytest.MonkeyPatch) -> Any:
    squadron = _Squadron([Pilot("El Jefe"), Pilot("Yayo"), Pilot("Tercero")])
    flight = SimpleNamespace(id="f1", squadron=squadron, roster=_Roster(squadron, 2))
    monkeypatch.setattr(planner, "flight_for_side", lambda *a, **k: flight)
    return flight


def test_the_crew_lists_the_seats_and_who_is_free(flight: Any) -> None:
    crew = planner.flight_crew(NO_GAME, "red", "f1")
    assert [s["seat"] for s in crew["seats"]] == [0, 1]
    assert all(s.get("empty") for s in crew["seats"])
    assert {p["name"] for p in crew["available"]} == {"El Jefe", "Yayo", "Tercero"}
    assert crew["available"][0]["rank"] == "2ndLt"


def test_a_named_pilot_takes_a_seat(flight: Any) -> None:
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, "El Jefe")
    assert result.ok
    assert flight.roster.pilot_at(0).name == "El Jefe"
    assert "El Jefe" not in [p.name for p in flight.squadron.available_pilots]


def test_he_cannot_take_a_second_seat(flight: Any) -> None:
    """The whole point: one pilot, one place."""
    planner.set_flight_crew(NO_GAME, "red", "f1", 0, "El Jefe")
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 1, "El Jefe")
    assert not result.ok
    assert "already flying" in (result.error or "")


def test_a_seat_can_be_emptied(flight: Any) -> None:
    planner.set_flight_crew(NO_GAME, "red", "f1", 0, "El Jefe")
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, None)
    assert result.ok
    assert flight.roster.pilot_at(0) is None
    assert "El Jefe" in [p.name for p in flight.squadron.available_pilots]


def test_a_seat_that_does_not_exist_is_refused(flight: Any) -> None:
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 7, "El Jefe")
    assert not result.ok
    assert "seat 7" in (result.error or "")


def test_a_stranger_is_refused(flight: Any) -> None:
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, "Nadie")
    assert not result.ok
    assert "books" in (result.error or "")


# Two men of the same name in one squadron. The name generator does it -- the OPFOR
# agent found two 何秀梅 on the same roster -- and the API used to crew whichever came
# first, silently. A name that picks out more than one man is now refused, and the id
# always works.


@pytest.fixture
def homonyms(monkeypatch: pytest.MonkeyPatch) -> Any:
    squadron = _Squadron([Pilot("He Xiumei"), Pilot("He Xiumei"), Pilot("Solitario")])
    flight = SimpleNamespace(id="f1", squadron=squadron, roster=_Roster(squadron, 2))
    monkeypatch.setattr(planner, "flight_for_side", lambda *a, **k: flight)
    return flight


def test_a_shared_name_is_refused_rather_than_guessed(homonyms: Any) -> None:
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, "He Xiumei")
    assert not result.ok
    assert "2 pilots are called He Xiumei" in (result.error or "")
    assert homonyms.roster.pilot_at(0) is None
    # The error has to carry the ids, or the caller has no way to try again.
    for pilot in homonyms.squadron.current_roster[:2]:
        assert str(pilot.id) in (result.error or "")


def test_the_id_picks_the_man_out(homonyms: Any) -> None:
    wanted = homonyms.squadron.current_roster[1]
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, str(wanted.id))
    assert result.ok
    assert homonyms.roster.pilot_at(0) is wanted


def test_a_name_nobody_shares_still_works(homonyms: Any) -> None:
    """Compatibility: the id is preferred, the name is not taken away."""
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, "Solitario")
    assert result.ok
    assert homonyms.roster.pilot_at(0).name == "Solitario"


def test_the_seat_he_already_has_is_recognised_by_id(homonyms: Any) -> None:
    wanted = homonyms.squadron.current_roster[0]
    planner.set_flight_crew(NO_GAME, "red", "f1", 0, str(wanted.id))
    result = planner.set_flight_crew(NO_GAME, "red", "f1", 0, str(wanted.id))
    assert result.ok
    assert "already has seat 0" in (result.detail or "")


def test_every_setting_is_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mission durations were unreadable: the view was a hand-written subset."""
    from game.agent.views import _all_settings

    items = {item.key: item for item in _all_settings(Settings())}
    assert len(items) > 150
    assert items["desired_player_mission_duration"].value == 60
    assert items["desired_barcap_mission_duration"].page == "Campaign Doctrine"
    assert items["desired_tarcap_mission_duration"].label
