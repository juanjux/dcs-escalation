"""Spino v3 aircraft keep fifteen valid stations and only air-to-air tasks."""

import json
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4
from zipfile import ZipFile

import pytest
from dcs import Mission, Point, lua, planes, task
from dcs.countries import USA
from dcs.payloads import PayloadDirectories
from dcs.terrain import Caucasus
from dcs.unittype import FlyingType

from game import persistency
from game.ato import FlightType
from game.ato.airtaaskingorder import AirTaskingOrder
from game.ato.loadouts import Loadout
from game.ato.package import Package
from game.data.weapons import Pylon, Weapon
from game.db.database import Database
from game.dcs.aircrafttype import AircraftType
from game.factions.faction import Faction
from game.migrator import Migrator
from game.radio.channels import CommonRadioChannelAllocator
from game.theater.start_generator import ModSettings
from pydcs_extensions.f15ex.f15ex import F_15EX, F_15EX_CFT, F_15IA

VARIANTS = [
    ("F-15EX Eagle II", F_15EX, 6146),
    ("F-15EX Eagle II (CFTs)", F_15EX_CFT, 10571),
    ("F-15IA", F_15IA, 10571),
]
TASKS = [
    FlightType.INTERCEPTION,
    FlightType.SWEEP,
    FlightType.BARCAP,
    FlightType.TARCAP,
    FlightType.ESCORT,
]


@pytest.fixture(autouse=True)
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16885)
    monkeypatch.setattr(
        PayloadDirectories, "preferred", Path("resources/customized_payloads")
    )
    for _, unit, _ in VARIANTS:
        monkeypatch.setattr(unit, "payloads", None)


@pytest.mark.parametrize("name,unit,fuel", VARIANTS)
def test_catalog_and_tasks(name: str, unit: Any, fuel: int) -> None:
    aircraft = AircraftType.named(name)
    assert aircraft.dcs_unit_type is planes.plane_map[unit.id] is unit
    assert aircraft.max_fuel == fuel
    assert set(aircraft.task_priorities) == set(TASKS)
    assert set(unit.tasks) == {task.CAP, task.Escort, task.FighterSweep, task.Intercept}
    assert unit.category == "Interceptor"
    assert unit.pylons == set(range(1, 16))
    assert aircraft.intra_flight_radio is not None
    assert aircraft.intra_flight_radio.name == "AN/ARC-210"
    assert isinstance(aircraft.channel_allocator, CommonRadioChannelAllocator)
    assert aircraft.channel_allocator.intra_flight_radio_index == 2
    assert aircraft.channel_allocator.inter_flight_radio_index == 1
    assert set(unit.panel_radio) == {1, 2}
    assert all(len(r["channels"]) == 20 for r in unit.panel_radio.values())


@pytest.mark.parametrize("name,unit,fuel", VARIANTS)
@pytest.mark.parametrize("role", TASKS)
def test_default_loadouts_use_valid_nonempty_stations(
    name: str, unit: Any, fuel: int, role: FlightType
) -> None:
    aircraft = AircraftType.named(name)
    loadout = Loadout.default_for_task_and_aircraft(role, unit)
    assert loadout.name == f"Retribution {role.value}"
    assert len(loadout.pylons) == 13
    for number, weapon in loadout.pylons.items():
        assert weapon is not None
        assert Pylon.for_aircraft(aircraft, number).can_equip(weapon)
        assert weapon.pydcs_data["weight"] > 0
        assert not any(
            token in weapon.clsid for token in ("AGM", "GBU", "MAKO", "MALD")
        )


def test_variant_payload_caches_do_not_reuse_the_base_aircraft() -> None:
    # pydcs caches by class attribute; inherited payloads must not mask a variant's file.
    loads = [
        Loadout.default_for_task_and_aircraft(FlightType.BARCAP, u)
        for _, u, _ in VARIANTS
    ]
    assert loads[0].pylons[5] is not None
    assert loads[1].pylons[5] is not None
    assert loads[2].pylons[3] is not None
    assert "FUS_LF" in loads[0].pylons[5].clsid
    assert loads[1].pylons[5].clsid == "{AMBER_2xAIM260A}"
    assert "PYTHON-5" in loads[2].pylons[3].clsid


@pytest.mark.parametrize("name,unit,fuel", VARIANTS)
def test_stations_only_offer_declared_positive_weight_stores(
    name: str, unit: Any, fuel: int
) -> None:
    aircraft = AircraftType.named(name)
    for number in range(1, 16):
        pylon = Pylon.for_aircraft(aircraft, number)
        assert pylon.allowed
        assert all(weapon.pydcs_data["weight"] > 0 for weapon in pylon.allowed)
        assert not any(
            any(
                token in weapon.clsid for token in ("B21_AGM", "MAKO", "aargm", "APKWS")
            )
            for weapon in pylon.allowed
        )


def test_existing_aircraft_pickles_reload_current_capabilities() -> None:
    aircraft = AircraftType.named("F-15EX Eagle II")
    restored = pickle.loads(pickle.dumps(aircraft))
    assert restored.max_fuel == 6146
    assert not restored.capable_of(FlightType.STRIKE)
    assert restored.capable_of(FlightType.BARCAP)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    ("faction_name", "expected_variants"),
    [
        ("bluefor_modern", {"F15EX", "F15EX_CFT", "F15IA"}),
        ("blufor_current", {"F15EX_CFT"}),
        ("wrl_taskforceblue", {"F15EX_CFT"}),
    ],
)
def test_mod_switch_filters_all_variants(
    enabled: bool, faction_name: str, expected_variants: set[str]
) -> None:
    faction = Faction.from_dict(
        json.loads(
            Path(f"resources/factions/{faction_name}.json").read_text(encoding="utf-8")
        )
    )
    faction.apply_mod_settings(ModSettings(f15ex=enabled))
    ids = {a.dcs_id for a in faction.aircraft}
    mod_ids = {"F15EX", "F15EX_CFT", "F15IA"} & ids
    assert mod_ids == (expected_variants if enabled else set())


def test_all_variants_serialize_with_valid_loadouts_and_nato_callsigns(
    tmp_path: Path,
) -> None:
    mission = Mission(Caucasus())
    country = mission.country("USA")
    for index, (name, unit, fuel) in enumerate(VARIANTS):
        group = mission.flight_group_inflight(
            country, unit.id, unit, Point(index * 10000, 0, mission.terrain), 6000, 250
        )
        group.frequency = 251
        group.task = task.CAP.name
        group.units[0].fuel = fuel
        group.units[0].set_client()
        group.units[0].set_radio_channel_preset(1, 1, 251.0)
        group.units[0].set_radio_channel_preset(2, 1, 124.0)
        loadout = Loadout.default_for_task_and_aircraft(FlightType.BARCAP, unit)
        for number, weapon in loadout.pylons.items():
            assert weapon is not None
            Pylon.for_aircraft(AircraftType.named(name), number).equip(
                group.units[0], weapon
            )
    path = tmp_path / "f15ex_v3.miz"
    mission.save(str(path))
    with ZipFile(path) as archive:
        saved = lua.loads(archive.read("mission").decode())["mission"]
    saved_country = next(
        c for c in saved["coalition"]["blue"]["country"].values() if c["id"] == USA.id
    )
    groups = saved_country["plane"]["group"]
    assert len(groups) == 3
    for saved_group in groups.values():
        saved_unit = saved_group["units"][1]
        assert saved_unit["type"] in {u.id for _, u, _ in VARIANTS}
        assert isinstance(saved_unit["callsign"], dict)
        assert len(saved_unit["payload"]["pylons"]) == 13
        assert len(saved_unit["Radio"]) == 2
        expected_fuel = next(
            fuel for _, unit, fuel in VARIANTS if unit.id == saved_unit["type"]
        )
        assert saved_unit["payload"]["fuel"] == expected_fuel


def test_local_mod_station_tables_match_integration() -> None:
    root = Path.home() / "Saved Games/DCS/Mods/aircraft/F-15EX V3"
    if not root.is_dir():
        pytest.skip("Optional cross-check against a local Spino v3 installation")
    from tools.audit_mod_pylons import pylon_offers, strip_comments

    for name, unit, _ in VARIANTS:
        offered = pylon_offers(
            strip_comments((root / f"{unit.id}.lua").read_text(encoding="utf-8-sig"))
        )
        aircraft = AircraftType.named(name)
        for number in unit.pylons:
            declared = {w.clsid for w in Pylon.for_aircraft(aircraft, number).allowed}
            assert declared <= offered[number], (
                unit.id,
                number,
                declared - offered[number],
            )


def test_migration_cancels_ground_tasks_and_repairs_legacy_loadouts() -> None:
    aircraft = AircraftType.named("F-15EX Eagle II")
    squadron = SimpleNamespace(
        aircraft=aircraft,
        primary_task=FlightType.STRIKE,
        auto_assignable_mission_types={FlightType.STRIKE, FlightType.BARCAP},
    )

    def set_tasks(tasks: set[FlightType]) -> None:
        squadron.auto_assignable_mission_types = {
            t for t in tasks if aircraft.capable_of(t)
        }

    squadron.set_auto_assignable_mission_types = set_tasks
    db: Any = Database()
    package = Package(MagicMock(), db)
    wrong = Loadout(
        "old", {6: Weapon.with_clsid("{F15E_EXTTANK}")}, None, is_custom=True
    )
    member = SimpleNamespace(loadout=wrong, use_custom_loadout=True)

    def flight(role: FlightType) -> Any:
        return SimpleNamespace(
            id=uuid4(),
            unit_type=aircraft,
            flight_type=role,
            fuel=13455,
            roster=SimpleNamespace(members=[member]),
            flight_plan=None,
            cargo=None,
            return_pilots_and_aircraft=MagicMock(),
            label_formation_waypoints=MagicMock(),
        )

    strike, patrol = flight(FlightType.STRIKE), flight(FlightType.BARCAP)
    package.add_flight(strike)
    package.add_flight(patrol)
    coalition = SimpleNamespace(
        ato=AirTaskingOrder([package]),
        faction=SimpleNamespace(aircraft={aircraft}),
        air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron]),
    )
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(coalitions=[coalition])
    expected = Loadout.default_for_task_and_aircraft(FlightType.BARCAP, F_15EX)
    from unittest.mock import patch

    with patch.object(Loadout, "default_for", return_value=expected):
        migrator._update_f15ex_v3()
        migrator._update_f15ex_v3()
    assert package.flights == [patrol]
    assert strike.id not in db.objects
    strike.return_pilots_and_aircraft.assert_called_once()
    assert patrol.fuel == 6146
    assert member.loadout.pylons == expected.pylons
    assert not member.use_custom_loadout
    assert squadron.primary_task is FlightType.INTERCEPTION
    assert squadron.auto_assignable_mission_types == {FlightType.BARCAP}
    assert {a.dcs_id for a in coalition.faction.aircraft} == {"F15EX", "F15EX_CFT"}


def test_migration_preserves_valid_custom_loadouts_empty_auto_tasks_and_ferries() -> (
    None
):
    aircraft = AircraftType.named("F-15IA")
    custom = Loadout.default_for_task_and_aircraft(FlightType.ESCORT, F_15IA).clone()
    member = SimpleNamespace(loadout=custom, use_custom_loadout=True)
    squadron = SimpleNamespace(
        aircraft=aircraft,
        primary_task=FlightType.ESCORT,
        auto_assignable_mission_types=set(),
        set_auto_assignable_mission_types=lambda _: None,
    )
    ferry = SimpleNamespace(
        unit_type=aircraft,
        flight_type=FlightType.FERRY,
        fuel=1000,
        roster=SimpleNamespace(members=[member]),
    )
    package = SimpleNamespace(flights=[ferry])
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(
        coalitions=[
            SimpleNamespace(
                ato=SimpleNamespace(packages=[package]),
                faction=SimpleNamespace(aircraft={aircraft}),
                air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron]),
            )
        ]
    )
    migrator._update_f15ex_v3()
    assert ferry.fuel == 1000 and member.loadout is custom and member.use_custom_loadout
    assert squadron.primary_task is FlightType.ESCORT
    assert not squadron.auto_assignable_mission_types


def test_migration_removes_empty_ground_package_without_touching_other_aircraft() -> (
    None
):
    aircraft = AircraftType.named("F-15EX Eagle II")
    db: Any = Database()
    package = Package(MagicMock(), db)
    strike: Any = SimpleNamespace(
        id=uuid4(),
        unit_type=aircraft,
        flight_type=FlightType.DEAD,
        cargo=None,
        return_pilots_and_aircraft=MagicMock(),
        label_formation_waypoints=MagicMock(),
    )
    package.add_flight(strike)
    other = SimpleNamespace(unit_type=SimpleNamespace(dcs_id="FA-18E"))
    other_package: Any = SimpleNamespace(flights=[other])
    squadron = SimpleNamespace(
        aircraft=aircraft,
        primary_task=FlightType.DEAD,
        auto_assignable_mission_types={FlightType.DEAD},
    )

    def set_tasks(tasks: set[FlightType]) -> None:
        squadron.auto_assignable_mission_types = {
            t for t in tasks if aircraft.capable_of(t)
        }

    squadron.set_auto_assignable_mission_types = set_tasks
    coalition = SimpleNamespace(
        ato=AirTaskingOrder([package, other_package]),
        faction=SimpleNamespace(aircraft={aircraft}),
        air_wing=SimpleNamespace(iter_squadrons=lambda: [squadron]),
    )
    migrator: Any = Migrator.__new__(Migrator)
    migrator.game = SimpleNamespace(coalitions=[coalition])
    migrator._update_f15ex_v3()
    assert coalition.ato.packages == [other_package]
    assert not db.objects
    strike.return_pilots_and_aircraft.assert_called_once()
    assert other_package.flights == [other]
    assert squadron.primary_task is FlightType.INTERCEPTION
    assert squadron.auto_assignable_mission_types == {FlightType.INTERCEPTION}
