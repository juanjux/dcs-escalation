"""Manual MSL edits cannot put a waypoint under known terrain."""

from typing import Any

from dcs import Point
from dcs.terrain import Caucasus
import pytest

from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato import waypointaltitude
from game.utils import feet


@pytest.fixture
def point(monkeypatch: pytest.MonkeyPatch) -> FlightWaypoint:
    monkeypatch.setattr(
        waypointaltitude, "elevation_m", lambda *args: feet(6000).meters
    )
    return FlightWaypoint(
        "HOLD", FlightWaypointType.LOITER, Point(0, 0, Caucasus()), feet(21000)
    )


def test_msl_under_terrain_is_rejected_without_mutating_the_waypoint(
    point: FlightWaypoint,
) -> None:
    with pytest.raises(ValueError, match="6,000 ft MSL"):
        point.apply_altitude_edit(feet(600))
    assert point.alt == feet(21000)
    assert point.alt_type == "BARO"
    assert not point.altitude_is_manual


def test_agl_is_not_compared_to_msl_terrain(point: FlightWaypoint) -> None:
    point.apply_altitude_edit(feet(600), "RADIO")
    assert (point.alt, point.alt_type, point.altitude_is_manual) == (
        feet(600),
        "RADIO",
        True,
    )
    with pytest.raises(ValueError, match="below"):
        point.apply_altitude_edit(reference="BARO")
    assert (point.alt, point.alt_type) == (feet(600), "RADIO")


@pytest.mark.parametrize("height", [6000, 6600, 20000])
def test_msl_at_or_above_terrain_is_allowed(height: int, point: FlightWaypoint) -> None:
    point.apply_altitude_edit(feet(height))
    assert point.alt == feet(height)
    assert point.altitude_is_manual


def test_agl_edit_does_not_need_an_elevation_query(
    point: FlightWaypoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: Any) -> float:
        pytest.fail("AGL does not need an external elevation lookup")

    monkeypatch.setattr(waypointaltitude, "elevation_m", unexpected)
    point.apply_altitude_edit(feet(500), "RADIO")


def test_missing_elevation_allows_msl_with_a_warning(
    point: FlightWaypoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(waypointaltitude, "elevation_m", lambda *args: None)
    warning = point.apply_altitude_edit(feet(600))
    assert point.alt == feet(600)
    assert point.altitude_is_manual
    assert warning is not None and "could not be checked" in warning


def test_failed_bulk_validation_does_not_change_any_waypoint(
    point: FlightWaypoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace as NS
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab import (
        QFlightWaypointTab,
    )

    other = FlightWaypoint("NAV", FlightWaypointType.NAV, Point(0, 0, None), feet(21000))  # type: ignore[arg-type]
    messages: list[str] = []
    monkeypatch.setattr(
        "qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab.QMessageBox.warning",
        lambda parent, title, message: messages.append(message),
    )
    view: Any = NS(
        flight=NS(flight_plan=NS(waypoints=[other, point])),
        bulk_altitude=NS(value=lambda: 600),
        _is_bulk_editable=lambda w: True,
        on_change=lambda: pytest.fail("Invalid bulk edit must not publish changes"),
    )
    QFlightWaypointTab.on_apply_bulk_altitude(view)
    assert len(messages) == 1
    assert all(
        w.alt == feet(21000) and not w.altitude_is_manual for w in (other, point)
    )
