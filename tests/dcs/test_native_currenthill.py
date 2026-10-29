"""Stock DCS 2.9.31 assets load without replacing the pinned pydcs."""

import importlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any
import zipfile

import pytest
from dcs import Mission, Point, lua, planes, vehicles
from dcs.countries import Iraq
from dcs.terrain import Caucasus
from dcs.unittype import VehicleType

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.mobility import MobilityMode
from pydcs_extensions import native_currenthill

UNITS = [
    ("CHAP_ZTQ15", "LT ZTQ-15 [CH]", UnitClass.TANK, 25),
    ("CHAP_BMD2", "IFV BMD-2 [CH]", UnitClass.IFV, 10),
    ("CHAP_Atlet", "MRAP AMN-2 Atlet [CH]", UnitClass.RECON, 3),
    ("CHAP_PGZ09", "SPAAG PGZ-09 [CH]", UnitClass.AAA, 15),
    ("CHAP_Ural4320_ZU232", "AAA ZU-23-2 on Ural 4320 [CH]", UnitClass.AAA, 7),
    ("CHAP_UralTyphoon", "MRAP Ural Typhoon-U [CH]", UnitClass.LOGISTICS, 3),
    ("CHAP_ZIL131", "Truck ZIL-131 [CH]", UnitClass.LOGISTICS, 3),
    ("CHAP_ZIL131_Kung", "Truck ZIL-131 Kung C2 [CH]", UnitClass.COMMAND_POST, 8),
]


@pytest.mark.parametrize("unit_id,name,unit_class,price", UNITS)
def test_native_catalog_and_mobility(
    unit_id: str,
    name: str,
    unit_class: UnitClass,
    price: int,
) -> None:
    unit = GroundUnitType.named(name)
    assert unit.dcs_unit_type is vehicles.vehicle_map[unit_id]
    assert unit.unit_class is unit_class
    assert unit.price == price
    assert unit.ground_mobility.mode is MobilityMode.SELF_PROPELLED
    assert unit.dcs_unit_type.id == unit_id
    assert len(list(GroundUnitType.for_dcs_type(unit.dcs_unit_type))) == 1


def test_native_registration_is_idempotent() -> None:
    before = {unit_id: vehicles.vehicle_map[unit_id] for unit_id, *_ in UNITS}
    aircraft = list(Iraq.planes)
    importlib.reload(native_currenthill)
    assert all(vehicles.vehicle_map[k] is v for k, v in before.items())
    assert Iraq.planes == aircraft
    assert not native_currenthill.__dict__.get("requires_mod")


def test_future_pydcs_definition_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Upstream(VehicleType):
        id = "CHAP_ZTQ15"

    class Fallback(VehicleType):
        id = "CHAP_ZTQ15"

    category = SimpleNamespace()
    monkeypatch.setitem(vehicles.vehicle_map, Upstream.id, Upstream)
    registered = native_currenthill._native_vehicle(category)(Fallback)
    assert registered is Upstream
    assert category.Fallback is Upstream
    assert vehicles.vehicle_map[Upstream.id] is Upstream


@pytest.mark.parametrize(
    "aircraft", [planes.MiG_25RBT, planes.MiG_23MLD, planes.IL_76MD]
)
def test_iraqi_aircraft_availability(aircraft: Any) -> None:
    assert getattr(Iraq.Plane, aircraft.__name__) is aircraft
    assert Iraq.planes.count(aircraft) == 1


def test_native_units_serialize_with_stock_type_ids(tmp_path: Path) -> None:
    mission = Mission(Caucasus())
    for index, (unit_id, *_rest) in enumerate(UNITS):
        mission.vehicle_group(
            mission.country("USA"),
            unit_id,
            vehicles.vehicle_map[unit_id],
            position=Point(-200000 + index * 100, 600000, mission.terrain),
        )
    output = tmp_path / "native-currenthill.miz"
    mission.save(str(output))
    with zipfile.ZipFile(output) as archive:
        data = lua.loads(archive.read("mission").decode("utf-8"))["mission"]
    spawned = [
        u["type"]
        for c in data["coalition"]["blue"]["country"].values()
        for g in c.get("vehicle", {}).get("group", {}).values()
        for u in g["units"].values()
    ]
    assert sorted(spawned) == sorted(unit_id for unit_id, *_ in UNITS)


@pytest.mark.parametrize("unit_id,name,_class,_price", UNITS)
def test_ids_and_names_match_installed_stock_assets(
    unit_id: str,
    name: str,
    _class: UnitClass,
    _price: int,
) -> None:
    path = (
        Path(
            "D:/SteamLibrary/steamapps/common/DCSWorld/CoreMods/tech/Currenthill Assets Pack/Database/Vehicles"
        )
        / f"{unit_id}.lua"
    )
    if not path.is_file():
        pytest.skip("DCS is not installed here")
    text = path.read_text(encoding="utf-8-sig")
    assert re.search(r'GT\.Name\s*=\s*"' + re.escape(unit_id) + r'"', text)
    assert re.search(
        r"""GT\.DisplayName\s*=\s*_\(["']""" + re.escape(name) + r"""["']\)""", text
    )
    for field, value in (
        ("DetectionRange", vehicles.vehicle_map[unit_id].detection_range),
        ("ThreatRange", vehicles.vehicle_map[unit_id].threat_range),
    ):
        declared = re.search(r"GT\." + field + r"\s*=\s*([0-9]+)", text)
        assert declared is not None
        assert int(declared.group(1)) == value
