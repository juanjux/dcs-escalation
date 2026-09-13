"""What the LLM can see about one pilot.

The roster is built for every pilot of every squadron on every turn, so it carries
figures. The whole of a man -- every kill, everything that moved him -- is a call of
its own.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from game.agent import planner
from game.squadrons.pilot import KilledBy, PilotRecord


def _record() -> PilotRecord:
    record = PilotRecord()
    record.missions_flown = 5
    record.missions_completed = 4
    record.aircraft_lost = 1
    record.survived_losses = 1
    record.wounds = 1
    record.turns_in_hospital = 2
    record.last_wound_turn = 9
    record.last_wound_turns = 2
    record.leaves_taken = 1
    record.leave_turns_total = 3
    record.note_kill(True, "JF-17", "", 11, "AIM-120C")
    record.note_kill(False, "SA-15 Tor", "Air defence", 11, "AGM-88C")
    return record


def test_the_roster_carries_the_figures() -> None:
    figures = planner._record_figures(_record())
    assert figures["missions_completed"] == 4
    assert figures["air_kills"] == 1
    assert figures["ground_kills"] == 1
    assert figures["wounds"] == 1
    assert figures["leaves_taken"] == 1


def test_the_roster_says_nothing_about_what_has_not_happened() -> None:
    """A roster of thirty men carrying eight zeroes each is a page of nothing."""
    assert planner._record_figures(PilotRecord()) == {}


def test_a_dead_man_is_named_with_who_got_him() -> None:
    record = PilotRecord()
    record.killed_by = KilledBy(
        pilot_name="Ali Hassan", aircraft="JF-17", weapon="PL-12", turn=11
    )
    figures = planner._record_figures(record)
    assert figures["killed_by"] == "Ali Hassan (JF-17) with PL-12"
    assert figures["killed_on_turn"] == 11


def test_the_record_is_asked_for_by_name(monkeypatch: pytest.MonkeyPatch) -> None:

    class Squadron:
        id = "sq-1"
        name = "VMA-223"

        def __init__(self, roster: list[Any]) -> None:
            self.current_roster = roster

        def __str__(self) -> str:
            return self.name

    class Game:
        def __init__(self, squadron: Any) -> None:
            wing = type("Wing", (), {"iter_squadrons": lambda self: iter([squadron])})()
            player = type("Player", (), {"name": "red"})()
            coalition = type("Coalition", (), {"air_wing": wing, "player": player})()
            blue_player = type("Player", (), {"name": "blue"})()
            self.red = coalition
            self.blue = type(
                "Coalition",
                (),
                {
                    "air_wing": type(
                        "Wing", (), {"iter_squadrons": lambda self: iter([])}
                    )(),
                    "player": blue_player,
                },
            )()

    pilot = type("Pilot", (), {"name": "Solis", "id": "p1"})()
    game = Game(Squadron([pilot]))

    seen: list[Any] = []

    def note(_squadron: Any, found: Any) -> dict[str, Any]:
        seen.append(found)
        return {}

    monkeypatch.setattr(planner, "_pilot_record_view", note)
    planner.pilot_record(cast(Any, game), "red", "sq-1", "Solis")
    assert seen == [pilot]

    # And it says who it does know when it does not know the name asked for.
    with pytest.raises(ValueError, match="Solis"):
        planner.pilot_record(cast(Any, game), "red", "sq-1", "Nobody")
