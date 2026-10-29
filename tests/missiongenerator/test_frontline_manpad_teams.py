"""Vehicle-based MANPADS budgets, support teams and TIC formation membership."""

from __future__ import annotations

from itertools import count
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4
from zipfile import ZipFile

import pytest
from dcs import Mission
from dcs.lua import loads
from dcs.mapping import Point
from dcs.vehicles import Unarmed, vehicle_map

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import (
    CombatGroup,
    CombatGroupRole,
    GroundPlanner,
    deployable_armor,
    reserve_armor_for,
)
from game.ground_forces.combat_stance import CombatStance
from game.ground_forces.manpads import additional_manpad_teams, select_manpad_hosts
from game.missiongenerator.flotgenerator import FlotGenerator
from game.missiongenerator.missiondata import MissionData
from game.settings import Settings
from game.theater.player import Player
from game.utils import Heading


def unit(kind: UnitClass, *, rifleman: bool = False, weight: int = 1) -> GroundUnitType:
    identifier = (
        "SA-18 Igla manpad"
        if kind is UnitClass.MANPAD
        else "Soldier M4" if kind is UnitClass.INFANTRY else "Ural-375"
    )
    vehicle = vehicle_map.get(identifier, Unarmed.Ural_375)
    return GroundUnitType._variant_from_dict(
        vehicle,
        f"{kind.value}-{rifleman}-{weight}",
        {"class": kind.value, "spawn_weight": weight, "is_rifleman": rifleman},
    )


def combat(size: int, kind: UnitClass = UnitClass.IFV) -> CombatGroup:
    role = {
        UnitClass.IFV: CombatGroupRole.IFV,
        UnitClass.APC: CombatGroupRole.APC,
        UnitClass.TANK: CombatGroupRole.TANK,
        UnitClass.MANPAD: CombatGroupRole.SHORAD,
        UnitClass.LOGISTICS: CombatGroupRole.LOGI,
        UnitClass.INFANTRY: CombatGroupRole.INFANTRY,
    }[kind]
    return CombatGroup(role, unit(kind), size)


@pytest.mark.parametrize(
    "vehicles,expected", [(0, 0), (3, 0), (4, 1), (8, 1), (12, 2), (15, 2), (24, 3)]
)
def test_allowance_rounds_vehicle_count_not_group_count(
    vehicles: int, expected: int
) -> None:
    assert additional_manpad_teams([combat(vehicles)], 8) == expected
    assert additional_manpad_teams([combat(1) for _ in range(vehicles)], 8) == expected


@pytest.mark.parametrize("existing,expected", [(0, 2), (1, 1), (2, 0), (8, 0)])
def test_excludes_support_and_counts_existing_launchers(
    existing: int, expected: int
) -> None:
    groups = [
        combat(15),
        combat(50, UnitClass.LOGISTICS),
        combat(50, UnitClass.INFANTRY),
        combat(existing, UnitClass.MANPAD),
    ]
    assert additional_manpad_teams(groups, 8) == expected


@pytest.mark.parametrize(
    "ratio,expected", [(0, 0), (-1, 0), (4, 4), (8, 2), (16, 1), (100, 0)]
)
def test_ratio_is_configurable(ratio: int, expected: int) -> None:
    assert additional_manpad_teams([combat(15)], ratio) == expected


def scenario(*, infantry: bool = False, tic: bool = True, blue: bool = False) -> Any:
    mission = Mission()
    side = mission.country("USA" if blue else "Russia")
    settings = Settings()
    settings.perf_infantry = infantry
    settings.player_skill = "Excellent"
    settings.enemy_vehicle_skill = "High"
    soldiers = [unit(UnitClass.MANPAD), unit(UnitClass.INFANTRY, rifleman=True)]
    faction = NS(
        country=NS(name=side.name),
        infantry_with_class=lambda cls: (u for u in soldiers if u.unit_class is cls),
    )
    generator: Any = object.__new__(FlotGenerator)
    generator.mission = mission
    generator.mission_data = MissionData()
    generator.tic_enabled = tic
    generator.game = NS(settings=settings, faction_for=lambda _: faction)
    generator.conflict = NS(
        heading=Heading.from_degrees(0),
        theater=NS(is_on_land=lambda _: True),
        find_ground_position=lambda position, *_: position,
    )
    groups = []
    for index, size in enumerate((6, 4, 5)):
        group = combat(size)
        vehicle = mission.vehicle_group(
            side,
            ("TIC:" if tic else "") + f"HOST{index}",
            Unarmed.Ural_375,
            Point(index * 4000, 0, mission.terrain),
            group_size=size,
        )
        vehicle.late_activation = tic
        vehicle.add_waypoint(Point(index * 4000, 1000, mission.terrain)).name = (
            "t+5 roe=simulate mount"
        )
        groups.append((vehicle, group))
    return NS(
        gen=generator,
        mission=mission,
        side=side,
        groups=groups,
        soldiers=soldiers,
        settings=settings,
        player=Player.BLUE if blue else Player.RED,
    )


def generate(s: Any) -> list[Any]:
    sequence = count()
    with patch("game.missiongenerator.flotgenerator.GroundForcePainter"), patch(
        "game.missiongenerator.flotgenerator.namegen.next_infantry_name",
        side_effect=lambda *args: f"SUPPORT{next(sequence)}",
    ):
        for host, group in s.groups:
            if group.role in (CombatGroupRole.APC, CombatGroupRole.IFV):
                s.gen.gen_infantry_group_for_group(
                    host,
                    s.player,
                    s.side,
                    Heading.from_degrees(0),
                    str(host.name).removeprefix("TIC:") if s.gen.tic_enabled else None,
                )
        s.gen.gen_manpad_teams(s.groups, s.player)
    parents = {id(host) for host, _ in s.groups}
    return [g for g in s.side.vehicle_group if id(g) not in parents]


@pytest.mark.parametrize("infantry", [False, True])
@pytest.mark.parametrize("tic", [False, True])
@pytest.mark.parametrize("blue", [False, True])
def test_two_teams_independent_of_infantry_setting_and_side(
    infantry: bool, tic: bool, blue: bool
) -> None:
    s = scenario(infantry=infantry, tic=tic, blue=blue)
    groups = generate(s)
    launchers = [g for g in groups if g.units[0].type == "SA-18 Igla manpad"]
    assert len(launchers) == 2
    assert len(groups) == 4 + (15 if infantry else 0)
    assert {g.name for g in groups} == s.gen.mission_data.frontline_visibility_groups
    for g in groups:
        assert len(g.units) == 1 and g.hidden_on_mfd
        assert g.late_activation is tic
        assert g.units[0].skill.value == ("Excellent" if blue else "High")
    if tic:
        assert set(s.gen.mission_data.tic_groups) == {g.name for g in groups}
        for launcher in launchers:
            formation = launcher.name.split("#")[0]
            assert any(host.name == formation for host, _ in s.groups)
            assert any(
                g.units[0].type == "Soldier M4" and g.name.startswith(formation + "#")
                for g in groups
            )
    else:
        assert not s.gen.mission_data.tic_groups
        assert all(not g.name.startswith("TIC:") for g in groups)


def test_teams_and_auxiliaries_are_near_hosts_and_spread_apart() -> None:
    s = scenario()
    groups = generate(s)
    launchers = [g for g in groups if g.units[0].type == "SA-18 Igla manpad"]
    assert launchers[0].position.distance_to_point(launchers[1].position) >= 100
    for launcher in launchers:
        host = next(
            host for host, _ in s.groups if host.name == launcher.name.split("#")[0]
        )
        assert launcher.position.distance_to_point(host.position) <= 150
        auxiliary = next(
            g for g in groups if g is not launcher and g.name.split("#")[0] == host.name
        )
        assert 5 <= auxiliary.position.distance_to_point(launcher.position) <= 10.001


@pytest.mark.parametrize("setting", ["manpads", "frontline_manpad_vehicles_per_team"])
def test_disable_leaves_existing_inventory_alone(setting: str) -> None:
    s = scenario()
    setattr(s.settings, setting, False if setting == "manpads" else 0)
    existing = combat(1, UnitClass.MANPAD)
    host = s.mission.vehicle_group(
        s.side,
        "EXISTING",
        vehicle_map["SA-18 Igla manpad"],
        Point(0, 0, s.mission.terrain),
    )
    s.groups.append((host, existing))
    assert not generate(s)
    assert host in s.side.vehicle_group


def test_existing_launcher_uses_one_allowance_slot() -> None:
    s = scenario()
    existing = combat(1, UnitClass.MANPAD)
    host = s.mission.vehicle_group(
        s.side,
        "EXISTING",
        vehicle_map["SA-18 Igla manpad"],
        Point(0, 0, s.mission.terrain),
    )
    s.groups.append((host, existing))
    groups = generate(s)
    assert sum(g.units[0].type == "SA-18 Igla manpad" for g in groups) == 1
    assert len(groups) == 2


def test_faction_without_manpads_gets_no_team() -> None:
    s = scenario()
    s.soldiers[:] = [u for u in s.soldiers if u.unit_class is not UnitClass.MANPAD]
    assert not generate(s)


def test_auxiliary_is_a_faction_rifleman_not_a_heavy_weapon() -> None:
    s = scenario()
    s.soldiers[:] = [unit(UnitClass.MANPAD), unit(UnitClass.INFANTRY, weight=100)]
    groups = generate(s)
    assert (
        len(groups) == 2
    )  # No rifleman: retain launcher-only teams, not mortars/ATGMs.
    assert all(g.units[0].type == "SA-18 Igla manpad" for g in groups)


def test_zero_weight_candidates_are_not_selected() -> None:
    s = scenario()
    s.soldiers[:] = [
        unit(UnitClass.MANPAD, weight=0),
        unit(UnitClass.INFANTRY, rifleman=True),
    ]
    assert not generate(s)


def test_fallback_hosts_and_route_copy_do_not_copy_attack_tasks() -> None:
    s = scenario()
    for host, group in s.groups:
        group.role = CombatGroupRole.ARTILLERY
        host.name = str(host.name).removeprefix("TIC:")
    groups = generate(s)
    assert len(groups) == 4
    for g in groups:
        assert g.name.startswith("TIC:") and g.late_activation
        assert len(g.points) == 2
        assert g.points[1].name == "t+5 roe=simulate mount"
        assert not g.points[1].tasks


def test_prefers_carriers_and_spreads_teams_before_reusing_hosts() -> None:
    s = scenario()
    s.groups[0][1].role = CombatGroupRole.TANK
    hosts = select_manpad_hosts(s.groups, 3, [])
    assert hosts[0] is not s.groups[0][0]
    assert len({id(h) for h in hosts}) == 3
    assert select_manpad_hosts([], 2, []) == []
    assert select_manpad_hosts(s.groups, 0, []) == []


def test_transport_orders_board_between_bounds_and_deploy_on_arrival() -> None:
    s = scenario()
    host = s.groups[0][0]
    host.add_waypoint(Point(0, 2000, s.mission.terrain)).name = "t+20 roe=simulate"
    host.add_waypoint(Point(0, 3000, s.mission.terrain)).name = "t+40 roe=simulate"
    generate(s)
    assert host.points[0].name.endswith("mount")
    assert [point.name for point in host.points[1:]] == [
        "t+5 roe=simulate dismount",
        "t+18 mount",
        "t+20 roe=simulate dismount",
        "t+38 mount",
        "t+40 roe=simulate dismount",
    ]
    assert host.points[2].position == host.points[1].position
    assert host.points[4].position == host.points[3].position


def test_stationary_tic_carrier_does_not_hide_its_team_inside() -> None:
    s = scenario()
    for host, _ in s.groups:
        host.points[:] = host.points[:1]
    generate(s)
    assert all("mount" not in (host.points[0].name or "") for host, _ in s.groups)


def test_no_remote_terrain_snap_for_team_positions() -> None:
    s = scenario()
    origin = s.groups[0][0].points[0].position
    s.gen.conflict.theater.is_on_land = lambda p: p.distance_to_point(origin) < 0.01
    position = s.gen._manpad_position(s.groups[0][0], [origin])
    assert position is origin


def test_round_trip_miz_contains_two_teams_and_their_tic_hosts(tmp_path: Path) -> None:
    s = scenario()
    generate(s)
    output = tmp_path / "teams.miz"
    s.mission.save(output)
    with ZipFile(output) as archive:
        mission = loads(archive.read("mission").decode())["mission"]
    groups = [
        g
        for country in mission["coalition"]["red"]["country"].values()
        for g in country.get("vehicle", {}).get("group", {}).values()
    ]
    teams = [g for g in groups if "#SUPPORT" in g["name"]]
    assert len(teams) == 4
    assert sum(g["units"][1]["type"] == "SA-18 Igla manpad" for g in teams) == 2
    for g in teams:
        assert g["lateActivation"] and g["hiddenOnMFD"]
        assert g["name"].split("#")[0] in {parent["name"] for parent in groups}


def test_old_settings_keep_manpads_off_and_get_the_default_ratio() -> None:
    settings = object.__new__(Settings)
    settings.__setstate__({"manpads": False, "perf_infantry": False})
    assert settings.manpads is False and settings.perf_infantry is False
    assert settings.frontline_manpad_vehicles_per_team == 8
    settings.__setstate__({"frontline_manpad_vehicles_per_team": 16})
    assert settings.frontline_manpad_vehicles_per_team == 16


def test_complete_generation_assigns_each_side_after_planning_routes() -> None:
    s = scenario()
    s.gen.conflict.blue_cp = NS()
    s.gen.conflict.red_cp = NS()
    s.gen.conflict.front_line = NS()
    s.gen.game.theater = NS()
    s.gen.game.blue = NS(faction=NS(has_jtac=False))
    s.settings.use_jtac = False
    s.gen.player_stance = CombatStance.DEFENSIVE
    s.gen.enemy_stance = CombatStance.AGGRESSIVE
    s.gen.player_planned_combat_groups = []
    s.gen.enemy_planned_combat_groups = []
    blue, red = [s.groups[0]], [s.groups[1]]
    s.gen._generate_groups = Mock(side_effect=[blue, red])
    events: list[object] = []
    s.gen.plan_action_for_groups = Mock(
        side_effect=lambda *args: events.append("route")
    )
    s.gen.gen_manpad_teams = Mock(
        side_effect=lambda groups, side: events.append((groups, side))
    )
    with patch(
        "game.missiongenerator.flotgenerator.FrontLineConflictDescription.frontline_position"
    ):
        s.gen.generate()
    assert events == ["route", "route", (blue, Player.BLUE), (red, Player.RED)]


def test_inventory_manpads_are_deployed_and_not_reported_as_reserves() -> None:
    manpad = unit(UnitClass.MANPAD)
    enemy = NS(id=uuid4(), captured=False)
    cp: Any = NS(
        id=uuid4(),
        captured=True,
        name="BASE",
        connected_points=[enemy],
        frontline_unit_count_limit=10,
        base=NS(total_armor=2, armor={manpad: 2}),
        stances={enemy.id: CombatStance.DEFENSIVE},
    )
    planner = GroundPlanner(cp, NS())  # type: ignore[arg-type]
    planner.plan_groundwar()
    groups = planner.units_per_cp[enemy.id]
    assert len(groups) == 2
    assert all(
        g.unit_type is manpad and g.role is CombatGroupRole.SHORAD for g in groups
    )
    assert deployable_armor(cp) == {manpad: 2}
    assert reserve_armor_for(cp) == {}


@pytest.mark.parametrize(
    "name",
    ["Infantry M4", "Infantry AK-74 Rus", "Paratrooper AKS", "[CH] M4 AR Soldier"],
)
def test_rifleman_data_is_explicit(name: str) -> None:
    assert GroundUnitType.named(name).is_rifleman
    assert not GroundUnitType.named('MANPADS SA-18 Igla "Grouse"').is_rifleman
