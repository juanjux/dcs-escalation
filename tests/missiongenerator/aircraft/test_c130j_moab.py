"""The native C-130J Strike payload matches the validated MOAB configuration."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zipfile import ZipFile

import pytest
from dcs import Mission, Point, lua
from dcs.payloads import PayloadDirectories
from dcs.planes import C_130, C_130J_30
from dcs.task import Bombing, GroundAttack, WeaponType
from dcs.unittype import FlyingType

from game.ato.flightmember import FlightMember
from game.ato.flighttype import FlightType
from game.ato.loadouts import Loadout
from game.data.weapons import Pylon, Weapon
from game.dcs.aircrafttype import AircraftType
from game.dcs.payload_loading import install_resilient_payload_loading
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)
from game.missiongenerator.aircraft.waypoints.strikeingress import StrikeIngressBuilder
from game.settings import NightMissions
from game.squadrons import Pilot

MOAB = "{GBU-43}"


@pytest.fixture
def aircraft(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AircraftType:
    monkeypatch.setattr("game.persistency._dcs_saved_game_folder", str(tmp_path))
    directory = Path("resources/customized_payloads")
    monkeypatch.setattr(
        PayloadDirectories, "payload_dirs", classmethod(lambda cls: iter([directory]))
    )
    monkeypatch.setattr(FlyingType, "_payload_cache", None)
    monkeypatch.setattr(C_130J_30, "payloads", None)
    monkeypatch.setattr("game.payloadlibrary.builtin_changes", lambda _: {})
    install_resilient_payload_loading()
    return AircraftType.named(C_130J_30.id)


def scenario(aircraft: AircraftType, *, task: FlightType = FlightType.STRIKE) -> Any:
    mission = Mission()
    group = mission.flight_group_inflight(
        mission.country("USA"),
        "Native MOAB",
        C_130J_30,
        Point(-320000, 630000, mission.terrain),
        altitude=3000,
        speed=400,
        maintask=GroundAttack,
        group_size=2,
    )
    loadout = Loadout.default_for_task_and_aircraft(task, C_130J_30)
    members = [
        FlightMember(Pilot("Player" if player else "AI", player=player), loadout)
        for player in (True, False)
    ]
    for member in members:
        member.properties.update(allow_moab=False, ramp_down=True)
    generator: Any = object.__new__(FlightGroupConfigurator)
    generator.group = group
    generator.flight = NS(
        unit_type=aircraft,
        flight_type=task,
        iter_members=lambda: iter(members),
        package=NS(target=None),
    )
    generator.game = NS(
        date=date(2026, 1, 1),
        settings=NS(
            night_day_missions=NightMissions.DayAndNight,
            restrict_weapons_by_date=False,
            restrict_props_by_date=False,
            apply_target_overrides_to_loadouts=False,
        ),
    )
    return NS(mission=mission, group=group, generator=generator, members=members)


def test_strike_default_is_one_native_moab_on_rear_station(
    aircraft: AircraftType,
) -> None:
    loadout = Loadout.default_for_task_and_aircraft(FlightType.STRIKE, C_130J_30)
    assert {n: w.clsid for n, w in loadout.pylons.items() if w} == {3: MOAB}
    weapon = Weapon.with_clsid(MOAB)
    assert weapon is not None
    assert Pylon.for_aircraft(aircraft, 3).can_equip(weapon)
    assert not Pylon.for_aircraft(aircraft, 1).can_equip(weapon)
    assert not Pylon.for_aircraft(aircraft, 2).can_equip(weapon)
    assert aircraft.preferred_combat_altitude.feet == 10000


def test_transport_and_legacy_c130_do_not_gain_a_strike_payload(
    aircraft: AircraftType,
) -> None:
    assert not Loadout.default_for_task_and_aircraft(
        FlightType.TRANSPORT, C_130J_30
    ).pylons
    legacy = AircraftType.named(C_130.id)
    assert not legacy.capable_of(FlightType.STRIKE)
    weapon = Weapon.with_clsid(MOAB)
    assert weapon is not None
    assert all(not p.can_equip(weapon) for p in Pylon.iter_pylons(legacy))


def test_generated_miz_preserves_native_bomb_and_closed_ramp(
    aircraft: AircraftType, tmp_path: Path
) -> None:
    s = scenario(aircraft)
    original = [dict(m.properties) for m in s.members]
    s.generator.setup_props()
    s.generator.setup_payloads()
    assert [m.properties for m in s.members] == original

    ingress = s.group.add_waypoint(
        Point(-318000, 635000, s.mission.terrain), altitude=3000, speed=400
    )
    speed = ingress.speed
    builder: Any = object.__new__(StrikeIngressBuilder)
    builder.group = s.group
    builder.package = NS(target=None)
    builder.flight = NS(client_count=0)
    builder.waypoint = NS(
        targets=[
            NS(position=Point(-318000, 635000, s.mission.terrain)),
            NS(position=Point(-317800, 635200, s.mission.terrain)),
        ]
    )
    builder.add_tasks(ingress)
    assert len(ingress.tasks) == 1
    assert type(ingress.tasks[0]) is Bombing
    assert ingress.tasks[0].params["weaponType"] == WeaponType.Auto.value
    assert ingress.tasks[0].params["x"] == -317900
    assert ingress.tasks[0].params["y"] == 635100
    assert ingress.tasks[0].params["altitude"] == 3000
    assert ingress.speed == speed

    output = tmp_path / "c130j-strike.miz"
    s.mission.save(str(output))
    with ZipFile(output) as archive:
        data = lua.loads(archive.read("mission").decode())["mission"]
    groups = [
        group
        for country in data["coalition"]["blue"]["country"].values()
        for group in country.get("plane", {}).get("group", {}).values()
    ]
    for unit in groups[0]["units"].values():
        assert unit["payload"]["pylons"] == {3: {"CLSID": MOAB}}
        assert unit["AddPropAircraft"]["allow_moab"] is True
        assert unit["AddPropAircraft"]["ramp_down"] is False
    tasks = groups[0]["route"]["points"][2]["task"]["params"]["tasks"]
    assert [task["id"] for task in tasks.values()] == ["Bombing"]


@pytest.mark.parametrize("task", [FlightType.STRIKE, FlightType.TRANSPORT])
def test_empty_or_transport_payload_does_not_force_moab_properties(
    aircraft: AircraftType, task: FlightType
) -> None:
    s = scenario(aircraft, task=task)
    for member in s.members:
        member.loadout = Loadout.empty_loadout()
    s.generator.setup_props()
    s.generator.setup_payloads()
    for unit in s.group.units:
        assert not unit.pylons
        assert unit.addpropaircraft["allow_moab"] is False
        assert unit.addpropaircraft["ramp_down"] is True


def test_destroyed_objective_adds_no_moab_attack_task(aircraft: AircraftType) -> None:
    s = scenario(aircraft)
    s.generator.setup_payloads()
    builder: Any = object.__new__(StrikeIngressBuilder)
    builder.group = s.group
    builder.package = NS(target=None)
    builder.flight = NS(client_count=0)
    builder.waypoint = NS(targets=[])
    builder.add_tasks(s.group.points[0])
    assert not s.group.points[0].tasks
