"""The base menu says what the base is and whether it works, before anything else.

The window used to state neither: the kind was inferred from which tabs turned up,
the owner from the colours, and the runway state was the tail of a paragraph of rich
text that also held the aircraft and the ground units.

The pills say what is *not* there as well as what is. A base with no ammunition and no
factory looked exactly like a base whose ammunition and factory the window had
forgotten to mention, and the difference matters: one is a base you can still frag a
strike from, the other is one you cannot reinforce.
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


def _cp(
    runway: Any = None,
    depots: tuple[int, int] = (0, 0),
    factory: bool = False,
    has_runway: bool = True,
    helipads: int = 0,
    limit: int = 15,
) -> Any:
    alive, total = depots
    return SimpleNamespace(
        name="Creech",
        runway_status=runway,
        runway_is_destroyable=has_runway,
        captured=SimpleNamespace(is_blue=True),
        # The control point publishes these; the header does not re-derive them,
        # because the game counts warehouses rather than objectives and the two
        # disagree.
        active_ammo_depots_count=alive,
        total_ammo_depots_count=total,
        has_factory=factory,
        frontline_unit_count_limit=limit,
        front_line_capacity_with=lambda count: min(60, 15 + 12 * count),
        total_aircraft_parking=lambda _parking_type: helipads,
    )


def _pills(cp: Any) -> list[Any]:
    from qt_ui.windows.basemenu.header import BaseHeader

    header = cast(Any, BaseHeader.__new__(BaseHeader))
    header.cp = cp
    return BaseHeader.status_pills(header)


def _texts(cp: Any) -> list[str]:
    return [pill.text() for pill in _pills(cp)]


def _tooltip(cp: Any, contains: str) -> str:
    """A pill's tooltip as a sentence, with the wrapping and escaping undone.

    It is rich text, so it carries <br> wherever the wrapper chose to break and an
    escaped apostrophe. Asserting on that would be asserting about the wrapping
    rather than about what the tooltip says.
    """
    import html
    import re

    pill = next(pill for pill in _pills(cp) if contains in pill.text())
    plain = html.unescape(re.sub("<[^>]+>", " ", pill.toolTip()))
    return " ".join(plain.split())


def _working() -> Any:
    return SimpleNamespace(damaged=False, repair_turns_remaining=None)


def test_a_working_runway_says_so(qt_app: Any) -> None:
    assert _texts(_cp(runway=_working()))[0] == "Runway operational"


def test_a_runway_under_repair_says_how_long(qt_app: Any) -> None:
    """The number is the whole point: it decides whether to frag from here next turn."""
    cp = _cp(runway=SimpleNamespace(damaged=True, repair_turns_remaining=2))
    assert _texts(cp)[0] == "Runway damaged · repairs in 2"


def test_a_damaged_runway_nobody_is_fixing_says_only_that(qt_app: Any) -> None:
    cp = _cp(runway=SimpleNamespace(damaged=True, repair_turns_remaining=None))
    assert _texts(cp)[0] == "Runway damaged"


def test_a_farp_talks_about_its_helipads_not_about_a_runway(qt_app: Any) -> None:
    """It reports a runway status because every control point does, but it has none.

    Nothing can crater it and nothing repairs it, so "runway operational" there says
    nothing -- and invites the player to believe a Hornet could use it.
    """
    cp = _cp(runway=_working(), has_runway=False, helipads=8)
    assert _texts(cp)[0] == "8 helipads"


def test_a_farp_with_one_pad_counts_it_in_the_singular(qt_app: Any) -> None:
    cp = _cp(runway=_working(), has_runway=False, helipads=1)
    assert _texts(cp)[0] == "1 helipad"


def test_a_base_with_nowhere_to_land_says_nothing_about_landing(qt_app: Any) -> None:
    cp = _cp(runway=_working(), has_runway=False, helipads=0)
    assert not any("helipad" in text or "Runway" in text for text in _texts(cp))


def test_the_ammo_depots_are_a_figure(qt_app: Any) -> None:
    cp = _cp(runway=_working(), depots=(3, 3), factory=True)
    assert _texts(cp) == [
        "Runway operational",
        "Ammo depots 3/3",
        "Factory producing",
    ]


def test_a_base_with_no_depots_says_so_rather_than_going_quiet(qt_app: Any) -> None:
    """Silence read as "the window forgot", which is the one thing it must not say."""
    assert "No ammo depots" in _texts(_cp(runway=_working()))


def test_a_base_with_no_factory_says_so_too(qt_app: Any) -> None:
    assert "No factory" in _texts(_cp(runway=_working()))


def test_depots_partly_down_are_called_low(qt_app: Any) -> None:
    assert "Ammo depots 1/2 · low" in _texts(_cp(depots=(1, 2)))


def test_every_depot_down_is_not_called_low(qt_app: Any) -> None:
    """None left is not "running short": it is the floor, and it reads as one."""
    assert "Ammo depots 0/2" in _texts(_cp(depots=(0, 2)))


def test_a_dead_factory_is_not_producing(qt_app: Any) -> None:
    """has_factory is false once it is rubble, which is the answer that matters."""
    cp = _cp(runway=None, factory=False)
    assert "No factory" in _texts(cp)


def test_the_depots_pill_explains_the_limit_it_sets(qt_app: Any) -> None:
    """The figure means nothing without the arithmetic: each depot is twelve units."""
    tooltip = _tooltip(_cp(depots=(2, 2), limit=39), "Ammo depots")
    assert "39 units can be deployed to the front from here" in tooltip
    assert "12 for each of its 2 live depots" in tooltip


def test_a_limit_the_campaign_caps_says_that_rather_than_an_arithmetic_that_is_wrong(
    qt_app: Any,
) -> None:
    """Reciting "15 plus 12 each" against a capped figure quotes a sum that does not
    equal the number beside it, which reads as a bug in the window."""
    tooltip = _tooltip(_cp(depots=(5, 5), limit=60), "Ammo depots")
    assert "the campaign's own ceiling" in tooltip
    assert "would otherwise supply 75, so another depot would buy nothing" in tooltip


def test_a_broken_depot_says_what_repairing_it_would_buy(qt_app: Any) -> None:
    tooltip = _tooltip(_cp(depots=(1, 2), limit=27), "Ammo depots")
    assert "Repairing the other 1 would take that to 39" in tooltip


def test_the_factory_pill_says_where_the_units_come_from(qt_app: Any) -> None:
    """Not whether they can be ordered: without a factory they still can, and the
    pill claiming otherwise was contradicted by the list right under it."""
    assert "built here, and are on the base next turn" in _tooltip(
        _cp(factory=True), "Factory producing"
    )

    without = _tooltip(_cp(), "No factory")
    assert "can still be ordered here" in without
    assert "nearest friendly base that has one" in without


def test_every_kind_of_base_is_named(qt_app: Any) -> None:
    """Stated rather than inferred from which tabs appeared."""
    from game.theater import ControlPoint, Fob
    from qt_ui.windows.basemenu.header import kind_of

    def fake(**kwargs: bool) -> ControlPoint:
        return cast(ControlPoint, SimpleNamespace(**kwargs))

    assert kind_of(fake(is_carrier=False, is_lha=False)) == "AIRBASE"
    assert kind_of(fake(is_carrier=True, is_lha=False)) == "CARRIER"
    assert kind_of(fake(is_carrier=False, is_lha=True)) == "LHA"

    # is_carrier and is_lha are properties on the real class, so a FOB stand-in
    # subclasses it rather than assigning over them.
    class _Fob(Fob):
        def __init__(self, pads: bool, spawns: bool) -> None:
            self.pads = pads
            self.spawns = spawns

        @property
        def is_carrier(self) -> bool:
            return False

        @property
        def is_lha(self) -> bool:
            return False

        @property
        def has_helipads(self) -> bool:
            return self.pads

        @property
        def has_ground_spawns(self) -> bool:
            return self.spawns

    assert kind_of(_Fob(pads=False, spawns=True)) == "FOB"
    assert kind_of(_Fob(pads=True, spawns=False)) == "HELIPORT"


def test_a_long_sentence_does_not_decide_how_wide_a_window_opens(
    qt_app: Any,
) -> None:
    """A QLabel demands the full width of its text and a layout has to honour it.

    One air-defence line naming seven kinds of SAM set the smallest the base menu
    could be at 1803 px, so the window grew itself the moment it was shown -- which
    is what the window dancing its way open was.
    """
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    from qt_ui.widgets.cards import shrinkable

    sentence = (
        "M48 Chaparral x4 · M6 Linebacker x4 · M163 Vulcan Air Defense System x3 "
        "· SAM NASAMS LN AIM-120C · SAM Hawk TR (AN/MPQ-46)"
    )

    def demanded(label: QLabel) -> int:
        # The layout is where the size policy is honoured, which is where the window
        # got its floor from.
        holder = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        holder.setLayout(layout)
        return layout.minimumSize().width()

    assert demanded(QLabel(sentence)) > 400
    assert demanded(shrinkable(QLabel(sentence))) <= 40
