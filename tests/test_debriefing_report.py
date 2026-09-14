"""Unit tests for the debriefing kept in the save.

A Debriefing is built from the mission's state file and its unit map and holds the
flights and theater objects of a mission that is over. The window built from it was the
only place the report lived, so closing Escalation lost it. The report here is the same
thing as plain data: small enough to ride in the save, and carrying nothing that belongs
to the finished mission -- including the live game, which is hung on it for the window
and dropped again on the way out.
"""

from __future__ import annotations

import pickle
from types import SimpleNamespace
from typing import Any

from game.debriefing import SideLossCounts
from game.debriefingreport import DebriefingReport
from game.squadrons.experience import PilotOutcomes
from game.theater.player import Player


class _Airframe:
    """A unit type stand-in.

    A plain class, not a SimpleNamespace: air losses are keyed by unit type, and
    SimpleNamespace defines __eq__ without __hash__, so it cannot be a dict key.
    """

    def __init__(self, display_name: str) -> None:
        self.display_name = display_name


def _counts(aircraft: int) -> SideLossCounts:
    return SideLossCounts(aircraft, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def _debriefing(**overrides: Any) -> Any:
    """A stand-in for the parts of Debriefing the report reads."""
    blue = Player.BLUE
    nothing: dict[Any, int] = {}
    base = dict(
        game=SimpleNamespace(
            settings=SimpleNamespace(ignore_non_combat_air_losses=False)
        ),
        player_country="USA",
        enemy_country="Russia",
        state_data=SimpleNamespace(mission_ended=True),
        pilot_outcomes=PilotOutcomes(),
        base_captures=[
            SimpleNamespace(
                control_point=SimpleNamespace(name="Al Taqaddum"),
                captured_by_player=Player.RED,
            )
        ],
        damaged_runways=[SimpleNamespace(name="Al Asad")],
        air_losses=SimpleNamespace(
            player=[],
            enemy=[],
            by_type=lambda player: (
                {_Airframe("F/A-18C Hornet"): 4} if player is blue else {}
            ),
        ),
        is_non_combat_loss=lambda loss: False,
        loss_counts=lambda player: _counts(4 if player is blue else 9),
        front_line_losses_by_type=lambda player: (
            {"M1A2 Abrams": 3} if player is blue else nothing
        ),
        motorpool_losses_by_type=lambda player: nothing,
        convoy_losses_by_type=lambda player: (
            nothing if player is blue else {"UAZ-469": 4}
        ),
        cargo_ship_losses_by_type=lambda player: nothing,
        airlift_losses_by_type=lambda player: nothing,
        ground_object_losses_by_type=lambda player: nothing,
        scenery_losses_by_type=lambda player: nothing,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _report(**overrides: Any) -> DebriefingReport:
    return DebriefingReport.from_debriefing(_debriefing(**overrides), turn=11)


def test_it_carries_the_turn_the_mission_was_flown_in() -> None:
    """Not the turn on the clock: results are processed, then the turn is passed."""
    assert _report().turn == 11


def test_the_air_losses_are_counted_by_airframe() -> None:
    report = _report()

    assert report.air_rows(Player.BLUE) == [("F/A-18C Hornet", 4, "")]
    assert report.air_rows(Player.RED) == []


def test_the_ground_losses_say_where_the_units_were_going() -> None:
    report = _report()

    assert report.ground_rows(Player.BLUE) == [("M1A2 Abrams", 3, "")]
    assert report.ground_rows(Player.RED) == [("UAZ-469 from convoy", 4, "")]


def test_write_offs_are_subtracted_and_said_out_loud() -> None:
    """Under the crashed-do-not-count doctrine, not quietly left in the figure."""
    hornet = _Airframe("F/A-18C Hornet")
    crashed = SimpleNamespace(flight=SimpleNamespace(unit_type=hornet))
    report = _report(
        game=SimpleNamespace(
            settings=SimpleNamespace(ignore_non_combat_air_losses=True)
        ),
        air_losses=SimpleNamespace(
            player=[crashed],
            enemy=[],
            by_type=lambda player: {hornet: 4} if player is Player.BLUE else {},
        ),
        is_non_combat_loss=lambda loss: loss is crashed,
    )

    name, count, note = report.air_rows(Player.BLUE)[0]
    assert (name, count) == ("F/A-18C Hornet", 3)
    assert "not counted" in note


def test_a_captured_base_remembers_who_took_it() -> None:
    capture = _report().base_captures[0]

    assert capture.control_point.name == "Al Taqaddum"
    assert capture.captured_by_player is Player.RED


def test_the_runways_are_named() -> None:
    assert [runway.name for runway in _report().damaged_runways] == ["Al Asad"]


def test_the_live_game_never_goes_into_the_save() -> None:
    """It is hung on the report for the window, and must not be pickled with it."""
    report = _report()
    report.game = object()

    restored = pickle.loads(pickle.dumps(report))

    assert restored.game is None
    assert restored.turn == 11
    assert restored.air_rows(Player.BLUE) == [("F/A-18C Hornet", 4, "")]


def test_a_side_the_report_never_heard_of_lost_nothing() -> None:
    """Rather than raising on a report written before a field existed."""
    empty = DebriefingReport(turn=3)

    assert empty.loss_counts(Player.BLUE).aircraft == 0
    assert empty.air_rows(Player.RED) == []
    assert empty.ground_rows(Player.RED) == []


def test_losing_the_report_never_costs_the_player_the_turn() -> None:
    """Recording it runs inside the results commit, so it swallows its own failures."""
    from game.game import Game

    game: Any = Game.__new__(Game)
    game.turn = 11
    game.debrief_history = []
    game.last_debriefing_report = None

    Game.record_debrief(game, SimpleNamespace())  # nothing it needs is there

    assert game.last_debriefing_report is None


def test_a_good_debriefing_is_kept() -> None:
    from game.game import Game

    game: Any = Game.__new__(Game)
    game.turn = 11
    game.debrief_history = []

    Game.record_debrief(game, _debriefing())

    assert game.last_debriefing_report is not None
    assert game.last_debriefing_report.turn == 11
