"""Old EW Jammer settings must not reactivate calls to the removed Lua plugin."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from dcs import Mission
from dcs.mapping import Point
from dcs.planes import A_10C
from dcs.task import ControlledTask, OptECMUsing, SetUnlimitedFuelCommand

from game.ato import FlightType
from game.ato.flightplans.patrolling import PatrollingFlightPlan
from game.data.doctrine import MODERN_DOCTRINE
from game.missiongenerator.aircraft.waypoints.joinpoint import JoinPointBuilder
from game.missiongenerator.aircraft.waypoints.pydcswaypointbuilder import (
    PydcsWaypointBuilder,
)
from game.missiongenerator.aircraft.waypoints.racetrack import RaceTrackBuilder
from game.missiongenerator.aircraft.waypoints.racetrackend import RaceTrackEndBuilder
from game.missiongenerator.aircraft.waypoints.splitpoint import SplitPointBuilder
from game.settings import Settings
from game.utils import knots


@pytest.mark.parametrize("legacy_settings", [False, True])
@pytest.mark.parametrize(
    "builder_type,flight_type,ecm",
    [
        (JoinPointBuilder, FlightType.SEAD, OptECMUsing.Values.UseIfOnlyLockByRadar),
        (
            JoinPointBuilder,
            FlightType.SEAD_SWEEP,
            OptECMUsing.Values.UseIfOnlyLockByRadar,
        ),
        (JoinPointBuilder, FlightType.DEAD, OptECMUsing.Values.UseIfOnlyLockByRadar),
        (
            JoinPointBuilder,
            FlightType.SEAD_ESCORT,
            OptECMUsing.Values.UseIfDetectedLockByRadar,
        ),
        (SplitPointBuilder, FlightType.SEAD, OptECMUsing.Values.UseIfOnlyLockByRadar),
        (
            SplitPointBuilder,
            FlightType.SEAD_ESCORT,
            OptECMUsing.Values.UseIfOnlyLockByRadar,
        ),
        (RaceTrackBuilder, FlightType.AEWC, None),
        (RaceTrackBuilder, FlightType.BARCAP, None),
        (RaceTrackEndBuilder, FlightType.AEWC, None),
    ],
)
def test_removed_plugin_settings_do_not_inject_lua_calls(
    tmp_path: Path,
    legacy_settings: bool,
    builder_type: type[PydcsWaypointBuilder],
    flight_type: FlightType,
    ecm: OptECMUsing.Values | None,
) -> None:
    settings = Settings()
    if legacy_settings:
        settings.plugins.update(
            {"ewrj": True, "ewrj.ai_jammer_enabled": True, "ewrj.ecm_required": False}
        )
    # Use the old-save/preset deserializer, including unknown plugin settings.
    loaded = Settings.__new__(Settings)
    loaded.__setstate__(settings.__dict__.copy())
    if legacy_settings:
        assert loaded.plugins["ewrj"]
    loaded.ai_unlimited_fuel = True

    now = datetime(2026, 1, 1, 12)
    mission = Mission()
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "Legacy EW settings",
        A_10C,
        Point(0, 0, mission.terrain),
        5000,
        speed=350,
    )
    waypoint = group.points[0]
    waypoint.tasks.clear()
    plan = MagicMock(spec=PatrollingFlightPlan)
    plan.tot_offset = timedelta()
    plan.patrol_start_time = now
    plan.patrol_end_time = now + timedelta(minutes=30)
    plan.patrol_speed = knots(300)
    plan.engagement_distance = MODERN_DOCTRINE.cap_engagement_range
    coalition = NS(game=NS(settings=loaded), doctrine=MODERN_DOCTRINE)
    member = NS(is_player=False, loadout=NS(has_weapon_of_type=lambda _: True))
    flight: Any = NS(
        flight_type=flight_type,
        is_helo=False,
        client_count=0,
        coalition=coalition,
        squadron=NS(
            coalition=coalition,
            aircraft=NS(has_built_in_ecm=True, has_built_in_jamming=True),
        ),
        flight_plan=plan,
        package=NS(primary_flight=NS(group_id=7), target=NS()),
        iter_members=lambda: iter([member]),
    )
    logical_waypoint: Any = NS()
    builder = builder_type(logical_waypoint, group, flight, mission, now, MagicMock())
    builder.add_tasks(waypoint)

    native_ecm = [
        task.dict() for task in waypoint.tasks if isinstance(task, OptECMUsing)
    ]
    assert native_ecm == ([] if ecm is None else [OptECMUsing(ecm).dict()])
    fuel = SetUnlimitedFuelCommand(
        builder_type in (SplitPointBuilder, RaceTrackEndBuilder)
    )
    assert waypoint.tasks[0].dict() == fuel.dict()
    if builder_type is RaceTrackBuilder:
        assert any(isinstance(task, ControlledTask) for task in waypoint.tasks)
    if builder_type is SplitPointBuilder and flight_type is FlightType.SEAD_ESCORT:
        assert group.tasks  # The escort's triggered waypoint switch is retained.

    output = tmp_path / "legacy-ew-settings.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        serialized = archive.read("mission").decode("utf-8")
    assert "EWjamm(" not in serialized
    assert "IAdefjamming(" not in serialized
