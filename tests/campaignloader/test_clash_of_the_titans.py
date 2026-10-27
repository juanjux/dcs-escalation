"""Clash of the Titans retains usable forces, supply and redundant infrastructure."""

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
from game.ato.flighttype import FlightType
from game.campaignloader.campaign import Campaign
from game.dcs.afaccapabilities import capabilities_for
from game.factions import Faction
from game.naming import namegen
from game.settings import Settings
from game.theater import Player
from game.theater.controlpoint import ParkingType
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
    assert campaign.settings["squadrons_start_full"]
    assert "squadron_start_full" not in campaign.settings


def test_ground_axis_is_supplied_without_connecting_air_assault_objectives(
    authored: Any,
) -> None:
    _, theater, _, _ = authored
    expected = {
        frozenset(pair)
        for pair in (
            ("Bagram", "Kabul"),
            ("Kabul", "Ghazni Heliport"),
            ("Ghazni Heliport", "FOB Lagman"),
            ("FOB Lagman", "Kandahar Heliport"),
            ("Kandahar Heliport", "Camp Bastion"),
        )
    }
    actual = {
        frozenset((cp.name, other.name))
        for cp in theater.controlpoints
        for other in cp.connected_points
    }
    assert actual == expected
    assert {cp.name for cp in theater.controlpoints if cp.is_isolated} == {
        "Kandahar",
        "Tarinkot",
        "Sharana",
        "Camp Bastion Heliport",
        "FOB Zeebrugge",
        "FOB Nawa",
        "FOB Khayr Kot Castle",
        "FOB Frontenac",
    }
    for cp in theater.controlpoints:
        assert len(cp.connected_points) == len(set(cp.connected_points))
        for other, route in cp.convoy_routes.items():
            assert cp is not other
            assert route == tuple(reversed(other.convoy_routes[cp]))
            assert all(a.distance_to_point(b) > 0 for a, b in zip(route, route[1:]))
            assert theater.closest_control_point(route[0]) is cp
            assert theater.closest_control_point(route[-1]) is other
            assert len(cp.convoy_spawns[other]) >= 60


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


def test_generated_squadrons_match_the_template_and_fit_their_bases(
    generated: Game,
) -> None:
    campaign = Campaign.from_file(CAMPAIGN)
    config = campaign.load_air_wing_config(generated.theater)
    assert sum(1 for cp in generated.theater.controlpoints for _ in cp.squadrons) == 69
    for cp, definitions in config.by_location.items():
        expected: Counter[tuple[Any, str, int]] = Counter()
        for definition in definitions:
            preferred = next(
                name
                for name in definition.aircraft
                if any(a.variant_id == name for a in cp.coalition.faction.all_aircrafts)
            )
            expected[definition.primary, preferred, definition.max_size] += 1
        actual = Counter(
            (s.primary_task, s.aircraft.variant_id, s.max_size) for s in cp.squadrons
        )
        assert actual == expected, cp.name
        assert sum(s.max_size for s in cp.squadrons) <= cp.total_aircraft_parking(
            ParkingType(True, True, True)
        ), cp.name
        for squadron in cp.squadrons:
            assert cp.can_operate(squadron.aircraft), squadron.aircraft
            assert squadron.aircraft.capable_of(
                squadron.primary_task
            ), squadron.aircraft
            assert squadron.pilot_limit == squadron.max_size + 4


def test_every_airframe_can_have_a_compatible_native_parking_slot(
    generated: Game,
) -> None:
    for cp in generated.theater.controlpoints:
        if not hasattr(cp, "airport"):
            continue
        candidates = [
            [
                slot.crossroad_idx
                for slot in cp.airport.free_parking_slots(s.aircraft.dcs_unit_type)
            ]
            for s in cp.squadrons
            for _ in range(s.max_size)
        ]
        # Shared pads can fit either a helicopter or a fighter, not both. Match
        # every airframe to one distinct, dimension-compatible native DCS slot.
        candidates.sort(key=len)
        occupied: dict[int, int] = {}

        def assign(airframe: int, seen: set[int]) -> bool:
            for slot in candidates[airframe]:
                if slot in seen:
                    continue
                seen.add(slot)
                if slot not in occupied or assign(occupied[slot], seen):
                    occupied[slot] = airframe
                    return True
            return False

        for airframe in range(len(candidates)):
            assert assign(airframe, set()), (cp.name, airframe, candidates[airframe])


def test_no_runway_holds_half_the_fleet_or_all_critical_support(
    generated: Game,
) -> None:
    for coalition, limit in ((generated.blue, 46), (generated.red, 70)):
        wing = list(coalition.air_wing.iter_squadrons())
        by_base: Counter[Any] = Counter()
        for squadron in wing:
            by_base[squadron.location] += squadron.max_size
        assert max(by_base.values()) <= limit
        for task in (FlightType.AEWC, FlightType.REFUELING, FlightType.TRANSPORT):
            sources = {s.location for s in wing if s.primary_task is task}
            assert len(sources) >= 2, task
        for task, names in (
            (
                FlightType.ESCORT,
                {"F-22A Raptor", "F-15C Eagle", "Su-57 Felon", "Su-30 Flanker-C"},
            ),
            (FlightType.CAS, {"A-10C Thunderbolt II (Suite 7)"}),
            (FlightType.SEAD, {"F/A-18C Hornet (Lot 20)"}),
        ):
            assigned = [
                s
                for s in wing
                if s.primary_task is task and s.aircraft.variant_id in names
            ]
            if assigned:
                assert len({s.location for s in assigned}) >= 2, names


def test_each_side_can_supply_its_ground_front_from_a_factory(generated: Game) -> None:
    for coalition in (generated.blue, generated.red):
        bases = list(generated.theater.control_points_for(coalition.player))
        front_bases = [
            cp
            for cp in bases
            if any(
                not other.captured.is_neutral and other.captured is not coalition.player
                for other in cp.connected_points
            )
        ]
        assert front_bases
        for cp in front_bases:
            accessible = {cp, *cp.transitive_connected_friendly_points()}
            assert any(source.has_factory for source in accessible), cp.name
    # Retain the original economy apart from the additional $10M axis factory.
    from game.income import Income

    assert Income(generated, Player.BLUE).total == 162.5
    assert Income(generated, Player.RED).total == 206.5
    bastion = generated.theater.control_point_named("Camp Bastion")
    heliport = generated.theater.control_point_named("Camp Bastion Heliport")
    assert bastion.has_factory
    assert heliport.has_factory
    assert heliport.is_isolated


def test_both_sides_have_transport_and_afac_capable_squadrons(generated: Game) -> None:
    for coalition in (generated.blue, generated.red):
        squadrons = list(coalition.air_wing.iter_squadrons())
        for task in (
            FlightType.TRANSPORT,
            FlightType.AIR_ASSAULT,
            FlightType.AFAC_AREA,
            FlightType.AFAC_FRONTLINE,
        ):
            assert any(s.aircraft.capable_of(task) for s in squadrons), (
                coalition.player,
                task,
            )


def test_support_and_air_assault_are_not_missing_or_assigned_to_combat(
    generated: Game,
) -> None:
    for coalition in (generated.blue, generated.red):
        squadrons = list(coalition.air_wing.iter_squadrons())
        for task, minimum in (
            (FlightType.AEWC, 2),
            (FlightType.REFUELING, 2),
            (FlightType.TRANSPORT, 4),
        ):
            assert (
                sum(s.max_size for s in squadrons if s.primary_task is task) >= minimum
            )
        assault = [s for s in squadrons if s.primary_task is FlightType.AIR_ASSAULT]
        assert len(assault) == 1
        assert assault[0].aircraft.helicopter
        assert assault[0].max_size == 4
        expected = {FlightType.AIR_ASSAULT}
        if assault[0].aircraft.capable_of(FlightType.TRANSPORT):
            expected.add(FlightType.TRANSPORT)
        assert assault[0].auto_assignable_mission_types == expected


def test_dedicated_afacs_have_thermal_designators_and_both_patrol_modes(
    generated: Game,
) -> None:
    for coalition, aircraft in (
        (generated.blue, "MQ-9 Reaper"),
        (generated.red, "WingLoong-I"),
    ):
        squadrons = [
            s
            for s in coalition.air_wing.iter_squadrons()
            if s.primary_task is FlightType.AFAC_AREA
        ]
        assert len(squadrons) == 2
        assert len({s.location for s in squadrons}) == 2
        for squadron in squadrons:
            assert squadron.aircraft.variant_id == aircraft
            assert squadron.max_size == 2
            profile = capabilities_for(squadron.aircraft.dcs_id)
            assert profile is not None
            assert profile.eo and profile.ir and profile.laser and profile.ir_pointer
            assert profile.remote_operator
            tasks = {FlightType.AFAC_AREA, FlightType.AFAC_FRONTLINE}
            with pytest.MonkeyPatch.context() as patch:
                patch.setitem(generated.settings.plugins, "realisticcas", True)
                patch.setitem(
                    generated.settings.plugins, "realisticcas.afacEnabled", True
                )
                patch.setattr(
                    squadron,
                    "auto_assignable_mission_types",
                    squadron.auto_assignable_mission_types,
                )
                squadron.set_auto_assignable_mission_types(tasks)
                assert squadron.auto_assignable_mission_types == tasks
                assert all(squadron.can_auto_assign(task) for task in tasks)
                patch.setitem(generated.settings.plugins, "realisticcas", False)
                assert not any(squadron.can_auto_assign(task) for task in tasks)


def test_authored_force_caps_limit_stealth_and_retain_red_modern_fighters(
    generated: Game,
) -> None:
    blue = list(generated.blue.air_wing.iter_squadrons())
    red = list(generated.red.air_wing.iter_squadrons())
    assert sum(s.max_size for s in blue) == 140
    assert sum(s.max_size for s in red) == 170
    assert all(s.max_size == 2 for s in blue if s.aircraft.variant_id == "[CH] B-21")
    assert all(s.max_size == 4 for s in blue if s.aircraft.variant_id == "F-22A Raptor")
    assert (
        sum(
            s.max_size
            for s in red
            if s.primary_task is FlightType.BARCAP
            and s.aircraft.variant_id in {"Su-30SM Flanker-H", "Su-30 Flanker-C"}
        )
        == 12
    )
    assert (
        sum(s.max_size for s in red if s.aircraft.variant_id == "MiG-29S Fulcrum-C")
        == 16
    )
    assert sum(s.max_size for s in red if s.aircraft.variant_id == "Tu-16 Badger") == 8
    assert (
        sum(
            s.max_size
            for s in red
            if s.primary_task is FlightType.ESCORT
            and s.aircraft.variant_id in {"Su-57 Felon", "Su-30 Flanker-C"}
        )
        == 12
    )
    assert sum(s.max_size for s in blue if s.aircraft.dcs_id == "A-10C_2") == 8
    assert (
        sum(s.max_size for s in red if s.aircraft.variant_id == "Su-25T Frogfoot") == 16
    )
    assert generated.settings.player_skill == generated.settings.enemy_skill
    assert generated.blue.budget == generated.red.budget == 2000


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
