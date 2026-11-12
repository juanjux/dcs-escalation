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
    ("stores", "use_coordinates"),
    [
        (("{BRU55_2*AGM-154C}",), True),
        (("{GBU-31}",), True),
        (("{8_x_AGM_86C}",), True),
        (("LAU_117_AGM_65G",), False),
        (("{BRU55_2*AGM-154C}", "{B06DD79A-F21E-4EB9-BD9D-AB3844618C93}"), False),
        (("{BRU55_2*AGM-154C}", "LAU_117_AGM_65G"), False),
    ],
)
def test_dead_exports_coordinate_tasks_for_gps_stores(
    tmp_path: Path, stores: tuple[str, ...], use_coordinates: bool
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
        i: {"CLSID": clsid}
        for i, clsid in enumerate(
            ("{5CE2FF2A-645A-4197-B48D-8720AC69394F}", "{FPU_8A_FUEL_TANK}", *stores),
            start=1,
        )
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
    attack_tasks = [task for task in tasks if task["id"] in {"Bombing", "AttackGroup"}]
    expected_task = "Bombing" if use_coordinates else "AttackGroup"
    assert [task["id"] for task in attack_tasks] == [expected_task] * 4
    params = [task["params"] for task in attack_tasks]
    assert [task["weaponType"] for task in params] == [
        WeaponType.ARM.value,
        WeaponType.ASM.value,
        WeaponType.GuidedBombs.value,
        WeaponType.Unguided.value,
    ]
    assert [task["expend"] for task in params] == ["All", "All", "Auto", "All"]
    assert [task["groupAttack"] for task in params] == [True, True, False, False]
    assert [task["altitudeEnabled"] for task in params] == [True, True, True, False]
    assert [task["directionEnabled"] for task in params] == [False, False, False, True]
    assert [task["attackQtyLimit"] for task in params] == [False, False, False, True]
    if use_coordinates:
        assert all((task["x"], task["y"]) == (100, 200) for task in params)
        assert all("groupId" not in task for task in params)
    else:
        assert all(task["groupId"] == battery.id for task in params)
