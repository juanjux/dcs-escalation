"""Flight-table height references remain independent across a shared DEAD route."""

import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from game.ato import sharedroute
from game.ato import waypointaltitude
from dcs import Point
from dcs.terrain import Caucasus
from game.ato.flightplans.formationattack import FormationAttackLayout
from game.ato.flighttype import FlightType
from game.ato.flightwaypointtype import FlightWaypointType as Wpt
from game.utils import feet, meters
from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
    AltitudeReferenceEditorDelegate,
    QFlightWaypointList,
)
from tests.test_shared_package_route import _package, _wpt


@pytest.fixture(scope="module")
def qt_app() -> Any:
    return QApplication.instance() or QApplication([])


def _dead_package() -> Any:
    package = _package(FlightType.DEAD)
    for flight, height in zip(package.flights, (21000, 22000)):
        flight.flight_plan.layout = FormationAttackLayout(
            departure=_wpt(Wpt.TAKEOFF),
            arrival=_wpt(Wpt.LANDING_POINT),
            divert=None,
            bullseye=_wpt(Wpt.BULLSEYE),
            custom_waypoints=[],
            nav_to=[],
            nav_from=[_wpt(Wpt.NAV, name="ALIGN")],
            hold=_wpt(Wpt.LOITER),
            join=_wpt(Wpt.JOIN),
            split=_wpt(Wpt.SPLIT),
            refuel=None,
            ingress=_wpt(Wpt.INGRESS_DEAD),
            targets=[_wpt(Wpt.TARGET_POINT) for _ in range(15)],
        )
        for point in flight.flight_plan.waypoints:
            point.alt = feet(height)
        flight.flight_plan.fuel_burn_distance_between_points = lambda a, b: meters(
            a.position.distance_to_point(b.position)
        )
    sharedroute.set_enabled(package, True)
    return package


def _view(package: Any, flight: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(QFlightWaypointList, "tot_text", lambda *args: "")
    return QFlightWaypointList(package, flight)


def _row(view: Any, point: Any) -> int:
    return next(
        row
        for row in range(view.model.rowCount())
        if view.waypoint_at_row(row) is point
    )


def _set_reference(view: Any, row: int, reference: str) -> None:
    index = view.model.index(row, 2)
    delegate = view.itemDelegateForColumn(2)
    assert isinstance(delegate, AltitudeReferenceEditorDelegate)
    editor = delegate.createEditor(view, QStyleOptionViewItem(), index)
    try:
        delegate.setEditorData(editor, index)
        assert editor.currentText() == view.model.item(row, 2).text()
        assert [editor.itemText(i) for i in range(editor.count())] == ["MSL", "AGL"]
        editor.setCurrentText(reference)
        delegate.setModelData(editor, view.model, index)
    finally:
        editor.deleteLater()


@pytest.mark.parametrize("name", ["hold", "split"])
def test_reference_selector_keeps_the_numeric_altitude(
    name: str, qt_app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _dead_package()
    flight = package.flights[0]
    point = getattr(flight.flight_plan.layout, name)
    view = _view(package, flight, monkeypatch)
    try:
        row = _row(view, point)
        assert view.model.item(row, 2).isEditable()
        view.model.item(row, 1).setText("600")
        _set_reference(view, row, "AGL")
        assert (point.alt, point.alt_type) == (feet(600), "RADIO")
        assert point.altitude_is_manual
        view.update_list()
        row = _row(view, point)
        assert view.model.item(row, 2).text() == "AGL"
        _set_reference(view, row, "MSL")
        assert (point.alt, point.alt_type) == (feet(600), "BARO")
    finally:
        view.deleteLater()


@pytest.mark.parametrize("reference", ["MSL", "AGL"])
def test_partial_dead_profiles_survive_editing_the_other_flight(
    reference: str, qt_app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _dead_package()
    first, second = package.flights
    for flight, height, expected in (
        (first, 600, (600, 22000)),
        (second, 500, (600, 500)),
        (first, 500, (500, 500)),
    ):
        view = _view(package, flight, monkeypatch)
        try:
            for point in (
                flight.flight_plan.layout.hold,
                flight.flight_plan.layout.split,
            ):
                row = _row(view, point)
                view.model.item(row, 1).setText(str(height))
                _set_reference(view, row, reference)
            sharedroute.synchronize(package, flight)
            for other, altitude in zip(package.flights, expected):
                layout = other.flight_plan.layout
                assert layout.hold.alt == feet(altitude)
                assert layout.split.alt == feet(altitude)
            assert first.flight_plan.layout.join.alt == feet(21000)
            assert second.flight_plan.layout.join.alt == feet(22000)
        finally:
            view.deleteLater()
    for flight in package.flights:
        for point in (flight.flight_plan.layout.hold, flight.flight_plan.layout.split):
            assert point.alt_type == ("RADIO" if reference == "AGL" else "BARO")


def test_table_redraw_does_not_mark_references_as_manual(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _dead_package()
    flight = package.flights[0]
    view = _view(package, flight, monkeypatch)
    try:
        view.update_list()
        assert not any(w.altitude_is_manual for w in flight.flight_plan.waypoints)
    finally:
        view.deleteLater()


def test_table_rejects_msl_under_terrain_and_restores_the_previous_cell(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _dead_package()
    flight = package.flights[0]
    point = flight.flight_plan.layout.hold
    point.position = Point(0, 0, Caucasus())
    monkeypatch.setattr(
        waypointaltitude, "elevation_m", lambda *args: feet(6000).meters
    )
    messages: list[str] = []
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.waypoints.QFlightWaypointList.QMessageBox.warning",
        lambda parent, title, message: messages.append(message),
    )
    view = _view(package, flight, monkeypatch)
    try:
        row = _row(view, point)
        view.model.item(row, 1).setText("600")
        assert point.alt == feet(21000)
        assert not point.altitude_is_manual
        assert view.model.item(row, 1).text() == "21000"
        assert len(messages) == 1
        _set_reference(view, row, "AGL")
        view.model.item(row, 1).setText("600")
        assert (point.alt, point.alt_type) == (feet(600), "RADIO")
        _set_reference(view, row, "MSL")
        assert (point.alt, point.alt_type) == (feet(600), "RADIO")
        assert view.model.item(row, 2).text() == "AGL"
        assert len(messages) == 2
    finally:
        view.deleteLater()


def test_table_warns_but_accepts_msl_if_elevation_is_unavailable(
    qt_app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _dead_package()
    flight = package.flights[0]
    point = flight.flight_plan.layout.hold
    point.position = Point(0, 0, Caucasus())
    monkeypatch.setattr(waypointaltitude, "elevation_m", lambda *args: None)
    messages: list[str] = []
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.waypoints.QFlightWaypointList.QMessageBox.warning",
        lambda parent, title, message: messages.append(message),
    )
    view = _view(package, flight, monkeypatch)
    try:
        row = _row(view, point)
        view.model.item(row, 1).setText("600")
        assert (point.alt, point.alt_type) == (feet(600), "BARO")
        assert point.altitude_is_manual
        assert len(messages) == 1 and "could not be checked" in messages[0]
    finally:
        view.deleteLater()
