"""Coalition reference points are not numbered flight-plan legs."""

from datetime import timedelta
from pathlib import Path
import zipfile
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from dcs import Mission
from dcs.lua import loads
from dcs.mapping import Point
from dcs.planes import A_10C_2

from game.ato.flightplans.custom import CustomFlightPlan, CustomLayout
from game.ato.flightplans.ferry import FerryFlightPlan, FerryLayout
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as Kind
from game.missiongenerator.aircraft.waypoints.waypointgenerator import WaypointGenerator
from game.theater.bullseye import Bullseye


def _point(name: str, kind: Kind) -> FlightWaypoint:
    return FlightWaypoint(name, kind, Point(100, 200, cast(Any, None)))


def _plan(custom: bool) -> Any:
    departure = _point("TAKEOFF", Kind.TAKEOFF)
    target = _point("TARGET", Kind.TARGET_POINT)
    landing = _point("LAND", Kind.LANDING_POINT)
    bullseye = _point("RENAMED REFERENCE", Kind.BULLSEYE)
    # An ordinary, user-named point must not be filtered by its display name.
    nav = _point("BULLSEYE", Kind.NAV)
    flight = cast(Any, SimpleNamespace())
    if custom:
        return CustomFlightPlan(
            flight, CustomLayout(departure, [target, nav, landing, bullseye])
        )
    return FerryFlightPlan(
        flight,
        FerryLayout(
            departure=departure,
            arrival=landing,
            divert=None,
            bullseye=bullseye,
            nav_to=[target, nav],
            nav_from=[],
            custom_waypoints=[],
        ),
    )


@pytest.mark.parametrize("custom", [False, True])
def test_existing_layouts_keep_reference_but_no_route_leg(custom: bool) -> None:
    plan = _plan(custom)
    stored = list(plan.layout.iter_waypoints())
    assert stored[-1].waypoint_type == Kind.BULLSEYE
    assert plan.waypoints == stored[:-1]
    assert list(plan.edges())[-1] == (stored[2], stored[3])
    assert stored[2].name == "BULLSEYE"
    assert list(plan.layout.iter_waypoints()) == stored


@pytest.mark.parametrize("custom", [False, True])
def test_export_and_kneeboard_share_route_without_bullseye(custom: bool) -> None:
    plan = _plan(custom)
    flight = SimpleNamespace(
        points=plan.waypoints[1:],
        flight_plan=plan,
        client_count=1,
        state=None,
        unit_type=SimpleNamespace(dcs_unit_type=A_10C_2),
    )
    generator = cast(Any, object.__new__(WaypointGenerator))
    generator.flight = flight
    generator.group = SimpleNamespace(points=[])
    generator.set_takeoff_time = MagicMock(return_value=timedelta())
    generator.builder_for_waypoint = MagicMock()
    generator._resolve_locked_speed_time_conflicts = MagicMock()
    generator._estimate_min_fuel_for = MagicMock()
    _, kneeboard = generator.create_waypoints()
    exported = [call.args[0] for call in generator.builder_for_waypoint.call_args_list]
    assert exported == kneeboard[1:]
    assert not any(w.waypoint_type == Kind.BULLSEYE for w in kneeboard)
    # The coalition reference remains separate and unchanged.
    reference = Bullseye(list(plan.layout.iter_waypoints())[-1].position)
    assert reference.to_pydcs() == {"x": 100, "y": 200}


def test_dropped_waypoints_remain_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _plan(False)
    target = plan.layout.nav_to[0]
    monkeypatch.setattr(plan.layout, "dropped_waypoints", lambda: [target])
    assert target not in plan.waypoints
    assert not any(w.waypoint_type == Kind.BULLSEYE for w in plan.waypoints)


def test_saved_mission_keeps_coalition_reference_without_extra_leg(
    tmp_path: Path,
) -> None:
    plan = _plan(False)
    mission = Mission()
    mission.coalition["blue"].bullseye = {"x": 12345, "y": 67890}
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "Reference test",
        A_10C_2,
        Point(0, 0, mission.terrain),
        altitude=1000,
    )
    for waypoint in plan.waypoints[1:]:
        group.add_waypoint(waypoint.position, altitude=1000, name=waypoint.name)
    output = tmp_path / "reference.miz"
    mission.save(str(output))
    with zipfile.ZipFile(output) as archive:
        exported = loads(archive.read("mission").decode())["mission"]
    blue = exported["coalition"]["blue"]
    assert blue["bullseye"] == {"x": 12345, "y": 67890}
    written = next(c for c in blue["country"].values() if c.get("plane"))["plane"][
        "group"
    ][1]
    points = list(written["route"]["points"].values())
    assert len(points) == len(plan.waypoints)
    assert points[-1]["name"] == "LAND"
    assert all(p.get("name") != "RENAMED REFERENCE" for p in points)
