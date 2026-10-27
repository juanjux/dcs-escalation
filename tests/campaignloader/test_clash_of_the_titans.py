"""Clash of the Titans has reachable, redundant infrastructure for both sides."""

from collections import Counter
from copy import deepcopy
from dataclasses import fields
from datetime import datetime
import json
from pathlib import Path
import random
from typing import Any, Iterator
from zipfile import ZipFile

from dcs.lua import loads
import pytest

from game import Game, persistency
from game.ato.closestairfields import ObjectiveDistanceCache
from game.campaignloader.campaign import Campaign
from game.factions import Faction
from game.naming import namegen
from game.settings import Settings
from game.theater import Player
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, IadsStateMap
from game.theater.start_generator import GameGenerator, GeneratorSettings, ModSettings
from game.theater.theatergroundobject import IadsGroundObject, MotorpoolGroundObject

CAMPAIGN = Path("resources/campaigns/clash_of_the_titans.yaml")
IADS_KINDS = {
    "long_range_sams",
    "medium_range_sams",
    "short_range_sams",
    "aaa",
    "ewrs",
    "iads_command_center",
}


@pytest.fixture(scope="module")
def authored() -> Any:
    campaign = Campaign.from_file(CAMPAIGN)
    theater = campaign.load_theater(campaign.advanced_iads)
    placements = {
        point.original_name: (cp, kind, point)
        for cp in theater.controlpoints
        for kind, locations in vars(cp.preset_locations).items()
        if isinstance(locations, list)
        for point in locations
        if hasattr(point, "original_name")
    }
    config = {
        name: links
        for entry in campaign.data["iads_config"]
        for name, links in entry.items()
    }
    return campaign, theater, placements, config


def test_campaign_recommends_modern_factions_and_enables_its_features(
    authored: Any,
) -> None:
    campaign, _, _, _ = authored
    assert campaign.is_compatible
    assert campaign.recommended_player_faction == "USA 2020"
    assert campaign.recommended_enemy_faction == "Redfor (Russia) 2020"
    assert campaign.recommended_start_date.year == 2020
    assert campaign.advanced_iads
    assert campaign.settings["motorpool_enabled"]
    assert campaign.settings["plugins"]["skynetiads"]
    assert campaign.settings["plugins"]["gpsjamming"]


def test_every_base_has_a_depot_clear_of_all_capture_zones(authored: Any) -> None:
    _, theater, _, _ = authored
    assert len(theater.controlpoints) == 14
    for cp in theater.controlpoints:
        assert len(cp.preset_locations.motorpools) == 1, cp.name
        point = cp.preset_locations.motorpools[0]
        assert theater.is_on_land(point, ignore_exclusion=True)
        assert all(
            point.distance_to_point(other.position) > 4000
            for other in theater.controlpoints
        ), cp.name


def test_all_active_air_defences_and_commands_have_redundant_local_links(
    authored: Any,
) -> None:
    _, _, placements, config = authored
    expected = {
        name
        for name, (cp, kind, _) in placements.items()
        if kind in IADS_KINDS and not cp.starting_coalition.is_neutral
    }
    assert set(config) == expected
    for name, links in config.items():
        cp, kind, point = placements[name]
        counts: Counter[str] = Counter()
        assert len(links) == len(set(links)), name
        for dependency in links:
            source_cp, source_kind, source = placements[dependency]
            assert source_cp.starting_coalition is cp.starting_coalition
            counts[source_kind] += 1
            if source_kind == "iads_connection_node":
                assert point.distance_to_point(source) <= 15 * 1852, (name, dependency)
            elif source_kind == "iads_power_source":
                assert point.distance_to_point(source) <= 35 * 1852, (name, dependency)
            else:
                assert source_kind == "iads_command_center"
        assert counts["iads_connection_node"] >= 2, name
        assert counts["iads_power_source"] >= 2, name
        if kind != "iads_command_center":
            assert counts["iads_command_center"] == 2, name


def test_infrastructure_is_on_land_and_owned_by_its_named_side(authored: Any) -> None:
    _, theater, placements, _ = authored
    counts: Counter[Player] = Counter()
    for name, (cp, kind, point) in placements.items():
        if kind not in {
            "iads_connection_node",
            "iads_power_source",
            "iads_command_center",
        }:
            continue
        assert theater.is_on_land(point, ignore_exclusion=True), name
        side = Player.BLUE if name.startswith("Blue ") else Player.RED
        assert cp.starting_coalition is side, name
        if kind == "iads_command_center":
            counts[side] += 1
    assert counts == {Player.BLUE: 2, Player.RED: 2}


def test_jammers_do_not_replace_the_original_early_warning_radars(
    authored: Any,
) -> None:
    campaign, _, placements, _ = authored
    pins = campaign.data["ground_forces"]
    assert len(pins) == 8
    for side in ("Blue", "Red"):
        matching = [name for name in pins if name.startswith(side)]
        assert len(matching) == 4
        for name in matching:
            assert placements[name][1] == "ewrs"
            assert pins[name] == f"GPS Jamming Site ({side})"
    for original in ("Ground-68", "Ground-69", "Ground-70", "Ground-71"):
        assert placements[original][1] == "ewrs"
        assert original not in pins


def test_mission_ids_and_group_names_remain_unique() -> None:
    with ZipFile(CAMPAIGN.with_suffix(".miz")) as archive:
        mission = loads(archive.read("mission").decode())["mission"]
    groups = [
        group
        for side in ("blue", "red", "neutrals")
        for country in mission.get("coalition", {})
        .get(side, {})
        .get("country", {})
        .values()
        for category in ("static", "vehicle", "plane", "helicopter", "ship")
        for group in country.get(category, {}).get("group", {}).values()
    ]
    names = [group["name"] for group in groups]
    group_ids = [group["groupId"] for group in groups]
    unit_ids = [unit["unitId"] for group in groups for unit in group["units"].values()]
    assert len(names) == len(set(names))
    assert len(group_ids) == len(set(group_ids))
    assert len(unit_ids) == len(set(unit_ids))


@pytest.fixture(scope="module", params=[False, True], ids=["stock", "mods"])
def generated(request: pytest.FixtureRequest, tmp_path_factory: Any) -> Iterator[Game]:
    campaign = Campaign.from_file(CAMPAIGN)
    theater = campaign.load_theater(True)
    settings = Settings()
    settings.__dict__.update(Settings.deserialize_state_dict(campaign.settings))
    mods = (
        ModSettings(
            **{
                field.name: bool(campaign.settings.get(field.name, False))
                for field in fields(ModSettings)
            }
        )
        if request.param
        else ModSettings()
    )
    assert campaign.recommended_start_date is not None
    random_state = random.getstate()
    names = {
        key: deepcopy(value)
        for key, value in vars(namegen).items()
        if isinstance(value, (int, list))
    }
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            persistency, "_dcs_saved_game_folder", str(tmp_path_factory.mktemp("clash"))
        )
        patch.setattr(ObjectiveDistanceCache, "theater", ObjectiveDistanceCache.theater)
        patch.setattr(ObjectiveDistanceCache, "closest_airfields", {})
        random.seed(17)
        try:
            options = GeneratorSettings(
                start_date=datetime.combine(
                    campaign.recommended_start_date, datetime.min.time()
                ),
                start_time=None,
                player_budget=2000,
                enemy_budget=2000,
                inverted=False,
                advanced_iads=True,
                no_carrier=True,
                no_lha=True,
                no_player_navy=True,
                no_enemy_navy=True,
                tgo_config=campaign.load_ground_forces_config(),
                carrier_config=campaign.load_carrier_config(),
                squadrons_start_full=False,
            )
            blue = Faction.from_dict(
                json.loads(Path("resources/factions/usa_2020.json").read_text())
            )
            red = Faction.from_dict(
                json.loads(
                    Path("resources/factions/redfor_russia_2020.json").read_text()
                )
            )
            game = GameGenerator(
                blue,
                red,
                theater,
                campaign.load_air_wing_config(theater),
                settings,
                options,
                mods,
                campaign.name,
            ).generate()
            theater.iads_network.initialize_network(theater.ground_objects)
            yield game
        finally:
            random.setstate(random_state)
            for key, value in names.items():
                setattr(namegen, key, value)


def test_generated_network_is_operational_and_exports_to_skynet(
    generated: Game,
) -> None:
    network = generated.theater.iads_network
    owned = [
        (site, status)
        for site, status in network.state_map
        if not site.control_point.captured.is_neutral
    ]
    assert len(owned) == 45
    assert all(status.state is IadsState.NETWORKED for _, status in owned)
    assert len(network.skynet_nodes(generated)) == 45
    for cp in generated.theater.controlpoints:
        assert (
            sum(isinstance(tgo, MotorpoolGroundObject) for tgo in cp.ground_objects)
            == 1
        )


def test_generated_jammers_are_real_jammers_and_radars_still_detect(
    generated: Game,
) -> None:
    sites = {tgo.original_name: tgo for tgo in generated.theater.ground_objects}
    jammers = [
        tgo
        for name, tgo in sites.items()
        if isinstance(tgo, IadsGroundObject) and " GPS Jammer " in name
    ]
    assert len(jammers) == 8
    assert all(tgo.carries_gps_jammer for tgo in jammers)
    for name in ("Ground-68", "Ground-69", "Ground-70", "Ground-71"):
        radar = sites[name]
        assert isinstance(radar, IadsGroundObject)
        assert not radar.carries_gps_jammer
        assert radar.max_detection_range().meters > 0


def test_losing_one_infrastructure_object_does_not_break_the_network(
    generated: Game,
) -> None:
    network = generated.theater.iads_network
    infrastructure = [
        tgo
        for tgo in generated.theater.ground_objects
        if tgo.category in ("comms", "power", "commandcenter")
    ]
    assert len(infrastructure) == 50
    for lost in infrastructure:
        picture = IadsStateMap(network, [lost])
        assert all(
            status.state is IadsState.NETWORKED
            for site, status in picture
            if site is not lost and not site.control_point.captured.is_neutral
        ), lost.original_name


def test_destroying_all_local_comms_still_cuts_a_sam_off(generated: Game) -> None:
    network = generated.theater.iads_network
    sam = next(
        tgo
        for tgo in generated.theater.ground_objects
        if tgo.original_name == "Ground-13"
    )
    node = next(node for node in network.nodes if node.group.ground_object is sam)
    towers = [
        group.ground_object
        for group in node.connections.values()
        if group.iads_role is IadsRole.CONNECTION_NODE
    ]
    status = IadsStateMap(network, towers).status_for(sam)
    assert status is not None and status.state is IadsState.AUTONOMOUS


def test_destroying_both_command_centres_removes_direction(generated: Game) -> None:
    network = generated.theater.iads_network
    commands = [
        node.group.ground_object
        for node in network.nodes
        if node.group.iads_role is IadsRole.COMMAND_CENTER
        and node.group.ground_object.control_point.captured is Player.RED
    ]
    sam = next(
        tgo
        for tgo in generated.theater.ground_objects
        if tgo.original_name == "Ground-13"
    )
    status = IadsStateMap(network, commands).status_for(sam)
    assert status is not None and status.state is IadsState.AUTONOMOUS


def test_destroying_a_jammers_whole_power_grid_disables_it(generated: Game) -> None:
    network = generated.theater.iads_network
    jammer = next(
        tgo
        for tgo in generated.theater.ground_objects
        if tgo.original_name == "Red GPS Jammer Bastion"
    )
    node = next(node for node in network.nodes if node.group.ground_object is jammer)
    power = [
        group.ground_object
        for group in node.connections.values()
        if group.iads_role is IadsRole.POWER_SOURCE
    ]
    status = IadsStateMap(network, power).status_for(jammer)
    assert status is not None and status.state is IadsState.DARK


def test_each_jammer_protects_at_least_one_friendly_air_defence(
    generated: Game,
) -> None:
    sites = list(generated.theater.ground_objects)
    for jammer in (tgo for tgo in sites if " GPS Jammer " in tgo.original_name):
        assert any(
            target is not jammer
            and target.control_point.captured is jammer.control_point.captured
            and isinstance(target, IadsGroundObject)
            and not target.carries_gps_jammer
            and target.max_threat_range().meters > 0
            and target.position.distance_to_point(jammer.position) < 15 * 1852
            for target in sites
        ), jammer.original_name
