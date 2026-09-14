"""A repair message says what came back, not just its code name.

PYTHON and PRONGHORN are a factory and a SAM site, and the turn panel reported both
the same way. The name of the kind is already on the objective -- its __str__ is what
the map calls it -- so the message only had to say it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.theater.controlpoint import ControlPoint
from game.theater.player import Player


class _Tgo:
    """Only what the message needs: a name, a kind, and units under repair."""

    def __init__(self, name: str, kind: str, turns: int | None) -> None:
        self.obj_name = name
        self._kind = kind
        self.has_pending_repairs = turns is not None
        self.units = (
            [SimpleNamespace(alive=False, repair_turns_remaining=turns)]
            if turns is not None
            else []
        )

    def __str__(self) -> str:
        return self._kind


def _report(tgo: Any, blue: bool) -> list[str]:
    """ControlPoint is abstract, so the method is called unbound on a stand-in."""
    messages: list[str] = []
    cp = SimpleNamespace(
        captured=Player.BLUE if blue else Player.RED, runway_status=None
    )
    game = SimpleNamespace(message=messages.append)
    ControlPoint.report_repairs(cp, game, False, [tgo])  # type: ignore[arg-type]
    return messages


def test_a_finished_repair_names_the_kind() -> None:
    tgo = _Tgo("SUNBEAR", "Command Center", turns=None)
    assert _report(tgo, blue=True) == [
        "We have finished repairs at SUNBEAR (Command Center)"
    ]


def test_the_enemys_repairs_name_the_kind_too() -> None:
    tgo = _Tgo("PYTHON", "Factory", turns=None)
    assert _report(tgo, blue=False) == [
        "OPFOR has finished repairs at PYTHON (Factory)"
    ]


def test_a_repair_in_progress_names_the_kind_and_counts_one_turn() -> None:
    tgo = _Tgo("COYOTE", "AA Defense Site", turns=1)
    assert _report(tgo, blue=True) == [
        "Repairs at COYOTE (AA Defense Site) in progress, 1 turn remaining"
    ]


def test_several_turns_are_still_plural() -> None:
    tgo = _Tgo("SCARAB", "AA Defense Site", turns=3)
    assert _report(tgo, blue=True) == [
        "Repairs at SCARAB (AA Defense Site) in progress, 3 turns remaining"
    ]
