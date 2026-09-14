"""One colour per task on the chips the package and Air Wing lists paint.

The three families they used before painted CAS, Strike, DEAD and Armed Recon the
same, which is what the list is scanned for.
"""

from __future__ import annotations

from game.ato.flighttype import FlightType
from qt_ui.widgets.squadrondelegate import CHIP_TASKS, chip_colours


def test_every_task_has_its_own_chip() -> None:
    assert set(CHIP_TASKS) == set(FlightType)


def test_no_two_tasks_paint_the_same() -> None:
    inks = {chip_colours(task)[1].name() for task in FlightType}
    assert len(inks) == len(list(FlightType))


def test_the_fill_is_darker_than_the_ink() -> None:
    """A chip is dark ground with bright text, whatever the hue."""
    for task in FlightType:
        fill, ink = chip_colours(task)
        assert fill.lightness() < ink.lightness(), task
