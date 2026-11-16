from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from dcs import Mission, Point, lua
from dcs.planes import B_52H, FA_18C_hornet
from dcs.task import Expend, GroundAttack, WeaponType
from dcs.unittype import FlyingType

from game.missiongenerator.aircraft.waypoints.strikeingress import (
    StrikeIngressBuilder,
)


def test_add_strike_tasks_handles_no_targets() -> None:
    """Regression: a Strike against an objective whose units are all destroyed
    leaves the strike waypoint with no targets. add_strike_tasks must not divide
    by zero (len(units) / len(targets)) and must add no bombing task.
    """
    # Bypass __init__ (needs a full mission/flight); only add_strike_tasks() and
    # the attributes it reads are exercised.
    builder: Any = object.__new__(StrikeIngressBuilder)
    builder.waypoint = MagicMock()
    builder.waypoint.targets = []
    builder.group = MagicMock()
    builder.group.units = [MagicMock()]  # would make the ratio 1 / 0 if reached

    waypoint = MagicMock()
    waypoint.tasks = []

    builder.add_strike_tasks(waypoint)  # must not raise ZeroDivisionError

    assert waypoint.tasks == []


@pytest.mark.parametrize(
    "aircraft, expected_task",
    [(B_52H, "CarpetBombing"), (FA_18C_hornet, "Bombing")],
)
def test_miz_strike_routes_unguided_bombs_by_aircraft(
    tmp_path: Path, aircraft: type[FlyingType], expected_task: str
) -> None:
    mission = Mission()
    start = Point(-320000, 630000, mission.terrain)
    group = mission.flight_group_inflight(
        mission.country("USA"), "Strike", aircraft, start, 3000, maintask=GroundAttack
    )
    ingress = group.add_waypoint(start, altitude=3000, speed=400)
    targets = [
        SimpleNamespace(position=Point(x, start.y, mission.terrain))
        for x in (-318000, -317800, -317400)
    ]
    builder: Any = object.__new__(StrikeIngressBuilder)
    builder.group = group
    builder.package = SimpleNamespace(target=None)
    builder.flight = SimpleNamespace(unit_type=SimpleNamespace(dcs_unit_type=aircraft))
    builder.waypoint = SimpleNamespace(targets=targets)
    builder.register_special_strike_points = MagicMock()
    builder.register_special_ingress_points = MagicMock()
    builder.add_tasks(ingress)

    output = tmp_path / "strike.miz"
    mission.save(str(output))
    with ZipFile(output) as archive:
        data = lua.loads(archive.read("mission").decode("utf-8"))["mission"]
    groups = [
        group
        for country in data["coalition"]["blue"]["country"].values()
        for group in country.get("plane", {}).get("group", {}).values()
    ]
    tasks = groups[0]["route"]["points"][2]["task"]["params"]["tasks"].values()
    guided = [
        task
        for task in tasks
        if task["params"].get("weaponType") == WeaponType.GuidedBombs.value
    ]
    assert [(task["id"], task["params"]["x"]) for task in guided] == [
        ("Bombing", target.position.x) for target in targets
    ]
    unguided = [
        task
        for task in tasks
        if task["params"].get("weaponType") == WeaponType.Bombs.value
    ]
    if expected_task == "CarpetBombing":
        [carpet] = unguided
        assert carpet["id"] == expected_task
        assert carpet["params"]["expend"] == Expend.All.value
        assert carpet["params"]["carpetLength"] == pytest.approx(2000 / 3)
    else:
        assert [(task["id"], task["params"]["x"]) for task in unguided] == [
            (expected_task, target.position.x) for target in targets
        ]
