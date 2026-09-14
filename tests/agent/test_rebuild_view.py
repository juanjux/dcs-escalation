"""What the planner is told about work in progress on a site.

A site being repaired reads like a destroyed one from the outside -- no composition, and
an enemy site with nothing alive is dropped from the target list entirely -- so the
countdown is the only thing that says it is coming back. The half that used to be silent
is the PARTIAL repair: the serializer stopped looking the moment it found one unit
standing, on the grounds that a site with something alive is damaged rather than under
construction. True, and beside the point: a battery that is firing today and gets its
second launcher back next turn is a battery you plan against twice.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.agent import views


def _unit(alive: bool, repair_turns: Any = None) -> Any:
    return SimpleNamespace(alive=alive, repair_turns_remaining=repair_turns)


def _tgo(name: str, *units: Any) -> Any:
    return SimpleNamespace(
        name=name,
        units=list(units),
        groups=[SimpleNamespace(name=f"{name} (SAM)")],
    )


def test_a_site_rebuilt_from_nothing_reports_its_countdown() -> None:
    view = views._rebuild_state(_tgo("COYOTE", _unit(False, 3), _unit(False, 2)))
    assert view is not None
    assert view.turns_remaining == 3  # the last of it, not the first
    assert view.units_repairing == 2
    assert view.units_alive == 0


def test_a_partial_repair_is_reported_too() -> None:
    """SCARAB: five launchers firing and three more coming back in three turns. This
    was invisible, because the serializer bailed on the first live unit."""
    view = views._rebuild_state(
        _tgo("SCARAB", _unit(True), _unit(True), _unit(False, 3), _unit(False, 1))
    )
    assert view is not None
    assert view.turns_remaining == 3
    assert view.units_repairing == 2
    assert view.units_alive == 2


def test_units_alive_is_what_tells_the_two_apart() -> None:
    """A planner reads one number to know whether it is looking at a wreck with a
    countdown or a site that is shooting at it today."""
    wreck = views._rebuild_state(_tgo("COYOTE", _unit(False, 2)))
    fighting = views._rebuild_state(_tgo("SCARAB", _unit(True), _unit(False, 2)))
    assert wreck is not None and fighting is not None
    assert wreck.units_alive == 0
    assert fighting.units_alive == 1


def test_a_site_with_no_work_on_it_reports_nothing() -> None:
    assert views._rebuild_state(_tgo("MASTIFF", _unit(True), _unit(True))) is None


def test_a_wreck_nobody_is_repairing_reports_nothing() -> None:
    """Dead with no countdown is destroyed, not under construction -- and saying
    otherwise would promise the planner a site that is never coming back."""
    assert views._rebuild_state(_tgo("GONE", _unit(False), _unit(False))) is None


def test_a_site_with_no_units_at_all_does_not_raise() -> None:
    assert views._rebuild_state(_tgo("EMPTY")) is None
