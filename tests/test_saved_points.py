"""Points the player writes down for his own aircraft.

A spot on the map is worth noting long before it is worth a flight plan. What matters
here is that it goes to an aircraft somebody is actually flying, and that an airframe
is never promised more room than it has.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from game.ato.savedpoints import (
    UNKNOWN_CEILING,
    Capacity,
    PointKind,
    SavedPoint,
    add_point,
    capacity_for,
    instead_of,
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
    # And an A-10's DTS database indexes two thousand waypoints.
    assert capacity_for("A-10C_2") == Capacity(waypoints=2050, markpoints=0)
    # The Super Hornets carry the Hornet's cartridge, section for section.
    assert capacity_for("FA-18E") == capacity_for("FA-18C_hornet")


def test_an_airframe_nobody_measured_claims_nothing() -> None:
    assert capacity_for("Su-25T").waypoints == 0


def test_the_room_is_the_aircraft_s_own() -> None:
    """Not the kneeboard's: the page paginates, the aeroplane does not."""
    assert room_for(cast(Any, _flight()), PointKind.WAYPOINT) == 57
    assert room_for(cast(Any, _flight("A-10C_2")), PointKind.WAYPOINT) == 2050


def test_an_airframe_with_no_measured_room_still_takes_them() -> None:
    """They go on the kneeboard, which is where the player reads one off."""
    flight = _flight("Su-25T")

    assert room_for(cast(Any, flight), PointKind.MARKPOINT) == UNKNOWN_CEILING


def test_writing_one_down_uses_up_its_room() -> None:
    flight = _flight()

    assert add_point(cast(Any, flight), _point())

    assert room_for(cast(Any, flight), PointKind.WAYPOINT) == 56
    assert room_for(cast(Any, flight), PointKind.MARKPOINT) == UNKNOWN_CEILING


def test_a_full_aircraft_refuses_another() -> None:
    """The Viper's twenty-five steerpoints are the tightest measured ceiling."""
    flight = _flight("F-16C_50")
    for _ in range(25):
        assert add_point(cast(Any, flight), _point())

    assert not add_point(cast(Any, flight), _point())
    assert len(points_of(cast(Any, flight))) == 25


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


def test_the_kneeboard_paginates_rather_than_capping(qt_free: None = None) -> None:
    """An A-10 holds thousands; a page holds a couple of dozen."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from game.missiongenerator.kneeboard import SavedPointsPage

    points = [_point(name=f"P{n}") for n in range(50)]

    pages = SavedPointsPage.paginate(
        "HAWG", points, cast(Any, None), cast(Any, None), False
    )

    assert len(pages) == 3
    assert [page.first_number for page in pages] == [1, 23, 45]
    assert sum(len(page.points) for page in pages) == 50


def test_one_page_of_points_is_not_numbered() -> None:
    """A handful reads exactly as it did before there was more than one page."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from game.missiongenerator.kneeboard import SavedPointsPage

    (page,) = SavedPointsPage.paginate(
        "HAWG", [_point()], cast(Any, None), cast(Any, None), False
    )

    assert page.total_pages == 1


# ------------------------------------- the kind an aircraft cannot actually be given


def test_a_hornet_is_offered_a_waypoint_in_place_of_a_markpoint() -> None:
    """Its data cartridge has no markpoint section -- they are made in the cockpit --
    and the point is worth having in the aircraft as something."""
    assert instead_of("FA-18C_hornet", PointKind.MARKPOINT) is PointKind.WAYPOINT


def test_a_kind_the_aircraft_does_carry_is_not_questioned() -> None:
    assert instead_of("FA-18C_hornet", PointKind.WAYPOINT) is None
    assert instead_of("A-10C_2", PointKind.WAYPOINT) is None


def test_no_aircraft_takes_a_loaded_markpoint() -> None:
    """Every one of them has markpoints; none of them can be handed one. The Hornet's
    cartridge has no markpoint section and the A-10's DTS database is waypoints only,
    so the lettered marks are made in the cockpit either way."""
    for aircraft in ("FA-18C_hornet", "FA-18E", "F-16C_50", "A-10C_2"):
        assert instead_of(aircraft, PointKind.MARKPOINT) is PointKind.WAYPOINT


def test_an_airframe_that_carries_neither_is_left_alone() -> None:
    """Swapping one kind it cannot take for another it cannot take gains nothing, so
    the point is written down without a question."""
    assert instead_of("Ka-50_3", PointKind.MARKPOINT) is None
    assert instead_of("Ka-50_3", PointKind.WAYPOINT) is None
