"""Whole SAM batteries keep their identities and go offline while relocating."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import pickle
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from zipfile import ZipFile

from dcs import Mission, Point
from dcs.lua import loads
from dcs.task import OptAlarmState, OptROE
import pytest
import yaml

from game.dcs.groundunittype import GroundUnitType
from game.groundmovement.dispatch import advance_armor, dispatch_armor, stop_armor
from game.groundmovement.mobility import GroundMobility, MobilityMode
from game.groundmovement.orders import DestinationKind, GroundPosition, MovementSource
from game.groundmovement.planning import (
    armor_movement_options,
    movement_destination,
    preview_armor_movement,
)
from game.groundmovement.report import movement_reports
from game.groundmovement.settings import set_enabled
from game.point_with_heading import PointWithHeading
from game.missiongenerator.realisticcasluadata import collect_registry
from game.missiongenerator.tgogenerator import GroundObjectGenerator
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import EwrGroundObject, SamGroundObject
from game.theater.theatergroup import IadsGroundGroup, TheaterUnit
from game.utils import Heading
from game.unitmap import UnitMap
from tests.test_armor_movement_dispatch import native, prepare
from tests.test_armor_movement_planning import world  # noqa: F401

KUB = ('SAM SA-6 Kub "Straight Flush" STR', 'SAM SA-6 Kub "Gainful" TEL')
PATRIOT = ("SAM Patriot STR", "SAM Patriot LN", "Truck Ural-375", "Truck Ural-375")


def not_culled(_tgo: Any) -> bool:
    return False


def make_site(world: Any, names: tuple[str, ...] = KUB, *, radar: bool = False) -> Any:
    prepare(world)
    terrain = world.game.theater.terrain
    location = PresetLocation("SAM", Point(10, 10, terrain))
    site = (
        EwrGroundObject("SAM", location, world.a)
        if radar
        else SamGroundObject("SAM", location, world.a, None)
    )
    units = [
        TheaterUnit(
            100 + i,
            name,
            GroundUnitType.named(name).dcs_unit_type,
            PointWithHeading(10 + i * 4, 10 + i * 6, Heading.from_degrees(90), terrain),
            site,
        )
        for i, name in enumerate(names)
    ]
    for group_id, group_units in enumerate((units[:2], units[2:]), 200):
        if not group_units:
            continue
        group = IadsGroundGroup(
            group_id,
            f"SAM-{group_id}",
            PointWithHeading.from_point(site.position, Heading.from_degrees(90)),
            group_units,
            site,
        )
        group.iads_role = IadsRole.EWR if radar else IadsRole.SAM
        site.groups.append(group)
    world.a.connected_objectives.append(site)
    world.game.db.tgos.add(site.id, site)
    world.game.theater.iads_network = IadsNetwork(False, [])
    world.game.theater.iads_network.initialize_network(iter([site]))
    world.game.iads_considerate_culling = not_culled
    world.game.skynet_culled = not_culled
    for cp in world.game.theater.controlpoints:
        cp.coalition.game = world.game
    world.sam = site
    world.destination = movement_destination(
        world.game,
        world.a.captured,
        DestinationKind.POSITION,
        position=GroundPosition(90, 10),
    )
    return site


def selected(world: Any) -> list[int]:
    return [unit.id for unit in world.sam.units if unit.alive]


def move(world: Any) -> Any:
    return dispatch_armor(
        world.game,
        world.sam.id,
        world.a.captured,
        selected(world),
        world.destination,
        GameUpdateEvents(),
    )


def test_mobile_battery_preview_is_read_only_and_requires_the_whole_site(
    world: Any,
) -> None:
    site = make_site(world)
    before = pickle.dumps(world.game)
    options = armor_movement_options(world.game, site.id, Player.BLUE)
    assert options.enabled and options.towed_pieces == options.available_tractors == 0
    preview = preview_armor_movement(
        world.game, site.id, Player.BLUE, selected(world), world.destination
    )
    assert preview.manifest.unit_ids == (100, 101)
    assert preview.remaining_unit_ids == () and preview.manifest.towing == ()
    with pytest.raises(ValueError, match="every surviving unit"):
        preview_armor_movement(
            world.game, site.id, Player.BLUE, [100], world.destination
        )
    assert pickle.dumps(world.game) == before


@pytest.mark.parametrize("kind", [DestinationKind.BASE, DestinationKind.FRONTLINE])
def test_battery_cannot_be_absorbed_into_base_inventory(
    world: Any, kind: DestinationKind
) -> None:
    site = make_site(world)
    target = movement_destination(
        world.game,
        Player.BLUE,
        kind,
        base_id=world.a.id,
        opposing_base_id=world.enemy.id if kind is DestinationKind.FRONTLINE else None,
    )
    with pytest.raises(ValueError, match="cannot join bases or fronts"):
        preview_armor_movement(
            world.game, site.id, Player.BLUE, selected(world), target
        )
    assert not world.game.ground_movements.orders


def test_towed_battery_requires_one_organic_tractor_per_piece(world: Any) -> None:
    site = make_site(world, PATRIOT[:-1])
    options = armor_movement_options(world.game, site.id, Player.BLUE)
    assert (
        not options.enabled
        and options.towed_pieces == 2
        and options.available_tractors == 1
    )
    assert any(
        "entire battery needs transport" in warning for warning in options.warnings
    )
    with pytest.raises(ValueError, match="only 1"):
        move(world)
    assert not world.game.ground_movements.orders and not site.in_transit


@pytest.mark.parametrize("reason", ["fixed", "unknown", "repair", "reserved"])
def test_unsupported_or_unavailable_battery_cannot_be_partially_relocated(
    world: Any, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    site = make_site(world)
    unit = next(iter(site.units))
    if reason in ("fixed", "unknown"):
        original = GroundUnitType.named(KUB[0])
        changed = replace(
            original, ground_mobility=GroundMobility(MobilityMode(reason))
        )
        registry = GroundUnitType._by_name
        monkeypatch.setitem(registry, KUB[0], changed)
        unit.ground_unit_variant = KUB[0]
    elif reason == "repair":
        unit.repair_turns_remaining = 1
    else:
        world.game.ground_movements.plan(
            world.game.settings,
            source_id=world.source.id,
            source_kind=MovementSource.ARMOR,
            owner=Player.BLUE,
            origin=GroundPosition(0, 0),
            destination=world.destination,
            units={unit.id: unit.unit_type},
            selected=[unit.id],
            turn=1,
        )
    assert not armor_movement_options(world.game, site.id, Player.BLUE).enabled
    with pytest.raises(ValueError):
        move(world)
    assert not site.in_transit


@pytest.mark.parametrize("radar", [False, True])
def test_same_site_and_units_are_offline_in_transit_and_redeploy_on_arrival(
    world: Any, radar: bool
) -> None:
    site = make_site(world, radar=radar)
    network = world.game.theater.iads_network
    before_units = list(site.units)
    before_groups = list(site.groups)
    assert site.max_detection_range().meters > 0
    assert network.skynet_nodes(world.game)
    transit = move(world)
    assert transit.detachment_id == site.id
    assert (
        world.game.ground_movements.orders[transit.order_id].source_kind
        is MovementSource.SAM
    )
    assert list(site.units) == before_units and site.groups == before_groups
    assert site.in_transit and not site.purchasable and not site.sellable
    assert site.max_threat_range().meters == site.max_detection_range().meters == 0
    assert all(
        unit.detection_range.meters == unit.threat_range.meters == 0
        for unit in site.units
    )
    assert network.skynet_nodes(world.game) == []
    assert network.state_map.status_for(site).state is IadsState.DARK
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished and not site.in_transit and site.purchasable
    assert site.position.x == 90 and site.position.y == 10
    assert all(unit.ground_object is site for unit in site.units)
    assert list(site.units) == before_units and site.groups == before_groups
    assert site.max_detection_range().meters > 0 and network.skynet_nodes(world.game)
    assert network.state_map.status_for(site).state is not IadsState.DARK
    assert not world.b.base.armor and not world.game.ground_movements.reserved_unit_ids


def test_arrival_keeps_multigroup_layout_not_native_convoy_column(world: Any) -> None:
    site = make_site(world, PATRIOT)
    units = list(site.units)
    original = {
        u.id: (u.position.x - site.position.x, u.position.y - site.position.y)
        for u in units
    }
    group_ids = [g.id for g in site.groups]
    transit = move(world)
    transit.arrival_positions = {
        u.id: GroundPosition(500, 500 + i) for i, u in enumerate(units)
    }
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert [g.id for g in site.groups] == group_ids
    for unit in units:
        assert (
            unit.position.x - site.position.x,
            unit.position.y - site.position.y,
        ) == original[unit.id]
        assert unit.transported_by_id is None


@pytest.mark.parametrize("paused", [False, True])
def test_native_towed_battery_is_an_attackable_truck_convoy_without_radar_or_fire(
    world: Any, paused: bool
) -> None:
    site = make_site(world, PATRIOT)
    transit = move(world)
    if paused:
        set_enabled(world.game.settings, False)
    group, unit_map = native(world, transit)
    assert {u.type for u in group.units} == {"Ural-375"} and len(group.units) == 2
    assert len(group.points) == 1 if paused else len(group.points) > 1
    assert len(unit_map.ground_transport_cargo) == 2
    tasks = group.points[0].tasks
    assert [
        task.params["action"]["params"]["value"]
        for task in tasks
        if isinstance(task, OptAlarmState)
    ] == [1]
    assert [
        task.params["action"]["params"]["value"]
        for task in tasks
        if isinstance(task, OptROE)
    ] == [OptROE.Values.WeaponHold]
    assert len(list(site.units)) == 4


def test_lost_tractor_also_loses_its_loaded_piece_before_arrival(world: Any) -> None:
    site = make_site(world, PATRIOT)
    transit = move(world)
    units = {unit.id: unit for unit in site.units}
    units[102].kill(GameUpdateEvents())
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert not units[100].alive and not units[102].alive
    assert units[101].alive and units[103].alive
    assert transit.finished and not site.in_transit
    assert movement_reports(world.game, site.id, Player.BLUE)[0].surviving_units == 2


def test_total_loss_finishes_order_and_keeps_a_destroyed_rebuildable_site(
    world: Any,
) -> None:
    site = make_site(world)
    transit = move(world)
    for unit in site.units:
        unit.kill(GameUpdateEvents())
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert (
        transit.finished and not site.in_transit and site.is_dead and site.purchasable
    )
    assert movement_reports(world.game, site.id, Player.BLUE)[0].status == "lost"
    assert (
        world.game.theater.iads_network.state_map.status_for(site).state
        is IadsState.DESTROYED
    )


def test_stale_preview_cannot_dispatch_a_battery_after_tractor_loss(world: Any) -> None:
    site = make_site(world, PATRIOT)
    preview_armor_movement(
        world.game, site.id, Player.BLUE, selected(world), world.destination
    )
    list(site.units)[-1].kill(GameUpdateEvents())
    with pytest.raises(ValueError, match="only 1"):
        move(world)
    assert not site.in_transit and not world.game.ground_movements.orders


def generate_site(world: Any) -> tuple[Mission, UnitMap]:
    mission = Mission()
    mission.terrain = world.game.theater.terrain
    country = mission.country("USA")
    world.a.coalition.faction = SimpleNamespace(country=country)
    world.game.settings.set_plugin_option("skynetiads", False)
    mapping = UnitMap()
    generator = GroundObjectGenerator(world.sam, country, world.game, mission, mapping)
    with patch("game.missiongenerator.tgogenerator.GroundForcePainter"), patch(
        "game.missiongenerator.tgogenerator.shows_on_mfd", return_value=True
    ):
        generator.generate()
    return mission, mapping


@pytest.mark.parametrize("names", [KUB, PATRIOT])
def test_exported_miz_keeps_surviving_vehicles_offline_and_redeploys_after_arrival(
    world: Any, tmp_path: Path, names: tuple[str, ...]
) -> None:
    site = make_site(world, names)
    transit = move(world)
    mission, _mapping = generate_site(world)
    output = tmp_path / "sam-transit.miz"
    mission.save(output)
    with ZipFile(output) as archive:
        data = loads(archive.read("mission").decode())["mission"]
    groups = [
        g
        for country in data["coalition"]["blue"]["country"].values()
        for g in country.get("vehicle", {}).get("group", {}).values()
    ]
    assert len(groups) == 1
    assert len(groups[0]["units"]) == 2 and len(groups[0]["route"]["points"]) > 1
    options = [
        task["params"]["action"]["params"]
        for task in groups[0]["route"]["points"][1]["task"]["params"]["tasks"].values()
        if task["params"].get("action", {}).get("id") == "Option"
    ]
    assert {"name": 9, "value": 1} in options
    assert {"name": 0, "value": 4} in options
    assert not groups[0].get("lateActivation", False)
    world.game.turn += 1
    advance_armor(world.game, GameUpdateEvents())
    assert transit.finished
    restored, _mapping = generate_site(world)
    deployed = restored.country("USA").vehicle_group
    assert len(deployed) == len(site.groups)
    assert sum(len(group.units) for group in deployed) == len(names)
    assert {u.name for group in deployed for u in group.units} == {
        u.unit_name for u in site.units
    }


def test_realistic_cas_does_not_avoid_a_packed_mobile_sam(world: Any) -> None:
    make_site(world)
    data: Any = SimpleNamespace(flights=[], jtacs=[])
    deployed, deployed_map = generate_site(world)
    before = collect_registry(deployed, data, enabled=True, unit_map=deployed_map)
    assert before is not None and before["airDefenseThreats"]
    transit = move(world)
    moving, moving_map = generate_site(world)
    registry = collect_registry(moving, data, enabled=True, unit_map=moving_map)
    assert registry is not None and registry["airDefenseThreats"] == []
    assert len(registry["afacKnownTargets"]) == 2
    stop_armor(world.game, transit.order_id, Player.BLUE, GameUpdateEvents())
    stationary, stationary_map = generate_site(world)
    after = collect_registry(stationary, data, enabled=True, unit_map=stationary_map)
    assert after is not None and after["airDefenseThreats"]


def test_save_reload_stop_and_second_move_preserve_the_site(world: Any) -> None:
    site = make_site(world, PATRIOT)
    transit = move(world)
    restored = pickle.loads(pickle.dumps(world.game))
    loaded_site = restored.db.tgos.get(site.id)
    loaded_transit = restored.ground_movements.transits[transit.order_id]
    assert loaded_site.in_transit
    assert restored.theater.iads_network.skynet_nodes(restored) == []
    stop_armor(restored, loaded_transit.order_id, Player.BLUE, GameUpdateEvents())
    assert not loaded_site.in_transit and loaded_site.position == site.position
    assert all(u.transported_by_id is None for u in loaded_site.units)
    second = dispatch_armor(
        restored,
        site.id,
        Player.BLUE,
        selected(world),
        world.destination,
        GameUpdateEvents(),
    )
    assert second.detachment_id == site.id and second.order_id != transit.order_id
    reports = movement_reports(restored, site.id, Player.BLUE)
    assert reports[0].status == "stopped" and reports[0].surviving_units == 4
    assert reports[1].status == "moving"


@pytest.mark.parametrize(
    "filename,mode",
    [
        ("Patriot ln", MobilityMode.TOWED),
        ("Patriot str", MobilityMode.TOWED),
        ("Patriot ECS", MobilityMode.SELF_PROPELLED),
        ("Patriot EPP", MobilityMode.SELF_PROPELLED),
        ("NASAMS_LN_C", MobilityMode.TOWED),
        ("Hawk ln", MobilityMode.TOWED),
        ("CH_MIM104_M903_PAC2", MobilityMode.TOWED),
        ("CH_MIM104_M903_PAC2_HEMTT", MobilityMode.SELF_PROPELLED),
        ("CH_THAAD_ANTPY2", MobilityMode.SELF_PROPELLED),
        ("SA-11 Buk LN 9A310M1", MobilityMode.SELF_PROPELLED),
        ("CH_BukM3_9S36M", MobilityMode.SELF_PROPELLED),
        ("S-300PS 40B6M MAST tr", MobilityMode.TOWED),
        ("S-200_Launcher", MobilityMode.FIXED),
    ],
)
def test_reviewed_data_distinguishes_trailers_from_vehicle_weapon_pairs(
    filename: str, mode: MobilityMode
) -> None:
    path = Path("resources/units/ground_units") / f"{filename}.yaml"
    mobility = GroundMobility.from_data(
        yaml.safe_load(path.read_text(encoding="utf-8"))["ground_mobility"]
    )
    assert mobility.mode is mode and not mobility.can_tow
