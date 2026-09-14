"""Whatever the pilot dialog shows, the planner can read.

An earlier draft gave it only the positive bonds inside a man's own squadron, on the
grounds that the rest was not actionable. That was wrong twice: a package is crewed out
of more than one squadron, so hiding the cross-squadron half hides the input to a
decision the planner is asked to make -- and an enemy is exactly as actionable as a
friend, because what you do about either is not put them in the same flight.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from dcs.unit import Skill

from game.agent import planner
from game.settings import Settings
from game.squadrons import friendship
from game.squadrons.pilot import Pilot


def _settings(**values: Any) -> Settings:
    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value
    for name, value in values.items():
        setattr(settings, name, value)
    return settings


def _squadron(settings: Settings, name: str, pilots: list[Pilot]) -> Any:
    from game.squadrons.squadron import Squadron

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.name = name
    squadron.nickname = None
    squadron.country = None
    squadron.current_roster = list(pilots)
    squadron.available_pilots = list(pilots)
    squadron.location = SimpleNamespace(name="Nellis")
    squadron.aircraft = "F/A-18C"
    squadron.id = name
    return squadron


def _wing(settings: Settings, *squadrons: Any) -> None:
    """Point every squadron at a wing that holds them all, as a coalition does."""
    wing_squadrons = list(squadrons)
    air_wing: Any = SimpleNamespace(
        iter_squadrons=lambda: iter(wing_squadrons),
    )

    def pilot_index() -> dict[Any, Any]:
        from game.squadrons.airwing import AirWing

        return AirWing.pilot_index(air_wing)

    air_wing.pilot_index = pilot_index
    coalition = SimpleNamespace(
        air_wing=air_wing,
        player=SimpleNamespace(is_blue=True, name="blue"),
        game=SimpleNamespace(turn=6),
        ato=SimpleNamespace(packages=[]),
    )
    for squadron in wing_squadrons:
        squadron.coalition = coalition


def _roster(*pilots: Pilot) -> Any:
    seats = list(pilots)
    return SimpleNamespace(
        iter_pilots=lambda: iter(seats),
        pilot_at=lambda index: seats[index],
        max_size=len(seats),
    )


NO_GAME: Any = SimpleNamespace()


@pytest.fixture
def crew(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Two squadrons at a base, a flight crewed out of one of them."""
    settings = _settings()
    lead, wingman = Pilot("Maj Harkness"), Pilot("Lt Bayliss")
    outsider = Pilot("Capt Ortega")
    for pilot in (lead, wingman, outsider):
        pilot.record.xp = 2000
    mine = _squadron(settings, "VFA-2", [lead, wingman])
    theirs = _squadron(settings, "VMFA-9", [outsider])
    _wing(settings, mine, theirs)

    flight = SimpleNamespace(
        id="f1", squadron=mine, roster=_roster(lead, wingman), package=None
    )
    monkeypatch.setattr(planner, "flight_for_side", lambda *a, **k: flight)
    monkeypatch.setattr(planner, "_reconcile_pool", lambda *a, **k: None)
    return SimpleNamespace(
        settings=settings,
        lead=lead,
        wingman=wingman,
        outsider=outsider,
        squadron=mine,
        other_squadron=theirs,
        flight=flight,
    )


def _seat(crew_view: dict[str, Any], index: int) -> dict[str, Any]:
    return crew_view["seats"][index]


# --- what a pilot carries --------------------------------------------------------


def test_a_pilot_is_named_by_an_id_rather_than_by_his_name(crew: Any) -> None:
    """Two men of the same name are two men, and a relationship has to say which."""
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    assert view["id"] == str(crew.lead.id)


def test_both_directions_are_reported(crew: Any) -> None:
    friendship.move(crew.lead, crew.wingman, 4.0)
    friendship.move(crew.wingman, crew.lead, 1.0)
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    bond = view["relationships"][0]
    assert bond["name"] == "Lt Bayliss"
    assert bond["towards"] == 9.0
    assert bond["from"] == 6.0
    assert bond["band"] == "Close"  # 9.0; Inseparable starts at 9.1


def test_a_man_who_has_an_opinion_of_him_shows_up_even_if_it_is_not_returned(
    crew: Any,
) -> None:
    """Being disliked is worth knowing about, and he does not have to have noticed."""
    friendship.move(crew.wingman, crew.lead, -4.0)
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    bond = view["relationships"][0]
    assert bond["towards"] == friendship.FRIENDSHIP_START
    assert bond["from"] == 1.0


def test_a_bond_reaches_across_squadrons(crew: Any) -> None:
    """A package is crewed out of more than one, so hiding these hides the input to a
    decision the planner is asked to make."""
    friendship.move(crew.lead, crew.outsider, 4.0)
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    bond = view["relationships"][0]
    assert bond["name"] == "Capt Ortega"
    assert bond["squadron"] == "VMFA-9"


def test_a_stranger_is_not_worth_a_line(crew: Any) -> None:
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    assert "relationships" not in view


def test_switched_off_none_of_it_is_there(crew: Any) -> None:
    crew.settings.friendship_enabled = False
    friendship.move(crew.lead, crew.wingman, 4.0)
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    assert "id" not in view
    assert "relationships" not in view


# --- what a formation carries ----------------------------------------------------


def test_a_crew_that_gets_on_says_so_and_says_what_it_is_worth(crew: Any) -> None:
    friendship.move(crew.lead, crew.wingman, 5.0)
    friendship.move(crew.wingman, crew.lead, 5.0)
    view = planner.flight_crew(NO_GAME, "blue", "f1")
    assert view["synergy"]["value"] == 10.0
    assert view["synergy"]["band"] == "Inseparable"
    assert view["synergy"]["flies_a_rung_better"] is True


def test_a_crew_of_strangers_flies_at_its_rank(crew: Any) -> None:
    view = planner.flight_crew(NO_GAME, "blue", "f1")
    assert view["synergy"]["flies_a_rung_better"] is False


def test_the_working_behind_the_rung_is_shown(crew: Any) -> None:
    """The planner can already see the answer in flies_at. This is why."""
    friendship.move(crew.lead, crew.wingman, 5.0)
    friendship.move(crew.wingman, crew.lead, 5.0)
    view = _seat(planner.flight_crew(NO_GAME, "blue", "f1"), 0)
    assert view["skill_breakdown"]["friendship"] == 1
    assert view["skill_breakdown"]["morale"] == 0
    assert view["skill_breakdown"]["rank"] == crew.squadron.pilot_skill(crew.lead).value
    assert view["flies_at"] != view["skill_breakdown"]["rank"]


def test_a_squadron_says_whether_it_is_a_crew_or_a_list_of_names(crew: Any) -> None:
    friendship.move(crew.lead, crew.wingman, 5.0)
    friendship.move(crew.wingman, crew.lead, 5.0)
    game: Any = SimpleNamespace(
        blue=crew.squadron.coalition,
        red=SimpleNamespace(player=SimpleNamespace(name="red")),
    )
    roster = planner.squadron_pilots(game, "blue", "VFA-2")
    assert roster["cohesion"] == {"value": 10.0, "band": "Inseparable"}
