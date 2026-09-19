"""Asking for a squadron by name and getting that squadron.

``POST /packages`` takes a ``squadron_id``, and all it used to do with one was read
the aircraft off it. Two squadrons flying the same airframe both pass that filter, so
the planner took whichever was nearer the target: the package was built from the wrong
squadron, and the flights already counted against it were scrubbed later for having no
aircraft left. An id is an answer, not a hint.
"""

from __future__ import annotations

from typing import Any, cast

from game.squadrons.airwing import AirWing
from game.theater import Player


class _Squadron:
    """As much of one as the picker touches."""

    def __init__(
        self,
        name: str,
        player: Player = Player.BLUE,
        assignable: bool = True,
    ) -> None:
        self.name = name
        self.player = player
        self.assignable = assignable
        self.asked_about = 0

    def can_auto_assign_mission(self, *args: Any, **kwargs: Any) -> bool:
        self.asked_about += 1
        return self.assignable

    def __repr__(self) -> str:
        return f"<{self.name}>"


def _air_wing(player: Player = Player.BLUE) -> AirWing:
    wing = AirWing.__new__(AirWing)
    wing.player = player
    return wing


def _ask(wing: AirWing, squadron: Any) -> list[Any]:
    return wing.best_squadrons_for(
        cast(Any, None),
        cast(Any, "TASK"),
        2,
        heli=False,
        this_turn=True,
        preferred_squadron=squadron,
    )


def test_the_named_squadron_is_the_only_candidate() -> None:
    wanted = _Squadron("VMFA-251")

    assert _ask(_air_wing(), wanted) == [wanted]


def test_it_still_has_to_be_able_to_fly_the_mission() -> None:
    """Range, aircraft and the rest apply as they always did: naming a squadron
    forces the choice, not the physics."""
    grounded = _Squadron("VMFA-251", assignable=False)

    assert _ask(_air_wing(), grounded) == []
    assert grounded.asked_about == 1


def test_the_other_side_s_squadron_is_refused() -> None:
    theirs = _Squadron("23rd GvIAP", player=Player.RED)

    assert _ask(_air_wing(Player.BLUE), theirs) == []


# Naming nobody is the ordinary path and every other planner test goes through it:
# the base loop below this branch is untouched.
