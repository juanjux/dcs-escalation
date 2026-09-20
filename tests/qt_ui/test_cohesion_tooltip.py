"""What the word under a squadron's task chip means.

The Air Wing row draws a cohesion band by name -- Friendly, Frosty -- and the name on
its own says nothing about what it is measuring. The tooltip says it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from qt_ui.models import AirWingModel


def _squadron(cohesion: Optional[float]) -> Any:
    return SimpleNamespace(cohesion=cohesion, settings=None)


def test_a_squadron_that_gets_on_says_so() -> None:
    tip = AirWingModel.tooltip_for_squadron(_squadron(6.5))

    assert tip is not None
    assert tip.startswith("Squadron cohesion: Friendly")
    assert "6.5" in tip


def test_a_squadron_that_does_not_says_that_too() -> None:
    tip = AirWingModel.tooltip_for_squadron(_squadron(3.5))

    assert tip is not None
    assert "Frosty" in tip


def test_the_neutral_band_has_no_tooltip_because_it_has_no_word() -> None:
    """A band nobody needs to think about draws nothing, and a tooltip explaining
    nothing is worse than none."""
    assert AirWingModel.tooltip_for_squadron(_squadron(5.0)) is None


def test_a_squadron_with_no_cohesion_at_all_has_none() -> None:
    assert AirWingModel.tooltip_for_squadron(_squadron(None)) is None
