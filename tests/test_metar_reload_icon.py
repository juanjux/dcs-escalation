"""The METAR refresh button draws an icon, so the icon has to be there.

It used to be the text glyph U+27F3, which fell back to whatever font had it: wrong
weight, and off the button's centre. A drawn icon fixes that and introduces a new way
to fail -- a missing file paints nothing at all, and an empty button looks like a bug
rather than a missing asset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qt_ui.widgets.commandbar import REFRESH_BUTTON_PX, REFRESH_ICON_PX
from qt_ui.widgets.conditions.QWeatherWidget import BUTTON_PX, ICON_PX

MISC = Path(__file__).resolve().parent.parent / "resources/ui/misc"

#: The character that used to be the button. Spelled by code point so this file
#: does not itself contain the thing it is banning.
GLYPH = chr(0x27F3)


@pytest.mark.parametrize("theme", sorted(p.name for p in MISC.iterdir() if p.is_dir()))
def test_every_theme_has_the_reload_icon(theme: str) -> None:
    icon = MISC / theme / "reload.png"
    assert icon.is_file(), f"{theme} has no reload.png"
    assert icon.stat().st_size > 0


def test_the_icon_is_inset_in_the_button() -> None:
    """A button that is all icon reads as a glyph again."""
    assert ICON_PX < BUTTON_PX


def test_no_refresh_button_is_drawn_as_a_glyph() -> None:
    """There are two of these buttons and only one was fixed.

    The command bar replaced the six boxes above the map and brought its own copy of
    the weather panel, refresh button included. Fixing the original left the visible
    one drawing U+27F3 -- which on the reporter's machine did not render as an arrow at
    all -- and the fix looked like it had done nothing. A grep, because there is no
    third way to find the next copy.
    """
    for module in (
        Path(__file__).resolve().parent.parent / "qt_ui/widgets/commandbar.py",
        Path(__file__).resolve().parent.parent
        / "qt_ui/widgets/conditions/QWeatherWidget.py",
    ):
        source = module.read_text(encoding="utf-8")
        assert GLYPH not in source, f"{module.name} still draws the glyph as text"


def test_the_command_bar_icon_is_inset_too() -> None:
    assert REFRESH_ICON_PX < REFRESH_BUTTON_PX
