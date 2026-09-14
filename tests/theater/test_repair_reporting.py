"""Unit tests for turn info-panel repair reporting (ControlPoint.report_repairs).

Covers the finished-vs-in-progress distinction and the ownfor-only in-progress
lines for both runways and repairable ground objects/buildings.
"""

from types import SimpleNamespace
from typing import Any

from game.theater.controlpoint import ControlPoint, RunwayStatus
from game.theater.player import Player


class _FakeGame:
    """Captures messages the way game.message would append them."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def message(self, title: str, text: str = "") -> None:
        self.messages.append(title)


def _unit(*, alive: bool, turns: Any) -> SimpleNamespace:
    return SimpleNamespace(alive=alive, repair_turns_remaining=turns)


class _FakeGroundObject:
    """Hashable stand-in for TheaterGroundObject (real TGOs are dict-keyable)."""

    def __init__(
        self, name: str, units: list[SimpleNamespace], kind: str = "AA Defense Site"
    ) -> None:
        self.obj_name = name
        self.units = units
        self._kind = kind

    def __str__(self) -> str:
        # The real one answers with the name of its category, which the message uses.
        return self._kind

    @property
    def has_pending_repairs(self) -> bool:
        # Mirror TheaterGroundObject.has_pending_repairs.
        return any(
            (not u.alive) and u.repair_turns_remaining is not None for u in self.units
        )


def _ground_object(name: str, units: list[SimpleNamespace]) -> _FakeGroundObject:
    return _FakeGroundObject(name, units)


def _control_point(captured: Player, runway_status: RunwayStatus) -> SimpleNamespace:
    return SimpleNamespace(captured=captured, runway_status=runway_status)


def _report(
    cp: SimpleNamespace, game: _FakeGame, runway_was_repairing: bool, gos: list
) -> None:
    # report_repairs only reads self.captured and self.runway_status, plus the
    # passed-in args, so a SimpleNamespace stands in for a full ControlPoint.
    # Message assertions below are substring-based and don't depend on str(self).
    ControlPoint.report_repairs(cp, game, runway_was_repairing, gos)


def test_max_pending_repair_turns_picks_slowest() -> None:
    units = [
        _unit(alive=False, turns=1),
        _unit(alive=False, turns=3),
        _unit(alive=True, turns=None),
    ]
    go = _ground_object("SAM-1", units)
    assert ControlPoint._max_pending_repair_turns(go) == 3


def test_max_pending_repair_turns_none_when_idle() -> None:
    go = _ground_object("SAM-1", [_unit(alive=True, turns=None)])
    assert ControlPoint._max_pending_repair_turns(go) is None


def test_finished_runway_reported_for_both_sides() -> None:
    for side in (Player.BLUE, Player.RED):
        game = _FakeGame()
        # Operational again (repair() result): not damaged, no turns remaining.
        cp = _control_point(
            side, RunwayStatus(damaged=False, repair_turns_remaining=None)
        )
        _report(cp, game, runway_was_repairing=True, gos=[])
        assert any("finished repairing the runway" in m for m in game.messages), side
        assert all("in progress" not in m for m in game.messages)


def test_in_progress_runway_reported_for_player_only() -> None:
    blue = _FakeGame()
    cp_blue = _control_point(
        Player.BLUE, RunwayStatus(damaged=True, repair_turns_remaining=2)
    )
    _report(cp_blue, blue, runway_was_repairing=True, gos={})
    assert any("in progress" in m and "2 turns remaining" in m for m in blue.messages)

    red = _FakeGame()
    cp_red = _control_point(
        Player.RED, RunwayStatus(damaged=True, repair_turns_remaining=2)
    )
    _report(cp_red, red, runway_was_repairing=True, gos={})
    assert red.messages == []  # enemy in-progress is not surfaced


def test_finished_ground_object_reported_for_both_sides() -> None:
    for side in (Player.BLUE, Player.RED):
        game = _FakeGame()
        cp = _control_point(side, RunwayStatus())
        # Object was repairing before; now all units alive -> finished.
        go = _ground_object("Ammo depot Alpha", [_unit(alive=True, turns=None)])
        _report(cp, game, runway_was_repairing=False, gos=[go])
        assert any(
            "finished repairs at Ammo depot Alpha" in m for m in game.messages
        ), side


def test_in_progress_ground_object_player_only() -> None:
    blue = _FakeGame()
    cp_blue = _control_point(Player.BLUE, RunwayStatus())
    go = _ground_object("SAM Bravo", [_unit(alive=False, turns=2)])
    _report(cp_blue, blue, runway_was_repairing=False, gos=[go])
    assert any(
        "Repairs at SAM Bravo (AA Defense Site) in progress" in m
        and "2 turns remaining" in m
        for m in blue.messages
    )

    red = _FakeGame()
    cp_red = _control_point(Player.RED, RunwayStatus())
    go_red = _ground_object("SAM Bravo", [_unit(alive=False, turns=2)])
    _report(cp_red, red, runway_was_repairing=False, gos=[go_red])
    assert red.messages == []  # enemy in-progress is not surfaced


def test_neutral_control_point_reports_nothing() -> None:
    game = _FakeGame()
    cp = _control_point(Player.NEUTRAL, RunwayStatus(damaged=False))
    go = _ground_object("SAM", [_unit(alive=True, turns=None)])
    _report(cp, game, runway_was_repairing=True, gos=[go])
    assert game.messages == []
