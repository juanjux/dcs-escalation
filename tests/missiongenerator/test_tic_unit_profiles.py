"""TIC tunes a few unit types by name, and DCS renamed one of them.

2.9.29 folded the CurrentHill pack into core: those units keep the vanilla id but gain
a " [CH]" DisplayName suffix, and the vanilla file is gone. "IFV BMP-3" became
"IFV BMP-3 [CH]", missed the table, and the BMP-3 went back to spraying six rounds a
burst with a 100 mm gun. This is a tripwire on the shipped Lua: the behaviour itself was
checked against DCS's own interpreter, which no Python test can reach.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TIC = Path("resources/plugins/tic/TIC_v1.1.lua")


@pytest.fixture(scope="module")
def script() -> str:
    return TIC.read_text(encoding="utf8", errors="replace")


@pytest.mark.parametrize(
    "key", ['"IFV BMP-3"', '"APC BTR-80"', '"APC BTR-82A"', '"APC M113"']
)
def test_the_tuned_units_are_still_keyed_by_name(script: str, key: str) -> None:
    assert f"[{key}]" in script


def test_a_suffixed_display_name_falls_back_to_the_bare_one(script: str) -> None:
    assert 'profile[(displayName:gsub("%s*%[%u+%]$", ""))]' in script


def test_the_exact_name_still_wins(script: str) -> None:
    """The fallback is second: a table entry that matches in full must take priority."""
    lookup = script[script.index("local override = profile[displayName]") :][:200]
    assert lookup.index("profile[displayName]") < lookup.index("gsub")
