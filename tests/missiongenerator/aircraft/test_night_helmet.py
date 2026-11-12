"""Player night equipment is selected when generating the mission."""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zipfile import ZipFile

import pytest
import yaml
from dcs import Mission, Point, lua
from dcs.mapping import LatLng
from dcs.helicopters import Ka_50_3
from dcs.planes import A_10C, A_10C_2, AV8BNA, F_15ESE, F_16C_50, FA_18C_hornet, M_2000C
from dcs.terrain import Caucasus

from game.ato.flightmember import FlightMember
from game.ato.loadouts import Loadout
from game.dcs.aircraftproperties import PropertyDateGate
from game.missiongenerator.aircraft.flightgroupconfigurator import (
    FlightGroupConfigurator,
)
from game.settings import NightMissions
from game.squadrons import Pilot
from game.timeofday import TimeOfDay
from pydcs_extensions.a4ec import A_4E_C
from pydcs_extensions.fa18efg.fa18efg import FA_18F

HELMET = A_10C_2.Properties.HelmetMountedDevice


def scenario(
    *,
    aircraft: Any = A_10C_2,
    phase: TimeOfDay = TimeOfDay.Night,
    policy: NightMissions = NightMissions.DayAndNight,
    helmet: int | None = None,
    year: int = 2020,
    restrict: bool = False,
    start: time = time(21),
    duration: timedelta = timedelta(hours=1),
) -> Any:
    mission = Mission(Caucasus())
    group = mission.flight_group(
        mission.country("USA"),
        "Night equipment",
        aircraft,
        airport=None,
        position=Point(-200000, 600000, mission.terrain),
        group_size=2,
    )
    members = [
        FlightMember(
            Pilot("Player" if player else "Wingman", player=player),
            Loadout("Test", {}, None),
        )
        for player in (True, False)
    ]
    group.units[0].set_client()
    for member in members:
        # Keep the unrelated datalink configuration out of this test.
        member.properties["SADL_TN"] = "0601"
        if helmet is not None:
            member.properties[HELMET.id] = helmet
    data = yaml.safe_load(
        Path(f"resources/units/aircraft/{aircraft.id}.yaml").read_text(encoding="utf-8")
    )
    aircraft_type = NS(
        dcs_id=aircraft.id,
        dcs_unit_type=aircraft,
        laser_code_configs=[],
        property_date_gate=PropertyDateGate.from_data(
            data.get("date_gated_properties")
        ),
    )
    generator = FlightGroupConfigurator.__new__(FlightGroupConfigurator)
    generator.group = group
    generator.time = mission.start_time = datetime.combine(date(year, 1, 1), start)
    plan = NS(
        startup_time=lambda: mission.start_time,
        landing_time=mission.start_time + duration,
    )
    generator.flight = NS(  # type: ignore[assignment]
        unit_type=aircraft_type,
        iter_members=lambda: iter(members),
        flight_plan=plan,
    )
    generator.game = NS(  # type: ignore[assignment]
        conditions=NS(time_of_day=phase),
        settings=NS(night_day_missions=policy, restrict_props_by_date=restrict),
        date=date(year, 1, 1),
        theater=NS(
            reference_position=LatLng(42.0, 42.0),
            timezone=timezone(timedelta(hours=4)),
        ),
    )
    return NS(generator=generator, mission=mission, group=group, members=members)


@pytest.mark.parametrize("helmet", [None, HELMET.Values.HMCS, HELMET.Values.HMCS___NVG])
def test_night_equips_only_the_player_without_mutating_saved_properties(
    helmet: int | None,
) -> None:
    s = scenario(helmet=helmet)
    original = [dict(m.properties) for m in s.members]
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == HELMET.Values.HMCS___NVG
    assert s.group.units[1].addpropaircraft[HELMET.id] == (
        HELMET.Values.HMCS if helmet is None else helmet
    )
    assert [m.properties for m in s.members] == original


@pytest.mark.parametrize("phase", [TimeOfDay.Dawn, TimeOfDay.Day, TimeOfDay.Dusk])
@pytest.mark.parametrize("helmet", [None, HELMET.Values.HMCS___NVG])
def test_non_night_equipment_is_unchanged(phase: TimeOfDay, helmet: int | None) -> None:
    s = scenario(phase=phase, helmet=helmet, start=time(12))
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == (
        HELMET.Values.HMCS if helmet is None else helmet
    )


def test_explicitly_disabled_helmet_stays_disabled() -> None:
    s = scenario(helmet=HELMET.Values.Not_installed)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == HELMET.Values.Not_installed


@pytest.mark.parametrize(
    "phase,start",
    [(TimeOfDay.Dusk, time(19)), (TimeOfDay.Dawn, time(6))],
)
def test_actual_darkness_at_start_overrides_the_turn_label(
    phase: TimeOfDay, start: time
) -> None:
    s = scenario(phase=phase, start=start)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == HELMET.Values.HMCS___NVG


def test_only_the_planned_flight_window_counts() -> None:
    s = scenario(phase=TimeOfDay.Night, start=time(6), duration=timedelta(hours=6))
    s.generator.flight.flight_plan.startup_time = lambda: s.generator.time.replace(
        hour=10
    )
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == HELMET.Values.HMCS


@pytest.mark.parametrize(
    "phase,start,policy,expected",
    [
        (TimeOfDay.Night, time(21), NightMissions.OnlyDay, HELMET.Values.HMCS),
        (TimeOfDay.Day, time(12), NightMissions.OnlyNight, HELMET.Values.HMCS___NVG),
    ],
)
def test_forced_lighting_policy_overrides_turn_slot(
    phase: TimeOfDay, start: time, policy: NightMissions, expected: int
) -> None:
    s = scenario(phase=phase, policy=policy, start=start)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == expected


@pytest.mark.parametrize(
    "year,restrict,expected",
    [
        (2010, True, HELMET.Values.Not_installed),
        (2012, True, HELMET.Values.HMCS___NVG),
        (2010, False, HELMET.Values.HMCS___NVG),
    ],
)
def test_automatic_selection_respects_era_restrictions(
    year: int, restrict: bool, expected: int
) -> None:
    s = scenario(year=year, restrict=restrict)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == expected


def test_cockpit_nvg_aircraft_exports_without_an_extra_property() -> None:
    s = scenario(aircraft=A_10C)
    before = dict(s.group.units[0].addpropaircraft or {})
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft == {**before, "SADL_TN": "0601"}


@pytest.mark.parametrize("start,expected", [(time(12), 1), (time(21), 2)])
def test_exclusive_helmet_uses_nvg_only_if_the_flight_needs_it(
    start: time, expected: int
) -> None:
    s = scenario(aircraft=FA_18C_hornet, helmet=1, start=start)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == expected
    assert s.members[0].properties[HELMET.id] == 1


def test_nvg_remains_available_before_jhmcs_was_introduced() -> None:
    s = scenario(aircraft=FA_18C_hornet, year=2000, restrict=True)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == 2
    assert s.group.units[1].addpropaircraft[HELMET.id] == 0


def test_two_seat_super_hornet_equips_both_positions() -> None:
    s = scenario(aircraft=FA_18F)
    s.generator.setup_props()
    for identifier in (HELMET.id, "HelmetMountedDeviceWSO"):
        assert s.group.units[0].addpropaircraft[identifier] == 2
        assert s.group.units[1].addpropaircraft[identifier] == 1


def test_black_shark_uses_its_own_helmet_property() -> None:
    s = scenario(aircraft=Ka_50_3)
    identifier = "Helmet-mounted device"
    ai_helmet = (s.group.units[1].addpropaircraft or {}).get(identifier)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[identifier] == 2
    assert s.group.units[1].addpropaircraft.get(identifier) == ai_helmet


def test_explicitly_disabled_nvg_switch_stays_disabled() -> None:
    s = scenario(aircraft=F_15ESE)
    s.members[0].properties["MountNVG"] = False
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft["MountNVG"] is False


@pytest.mark.parametrize(
    "aircraft,prop,player_value,ai_value",
    [
        (A_10C_2, HELMET.id, 2, 1),
        (A_4E_C, "Night_Vision", True, False),
        (FA_18C_hornet, HELMET.id, 2, 1),
        (F_16C_50, HELMET.id, 2, 1),
        (F_15ESE, "MountNVG", True, False),
        (AV8BNA, "MountNVG", True, False),
        (M_2000C, "LoadNVGCase", True, False),
    ],
)
def test_generated_miz_equips_player_when_the_flight_crosses_sunset(
    tmp_path: Path,
    aircraft: Any,
    prop: str,
    player_value: int | bool,
    ai_value: int | bool,
) -> None:
    s = scenario(
        aircraft=aircraft,
        phase=TimeOfDay.Dusk,
        start=time(16),
        duration=timedelta(hours=3),
    )
    s.generator.setup_props()
    output = tmp_path / "dusk.miz"
    s.mission.save(str(output))
    with ZipFile(output) as archive:
        data = lua.loads(archive.read("mission").decode())["mission"]
    units = [
        unit
        for country in data["coalition"]["blue"]["country"].values()
        for group in country.get("plane", {}).get("group", {}).values()
        for unit in group["units"].values()
    ]
    assert units[0]["skill"] == "Client"
    assert [unit["AddPropAircraft"][prop] for unit in units] == [player_value, ai_value]
