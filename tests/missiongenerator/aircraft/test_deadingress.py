from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from dcs import Mission, Point, lua
from dcs.planes import FA_18C_hornet
from dcs.task import WeaponType
from dcs.terrain import Caucasus
from dcs.vehicles import AirDefence

from game.missiongenerator.aircraft.waypoints.deadingress import DeadIngressBuilder
from game.theater import TheaterGroundObject


@pytest.mark.parametrize(
    ("store", "point_masks"),
    [
        ("{BRU55_2*AGM-154C}", [262144, 8]),
        ("{GBU-31}", [8]),
        ("{8_x_AGM_86C}", [WeaponType.CruiseMissile.value]),
        ("LAU_117_AGM_65G", []),
    ],
)
def test_dead_exports_coordinate_tasks_for_gps_stores(
    tmp_path: Path, store: str, point_masks: list[int]
) -> None:
    terrain = Caucasus()
    mission = Mission(terrain)
    departure = Point(0, 0, terrain)
    battery = mission.vehicle_group(
        mission.country("Russia"),
        "Battery",
        AirDefence.Tor_9A331,
        Point(100, 200, terrain),
    )
    flight = mission.flight_group_inflight(
        mission.country("USA"), "DEAD", FA_18C_hornet, departure, 1000
    )
    flight.units[0].pylons = {
        2: {"CLSID": store},
        3: {"CLSID": "{B06DD79A-F21E-4EB9-BD9D-AB3844618C93}"},  # HARM
    }
    ingress = flight.add_waypoint(departure, 1000)
    builder: Any = object.__new__(DeadIngressBuilder)
    target = MagicMock(spec=TheaterGroundObject)
    target.groups = [SimpleNamespace(group_name=battery.name)]
    target.position = Point(300, 400, terrain)
    builder.package = SimpleNamespace(target=target)
    builder.group = flight
    builder.mission = mission
    builder.waypoint = SimpleNamespace(targets=[])
    builder.register_special_ingress_points = MagicMock()
    builder.add_tasks(ingress)

    path = tmp_path / "dead.miz"
    mission.save(str(path))
    with ZipFile(path) as miz:
        data = lua.loads(miz.read("mission").decode("utf-8"))["mission"]
    country = data["coalition"]["blue"]["country"]
    exported = next(c for c in country.values() if c["name"] == "USA")
    tasks = exported["plane"]["group"][1]["route"]["points"][2]["task"]["params"][
        "tasks"
    ].values()
    bombing = [task["params"] for task in tasks if task["id"] == "Bombing"]
    groups = [task["params"] for task in tasks if task["id"] == "AttackGroup"]

    assert [task["weaponType"] for task in bombing] == point_masks
    assert all((task["x"], task["y"]) == (100, 200) for task in bombing)
    assert all(task["groupId"] == battery.id for task in groups)
    assert [task["weaponType"] for task in groups] == [
        WeaponType.ARM.value,
        WeaponType.ASM.value & ~sum(point_masks),
        WeaponType.GuidedBombs.value & ~sum(point_masks),
        WeaponType.Unguided.value,
    ]
