"""What the button beside a set of coordinates offers.

Copying them was all it did, which is one step short of what anybody wants them for:
the point in the aeroplane. It is a small menu now, and the plain copy is still what
a campaign with nobody flying anything gets.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _flight(task: str = "SEAD", aircraft: str = "AV-8B", crewed: int = 1) -> Any:
    return SimpleNamespace(
        custom_name=None,
        flight_type=SimpleNamespace(value=task),
        unit_type=SimpleNamespace(
            display_name=aircraft, dcs_unit_type=SimpleNamespace(id="FA-18C_hornet")
        ),
        client_count=crewed,
        saved_points=[],
    )


def _game(*flights: Any) -> Any:
    return SimpleNamespace(
        blue=SimpleNamespace(
            ato=SimpleNamespace(packages=[SimpleNamespace(flights=list(flights))])
        )
    )


def _label(qt_app: Any, game: Any = None) -> Any:
    from dcs.mapping import Point
    from qt_ui.widgets.coordinatelabel import CoordinateLabel

    settings = SimpleNamespace(coordinate_format=None)
    position = cast(Any, SimpleNamespace(x=1.0, y=2.0))
    widget = CoordinateLabel.__new__(CoordinateLabel)
    # Built without its constructor: what is under test is the menu, and the
    # constructor is a pile of styling that wants a real Point to format.
    widget.text = "N36 W115"
    widget.position = position
    widget.game = game
    del Point, settings
    return widget


def test_nobody_flying_means_the_button_just_copies(qt_app: Any) -> None:
    assert _label(qt_app)._receivers() == []


def test_a_crewed_flight_is_offered(qt_app: Any) -> None:
    flying = _flight()
    ai = _flight(crewed=0)

    found = _label(qt_app, _game(flying, ai))._receivers()

    assert found == [flying]


def test_the_point_goes_into_the_flight_that_was_picked(qt_app: Any) -> None:
    from game.ato.savedpoints import PointKind, points_of

    flight = _flight()
    label = _label(qt_app, _game(flight))

    label._save(flight, PointKind.WAYPOINT)

    (point,) = points_of(flight)
    assert point.kind is PointKind.WAYPOINT
    assert point.name == "N36 W115"
    assert (point.x, point.y) == (1.0, 2.0)


def test_a_full_aircraft_is_greyed_rather_than_hidden(qt_app: Any) -> None:
    """Knowing the aircraft is full beats wondering where the entry went."""
    from PySide6.QtWidgets import QMenu

    from game.ato.savedpoints import PointKind, SavedPoint, add_point

    flight = _flight()
    # The Viper's steerpoints stop at 25, which is the tightest measured ceiling.
    flight.unit_type.dcs_unit_type.id = "F-16C_50"
    for n in range(25):
        assert add_point(flight, SavedPoint(PointKind.WAYPOINT, f"P{n}", 0.0, 0.0))
    label = _label(qt_app, _game(flight))

    menu = QMenu()
    label._add_kind(menu, PointKind.WAYPOINT, [flight])

    (action,) = menu.actions()
    assert not action.isEnabled()
    assert "no room" in action.toolTip()


def test_a_kind_the_aircraft_cannot_be_given_is_not_in_the_menu(qt_app: Any) -> None:
    """Nothing loads a markpoint into a Hornet, so the menu does not offer one."""
    from PySide6.QtWidgets import QMenu

    flight = _flight()
    label = _label(qt_app, _game(flight))

    menu = QMenu()
    label.pressed = lambda: None  # the real one would raise a window
    offered = {kind.label for kind in _kinds_of(flight)}

    assert offered == {"Waypoint"}
    del menu


def _kinds_of(flight: Any) -> Any:
    from qt_ui.widgets.coordinatelabel import _kinds

    return _kinds(flight)


def test_a_flight_is_named_by_its_task_when_it_has_no_name(qt_app: Any) -> None:
    from qt_ui.widgets.coordinatelabel import _name

    assert _name(_flight()) == "SEAD · AV-8B"
    named = _flight()
    named.custom_name = "TARSIER"
    assert _name(named) == "TARSIER · AV-8B"
