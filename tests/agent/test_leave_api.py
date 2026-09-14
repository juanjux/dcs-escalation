"""Answering a pilot who asked for leave, from the planner's side.

The window the player uses and the endpoint the LLM uses have to mean the same thing,
so both go through the squadron: he is granted at most what he asked for, a refusal
costs him, and neither can touch a pilot who never asked.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dcs.unit import Skill

from game.agent import planner, views
from game.settings import Settings
from game.squadrons import morale as morale_rules
from game.squadrons.pilot import Pilot


def _squadron(name: str, aircraft: int) -> Any:
    from game.squadrons.squadron import Squadron

    settings = Settings()
    settings.live_pilots_enabled = True
    settings.ai_pilot_levelling = True
    settings.player_skill = Skill.Good.value

    squadron: Any = Squadron.__new__(Squadron)
    squadron.settings = settings
    squadron.name = name
    squadron.nickname = None
    squadron.id = name
    squadron.country = None
    squadron.owned_aircraft = aircraft
    squadron.current_roster = []
    squadron.pilot_pool = []
    # Sending a man on leave now takes him off the list of who can be tasked.
    squadron.available_pilots = []
    squadron.coalition = SimpleNamespace(
        player=SimpleNamespace(is_blue=False, name="red"),
        game=SimpleNamespace(turn=6),
    )
    return squadron


def _game(squadron: Any) -> Any:
    red = SimpleNamespace(
        player=SimpleNamespace(is_blue=False, name="red"),
        air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron]),
    )
    blue = SimpleNamespace(
        player=SimpleNamespace(is_blue=True, name="blue"),
        air_wing=SimpleNamespace(iter_squadrons=lambda: []),
    )
    game = SimpleNamespace(
        blue=blue,
        red=red,
        turn=6,
        settings=squadron.settings,
        # The view helpers resolve a side through the game, the planner walks both
        # coalitions; the stub has to answer either way. Note the argument is a Player,
        # not a bool -- every member of that enum is truthy.
        coalition_for=lambda player: (
            blue if player is views.player_for_side("blue") else red
        ),
    )
    for coalition in (blue, red):
        coalition.game = game
    squadron.coalition = red
    return game


def _asking(squadron: Any, name: str, morale: int, asked: int) -> Pilot:
    pilot = Pilot(name)
    pilot.morale = morale
    pilot.wants_leave = True
    pilot.leave_turns_requested = asked
    squadron.current_roster.append(pilot)
    return pilot


def test_the_turn_context_carries_who_is_asking_and_what_it_would_cost() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    _asking(squadron, "Walker", morale=6, asked=3)
    _asking(squadron, "Byrd", morale=55, asked=1)

    requests = views.build_leave_requests(game, "red")

    assert [r.pilot_name for r in requests] == ["Walker", "Byrd"], "worst off first"
    assert requests[0].state == "Shattered"
    assert requests[0].asked_turns == 3
    assert requests[0].aircraft == 4
    # Byrd is also asking, so he is not counted as cover for Walker.
    assert requests[0].spare_pilots == 0


def test_he_is_granted_what_he_asked_for_and_never_more() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _asking(squadron, "Walker", morale=20, asked=2)

    result = planner.answer_leave_request(
        game, "red", "Lucky Tang", "Walker", grant=True, turns=99
    )

    assert result.ok
    assert pilot.on_leave
    assert pilot.leave_turns == 2, "he asked for two; ninety-nine is not on offer"
    assert not pilot.wants_leave


def test_fewer_turns_than_he_asked_for_is_allowed() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _asking(squadron, "Walker", morale=20, asked=4)

    assert planner.answer_leave_request(
        game, "red", "Lucky Tang", "Walker", grant=True, turns=1
    ).ok
    assert pilot.leave_turns == 1


def test_refusing_costs_him_and_ends_the_request() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _asking(squadron, "Walker", morale=40, asked=2)

    result = planner.answer_leave_request(
        game, "red", "Lucky Tang", "Walker", grant=False
    )

    assert result.ok
    assert not pilot.on_leave
    assert not pilot.wants_leave
    assert pilot.morale < 40
    assert [entry.reason for entry in pilot.morale_log] == ["leave refused"]


def test_a_pilot_who_did_not_ask_cannot_be_answered() -> None:
    """And the error says who *is* asking, so the next call can be right."""
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    _asking(squadron, "Walker", morale=20, asked=2)

    result = planner.answer_leave_request(
        game, "red", "Lucky Tang", "Nobody At All", grant=True
    )

    assert not result.ok
    assert result.error is not None
    assert "Walker" in result.error


def test_an_unknown_squadron_is_an_error_and_not_a_crash() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)

    result = planner.answer_leave_request(
        game, "red", "No Such Squadron", "Walker", grant=True
    )

    assert not result.ok


def test_leave_granted_here_runs_down_on_its_own() -> None:
    """The same as a granted request in the player's dialog, not an open-ended absence."""
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _asking(squadron, "Walker", morale=20, asked=2)
    planner.answer_leave_request(game, "red", "Lucky Tang", "Walker", grant=True)

    pilot.serve_a_turn_of_leave(6)  # the turn it was granted in does not count
    pilot.serve_a_turn_of_leave(7)
    pilot.serve_a_turn_of_leave(8)

    assert not pilot.on_leave
    assert pilot.turns_since_leave == 0


def test_nobody_asking_is_an_empty_list_and_not_an_error() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    squadron.current_roster.append(Pilot("Contented"))

    assert views.build_leave_requests(game, "red") == []
    assert morale_rules.MAX_LEAVE_TURNS >= 1  # the cap the endpoint honours


def _content(squadron: Any, name: str, morale: int) -> Pilot:
    """A pilot who is NOT asking for anything."""
    pilot = Pilot(name)
    pilot.morale = morale
    squadron.current_roster.append(pilot)
    squadron.available_pilots.append(pilot)
    return pilot


def test_a_pilot_who_never_asked_can_still_be_rested() -> None:
    """The men worth resting are often the ones who do not put a hand up."""
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _content(squadron, "Aksenov", morale=5)

    result = planner.set_pilot_leave(game, "red", "Lucky Tang", "Aksenov", turns=2)

    assert result.ok
    assert pilot.on_leave
    assert pilot.leave_turns == 2
    assert result.status == "On leave"
    assert result.leave_turns_remaining == 2
    assert pilot not in squadron.available_pilots, "he is off the roster now"


def test_leave_with_no_length_is_open_ended() -> None:
    """What the Air Wing button grants: out until he is called back."""
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _content(squadron, "Aksenov", morale=5)

    result = planner.set_pilot_leave(game, "red", "Lucky Tang", "Aksenov")

    assert result.ok
    assert pilot.on_leave
    assert result.leave_turns_remaining == 0


def test_calling_him_back_costs_him_morale() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _content(squadron, "Aksenov", morale=50)
    planner.set_pilot_leave(game, "red", "Lucky Tang", "Aksenov", turns=3)
    before = pilot.morale

    result = planner.set_pilot_leave(
        game, "red", "Lucky Tang", "Aksenov", on_leave=False
    )

    assert result.ok
    assert not pilot.on_leave
    assert result.status == "Active"
    assert pilot.morale < before, "being fetched back early is not free"


def test_only_an_active_pilot_can_be_sent_on_leave() -> None:
    """The squadron's own rule, the same one the Air Wing button obeys."""
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    pilot = _content(squadron, "Aksenov", morale=5)
    pilot.kill()

    result = planner.set_pilot_leave(game, "red", "Lucky Tang", "Aksenov", turns=2)

    assert not result.ok
    assert "active" in (result.error or "").lower()


def test_a_stranger_is_not_on_the_roster() -> None:
    squadron = _squadron("Lucky Tang", aircraft=4)
    game = _game(squadron)
    _content(squadron, "Aksenov", morale=5)

    result = planner.set_pilot_leave(game, "red", "Lucky Tang", "Nobody", turns=1)

    assert not result.ok
    assert "nobody called Nobody" in (result.error or "")
