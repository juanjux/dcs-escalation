"""An enemy base: what is there, and what a strike would have to get through.

The intel tab grouped aircraft by DCS task constants -- CAS, AFAC, GroundAttack --
and left the air defences out entirely, which is the one thing that decides whether
a strike on the base is worth planning.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - no Qt on this machine
        pytest.skip(f"PySide6 unavailable: {exc}")
    yield QApplication.instance() or QApplication([])


def _unit(name: str, alive: bool = True) -> Any:
    return SimpleNamespace(
        alive=alive, unit_type=SimpleNamespace(display_name=name) if name else None
    )


def _site(code: str, units: list[Any], dead: bool = False) -> Any:
    return SimpleNamespace(
        category="aa",
        obj_name=code,
        is_dead=dead,
        units=units,
        alive_unit_count=sum(1 for unit in units if unit.alive),
    )


def _cp(objectives: list[Any]) -> Any:
    return cast(Any, SimpleNamespace(connected_objectives=objectives))


def test_a_dead_site_is_not_counted(qt_app: Any) -> None:
    """A site whose launchers are gone is not a reason to send SEAD."""
    from qt_ui.windows.basemenu.header import air_defences

    alive = _site("ALBATROSS", [_unit("SA-15 Tor")])
    dead = _site("PYTHON", [_unit("SA-11 Buk TEL", alive=False)], dead=True)
    assert air_defences(_cp([alive, dead])) == [alive]


def test_only_air_defence_objectives_are_counted(qt_app: Any) -> None:
    from qt_ui.windows.basemenu.header import air_defences

    sam = _site("ALBATROSS", [_unit("SA-15 Tor")])
    factory = SimpleNamespace(category="factory", is_dead=False)
    assert air_defences(_cp([sam, factory])) == [sam]


def test_the_biggest_site_comes_first(qt_app: Any) -> None:
    """The one that takes the most killing is the one that shapes the package."""
    from qt_ui.windows.basemenu.header import air_defences

    small = _site("PYTHON", [_unit("SA-15 Tor")])
    big = _site("ALBATROSS", [_unit("SA-11 Buk TEL") for _ in range(5)])
    assert air_defences(_cp([small, big])) == [big, small]


def test_a_site_is_named_for_what_it_shoots_with(qt_app: Any) -> None:
    """The objective's own name is a code word: it says where, never what."""
    from qt_ui.windows.basemenu.header import site_name

    site = _site(
        "ALBATROSS",
        [
            _unit("SA-11 Buk TEL"),
            _unit("SA-11 Buk TEL"),
            _unit("SA-11 Buk TEL"),
            _unit("SA-11 Buk SR"),
            _unit("SA-11 Buk CC"),
        ],
    )
    assert site_name(site) == "SA-11 Buk TEL"


def test_dead_launchers_do_not_name_the_site(qt_app: Any) -> None:
    """What is left standing is what the strike still has to deal with."""
    from qt_ui.windows.basemenu.header import site_name

    site = _site(
        "ALBATROSS",
        [
            _unit("SA-11 Buk TEL", alive=False),
            _unit("SA-11 Buk TEL", alive=False),
            _unit("SA-11 Buk SR"),
        ],
    )
    assert site_name(site) == "SA-11 Buk SR"


def test_a_site_of_nothing_recognisable_keeps_its_code_name(qt_app: Any) -> None:
    """Better a code word that matches the map than a blank."""
    from qt_ui.windows.basemenu.header import site_name

    assert site_name(_site("ALBATROSS", [])) == "ALBATROSS"


def test_the_intel_tab_counts_each_kind_of_site(qt_app: Any) -> None:
    from qt_ui.windows.basemenu.intel.QIntelInfo import QIntelInfo

    tor_one = _site("PYTHON", [_unit("SA-15 Tor")])
    tor_two = _site("COBRA", [_unit("SA-15 Tor")])
    buk = _site("ALBATROSS", [_unit("SA-11 Buk TEL") for _ in range(4)])

    intel = cast(Any, QIntelInfo.__new__(QIntelInfo))
    intel.cp = _cp([tor_one, tor_two, buk])
    assert intel.air_defence_lines() == {"SA-15 Tor": 2, "SA-11 Buk TEL": 1}
