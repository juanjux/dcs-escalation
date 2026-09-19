"""Points the player writes down for his own aircraft.

A spot on the map is worth noting long before it is worth a flight plan. What matters
here is that it goes to an aircraft somebody is actually flying, and that an airframe
is never promised more room than it has.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.ato.savedpoints import (
    PAGE_FULL,
    Capacity,
    PointKind,
    SavedPoint,
    add_point,
    capacity_for,
    kinds_for,
    points_of,
    receivers,
    remove_point,
    room_for,
)


def _flight(aircraft: str = "FA-18C_hornet", crewed: int = 1) -> Any:
    return SimpleNamespace(
        callsign="TARSIER",
        client_count=crewed,
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id=aircraft)),
    )


def _point(kind: PointKind = PointKind.WAYPOINT, name: str = "Smoke") -> SavedPoint:
    return SavedPoint(kind=kind, name=name, x=1.0, y=2.0)


def test_a_flight_starts_with_nothing_written_down() -> None:
    """Including one from a save made before the feature existed."""
    assert points_of(cast(Any, _flight())) == []


def test_each_airframe_takes_what_its_own_cartridge_holds() -> None:
    """The Hornet's navigation set is 59 with HOME and the bullseye spoken for; the
    Viper's steerpoints stop at 25."""
    assert capacity_for("FA-18C_hornet") == Capacity(waypoints=57, markpoints=0)
    assert capacity_for("F-16C_50") == Capacity(waypoints=25, markpoints=0)


def test_an_airframe_nobody_measured_claims_nothing() -> None:
    assert capacity_for("Su-25T").waypoints == 0


def test_a_page_is_as_many_as_anyone_reads_in_the_air() -> None:
    """Every airframe measured so far holds more than a page, and the page is what
    gets read."""
    flight = _flight()

    assert room_for(cast(Any, flight), PointKind.WAYPOINT) == PAGE_FULL


def test_an_airframe_with_no_measured_room_still_takes_them() -> None:
    """They go on the kneeboard, which is where the player reads one off."""
    flight = _flight("Su-25T")

    assert room_for(cast(Any, flight), PointKind.MARKPOINT) == PAGE_FULL


def test_writing_one_down_uses_up_its_room() -> None:
    flight = _flight()

    assert add_point(cast(Any, flight), _point())

    assert room_for(cast(Any, flight), PointKind.WAYPOINT) == PAGE_FULL - 1
    assert room_for(cast(Any, flight), PointKind.MARKPOINT) == PAGE_FULL


def test_a_full_aircraft_refuses_another() -> None:
    flight = _flight()
    for _ in range(PAGE_FULL):
        assert add_point(cast(Any, flight), _point())

    assert not add_point(cast(Any, flight), _point())
    assert len(points_of(cast(Any, flight))) == PAGE_FULL


def test_one_can_be_taken_off_again() -> None:
    flight = _flight()
    add_point(cast(Any, flight), _point(name="First"))
    add_point(cast(Any, flight), _point(name="Second"))

    assert remove_point(cast(Any, flight), 0)

    assert [point.name for point in points_of(cast(Any, flight))] == ["Second"]
    assert not remove_point(cast(Any, flight), 7)


def test_an_airframe_whose_cartridge_takes_waypoints_is_offered_those_first() -> None:
    for aircraft in ("FA-18C_hornet", "F-16C_50"):
        assert kinds_for(aircraft)[0] is PointKind.WAYPOINT


def test_only_an_aircraft_somebody_is_flying_can_be_handed_one() -> None:
    """An AI aircraft has nobody in it to read a point."""
    crewed = _flight(crewed=2)
    empty = _flight(crewed=0)
    coalition = SimpleNamespace(
        ato=SimpleNamespace(packages=[SimpleNamespace(flights=[crewed, empty])])
    )

    assert list(receivers(coalition)) == [crewed]
