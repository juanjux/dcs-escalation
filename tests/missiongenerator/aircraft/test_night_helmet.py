"""Player A-10C II night equipment is selected when generating the mission."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from zipfile import ZipFile

import pytest
import yaml
from dcs import Mission, Point, lua
from dcs.planes import A_10C, A_10C_2, FA_18C_hornet
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

HELMET = A_10C_2.Properties.HelmetMountedDevice


def scenario(
    *,
    aircraft: Any = A_10C_2,
    phase: TimeOfDay = TimeOfDay.Night,
    policy: NightMissions = NightMissions.DayAndNight,
    helmet: int | None = None,
    year: int = 2020,
    restrict: bool = False,
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
    generator.flight = NS(unit_type=aircraft_type, iter_members=lambda: iter(members))  # type: ignore[assignment]
    generator.game = NS(  # type: ignore[assignment]
        conditions=NS(time_of_day=phase),
        settings=NS(night_day_missions=policy, restrict_props_by_date=restrict),
        date=date(year, 1, 1),
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
    s = scenario(phase=phase, helmet=helmet)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == (
        HELMET.Values.HMCS if helmet is None else helmet
    )


def test_explicitly_disabled_helmet_stays_disabled() -> None:
    s = scenario(helmet=HELMET.Values.Not_installed)
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft[HELMET.id] == HELMET.Values.Not_installed


@pytest.mark.parametrize(
    "phase,policy,expected",
    [
        (TimeOfDay.Night, NightMissions.OnlyDay, HELMET.Values.HMCS),
        (TimeOfDay.Day, NightMissions.OnlyNight, HELMET.Values.HMCS___NVG),
    ],
)
def test_forced_lighting_policy_overrides_turn_slot(
    phase: TimeOfDay, policy: NightMissions, expected: int
) -> None:
    s = scenario(phase=phase, policy=policy)
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


@pytest.mark.parametrize("aircraft", [A_10C, FA_18C_hornet])
def test_other_airframes_are_not_modified(aircraft: Any) -> None:
    s = scenario(aircraft=aircraft)
    before = dict(s.group.units[0].addpropaircraft or {})
    s.generator.setup_props()
    assert s.group.units[0].addpropaircraft.get(HELMET.id) == before.get(HELMET.id)


def test_generated_miz_contains_combined_device_for_player_only(tmp_path: Path) -> None:
    s = scenario()
    s.generator.setup_props()
    output = tmp_path / "a10-night.miz"
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
    assert [unit["AddPropAircraft"][HELMET.id] for unit in units] == [2, 1]
