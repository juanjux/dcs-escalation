from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from dcs.mapping import Point
from dcs.point import MovingPoint, PointProperties, VNav
from dcs.terrain import Caucasus

from game.missiongenerator.aircraft.waypoints.waypointgenerator import (
    WaypointGenerator,
)


def _wp(eta_locked: bool, speed_locked: bool, name: str = "") -> Any:
    wp = MagicMock()
    wp.ETA_locked = eta_locked
    wp.speed_locked = speed_locked
    wp.name = name
    return wp


def _generator(points: list[Any]) -> WaypointGenerator:
    # Bypass __init__ (it needs a full flight/mission); only group.points and
    # flight are consulted by the method under test.
    gen: Any = object.__new__(WaypointGenerator)
    gen.group = MagicMock()
    gen.group.points = points
    gen.flight = MagicMock()
    return gen


def test_unlocks_speed_locked_waypoint_trapped_between_tots() -> None:
    """A carrier escort's JOIN waypoint gets a locked speed (its TOT clamps to
    the mission start, ETA == 0) while trapped between TOT-locked waypoints,
    which DCS rejects. The speed lock must be dropped while the times stay."""
    # spawn, JOIN (trapped), ESCORT HOLD, SPLIT, REFUEL, LANDING
    points = [
        _wp(eta_locked=True, speed_locked=True, name="spawn"),
        _wp(eta_locked=True, speed_locked=True, name="JOIN"),
        _wp(eta_locked=True, speed_locked=False, name="ESCORT HOLD"),
        _wp(eta_locked=False, speed_locked=True, name="SPLIT"),
        _wp(eta_locked=False, speed_locked=True, name="REFUEL"),
        _wp(eta_locked=False, speed_locked=True, name="LANDING"),
    ]

    _generator(points)._resolve_locked_speed_time_conflicts()

    # JOIN and the spawn are unlocked -- this fork also drops the speed lock on ANY
    # TOT-locked waypoint (not just a trapped one), because a carrier CAP clamps every
    # waypoint to ETA == 0 and DCS rejects the speed+time pair even on the first one.
    # The SPLIT/RTB legs (no TOT-locked waypoint after them) keep their locked speed.
    assert [p.speed_locked for p in points] == [False, False, False, True, True, True]
    # Times are untouched.
    assert all(p.ETA_locked for p in points[:3])


def test_leaves_untrapped_speed_locks_alone() -> None:
    """A normal escort (JOIN has a real TOT, so no speed lock there): the split/RTB
    legs are not trapped (no TOT-locked waypoint follows them) and keep their locked
    speed. The spawn still loses its speed lock -- it is TOT-locked, and this fork
    never leaves speed and time locked on the same waypoint."""
    points = [
        _wp(eta_locked=True, speed_locked=True, name="spawn"),
        _wp(eta_locked=True, speed_locked=False, name="JOIN"),
        _wp(eta_locked=True, speed_locked=False, name="ESCORT HOLD"),
        _wp(eta_locked=False, speed_locked=True, name="SPLIT"),
        _wp(eta_locked=False, speed_locked=True, name="REFUEL"),
        _wp(eta_locked=False, speed_locked=True, name="LANDING"),
    ]

    _generator(points)._resolve_locked_speed_time_conflicts()

    assert [p.speed_locked for p in points] == [False, False, False, True, True, True]


def test_unlocks_a_run_of_trapped_speed_locked_waypoints() -> None:
    """Every locked-speed waypoint in a run bounded by TOT-locked waypoints on
    both sides is unlocked."""
    points = [
        _wp(eta_locked=True, speed_locked=False, name="A"),
        _wp(eta_locked=False, speed_locked=True, name="B"),
        _wp(eta_locked=False, speed_locked=True, name="C"),
        _wp(eta_locked=True, speed_locked=False, name="D"),
    ]

    _generator(points)._resolve_locked_speed_time_conflicts()

    assert [p.speed_locked for p in points] == [False, False, False, False]


def test_route_generation_enables_vnav_for_player_a10_including_spawn() -> None:
    """The VNAV helper must run on the completed export, not only CDU extras."""
    points = [MovingPoint(Point(i, i, Caucasus())) for i in range(3)]
    for point in points:
        point.properties = PointProperties(vnav=VNav.V2D)
    route = [SimpleNamespace(tot=None, only_for_player=False) for _ in points]
    gen: Any = _generator(points)
    gen.flight = SimpleNamespace(
        points=route,
        flight_plan=SimpleNamespace(waypoints=route),
        state=SimpleNamespace(),
        client_count=1,
        unit_type=SimpleNamespace(dcs_unit_type=SimpleNamespace(id="A-10C_2")),
    )
    gen.set_takeoff_time = MagicMock(return_value=timedelta())
    gen.builder_for_waypoint = MagicMock()
    gen._estimate_min_fuel_for = MagicMock()

    _, kneeboard_route = gen.create_waypoints()

    assert kneeboard_route == route
    assert [p.dict()["properties"]["vnav"] for p in points] == [1, 1, 1]
