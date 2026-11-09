"""IADS links are rebuilt from current coalition ownership and coverage."""

from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

from dcs import Point
from dcs.statics import Fortification
from dcs.terrain import Caucasus
from dcs.vehicles import AirDefence
import pytest
import yaml

from game.game import Game, TurnState
from game.migrator import Migrator
from game.point_with_heading import PointWithHeading
from game.settings import Settings
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState
from game.theater.player import Player
from game.theater.presetlocation import PresetLocation
from game.theater.theatergroundobject import IadsBuildingGroundObject, SamGroundObject
from game.theater.theatergroup import IadsGroundGroup, TheaterUnit
from game.utils import Heading


def site(
    name: str,
    role: IadsRole = IadsRole.SAM,
    x: float = 0,
    side: Player = Player.RED,
    settings: Settings | None = None,
) -> Any:
    cp: Any = NS(captured=side)
    cp.is_friendly = lambda player: cp.captured is player
    cp.coalition = NS(player=side, game=NS(settings=settings or Settings()))
    location = PresetLocation(name, Point(x, 0, Caucasus()))
    categories = {
        IadsRole.POWER_SOURCE: "power",
        IadsRole.CONNECTION_NODE: "comms",
        IadsRole.COMMAND_CENTER: "commandcenter",
    }
    obj = (
        IadsBuildingGroundObject(name, categories[role], location, cp, None)
        if role in categories
        else SamGroundObject(name, location, cp, None)
    )
    position = PointWithHeading.from_point(location, Heading.from_degrees(0))
    # Generic sites require external power; integrated defences have separate tests.
    kind = (
        Fortification.Comms_tower_M if role in categories else AirDefence.Kub_1S91_str
    )
    unit = TheaterUnit(1, name, kind, position, obj)
    group = IadsGroundGroup(1, name, position, [unit], obj)
    group.iads_role = role
    obj.groups.append(group)
    return obj


def links(network: IadsNetwork, obj: Any) -> set[Any]:
    node = network.node_for_tgo(obj)
    assert node is not None
    return {
        group.ground_object for group in network.effective_connections(node).values()
    }


def candidates(network: IadsNetwork, obj: Any) -> set[Any]:
    node = network.node_for_tgo(obj)
    assert node is not None and node.radio_candidates is not None
    return {group.ground_object for group, _distance in node.radio_candidates}


@pytest.mark.parametrize("side", [Player.RED, Player.BLUE])
def test_sites_use_local_feeds_and_no_enemy_infrastructure(
    side: Player,
) -> None:
    sam = site("SAM", side=side)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 10_000, side)
    backup = site("BACKUP", IadsRole.CONNECTION_NODE, 20_000, side)
    power = site("POWER", IadsRole.POWER_SOURCE, 50_000, side)
    centre = site("COMMAND", IadsRole.COMMAND_CENTER, 25_000, side)
    far = site("FAR", IadsRole.CONNECTION_NODE, 30_000, side)
    enemy = site("ENEMY", IadsRole.CONNECTION_NODE, 100, side.opponent)
    neutral = site("NEUTRAL", IadsRole.POWER_SOURCE, 200, Player.NEUTRAL)
    objects = [sam, tower, backup, power, centre, far, enemy, neutral]
    network = IadsNetwork(True)
    network.initialize_network(iter(objects))
    assert links(network, sam) == {tower, power}
    assert candidates(network, sam) == {tower, backup, centre, far}
    assert power in links(network, centre)
    assert all(len(links(network, obj)) < len(objects) - 1 for obj in objects)
    assert sam not in links(network, sam)
    for node in network.nodes:
        assert len(node.connections) == len({id(g) for g in node.connections.values()})
        assert all(
            node.group.ground_object.control_point.captured
            is group.ground_object.control_point.captured
            for group in node.connections.values()
        )


def test_rebuild_discards_old_positions_groups_and_deleted_objectives() -> None:
    sam, tower = site("SAM"), site("TOWER", IadsRole.CONNECTION_NODE, 1000)
    removed = site("REMOVED", IadsRole.POWER_SOURCE, 1000)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, tower, removed]))
    old_nodes = list(network.nodes)
    old_links = {cid for node in old_nodes for cid in node.connections}
    sam.position = PointWithHeading(100_000, 0, Heading.from_degrees(0), Caucasus())
    sam.groups[0] = IadsGroundGroup(9, "REPLACED", sam.position, [], sam)
    sam.groups[0].iads_role = IadsRole.SAM
    added = site("NEW", IadsRole.COMMAND_CENTER, 101_000)
    events = GameUpdateEvents()
    network.initialize_network(iter([sam, tower, added]), events)
    assert links(network, sam) == set()
    assert candidates(network, sam) == {added}
    assert all(node not in old_nodes for node in network.nodes)
    assert all(node.group.ground_object is not removed for node in network.nodes)
    assert events.deleted_iads_connections == old_links
    assert events.updated_iads == set(network.nodes)
    node = network.node_for_tgo(sam)
    assert node is not None and node.group is sam.groups[0]


def test_repeated_builds_have_no_duplicate_nodes_or_links() -> None:
    sam, tower = site("SAM"), site("TOWER", IadsRole.CONNECTION_NODE, 1000)
    network = IadsNetwork(True)
    for _ in range(3):
        network.initialize_network(iter([sam, tower]))
        assert len(network.nodes) == 2
        assert links(network, sam) == set()
        assert candidates(network, sam) == {tower}


def test_replaced_infrastructure_group_updates_incoming_links_immediately() -> None:
    sam, tower = site("SAM"), site("TOWER", IadsRole.CONNECTION_NODE, 1000)
    replacement = site("REPLACEMENT", IadsRole.CONNECTION_NODE, 1000)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, tower]))
    old_group = tower.groups[0]
    tower.groups = replacement.groups
    tower.groups[0].ground_object = tower
    for unit in tower.groups[0].units:
        unit.ground_object = tower
    events = GameUpdateEvents()
    network.update_tgo(tower, events)
    node = network.node_for_tgo(sam)
    assert node is not None
    assert node.radio_candidates is not None
    assert [group for group, _ in node.radio_candidates] == tower.groups
    assert old_group not in node.connections.values()
    assert all(group is not old_group for group, _ in node.radio_candidates)
    assert node in events.updated_iads


def test_export_keeps_broken_dependencies_and_excludes_neutral_and_moving_sites() -> (
    None
):
    sam, power = site("SAM"), site("POWER", IadsRole.POWER_SOURCE, 1000)
    neutral = site("NEUTRAL", IadsRole.COMMAND_CENTER, side=Player.NEUTRAL)
    moving = site("MOVING", x=1000)
    moving.in_transit = True
    power.groups[0].units[0].alive = False
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, power, neutral, moving]))
    game: Any = NS(
        iads_considerate_culling=lambda _: False, skynet_culled=lambda _: False
    )
    exported = network.skynet_nodes(game)
    sam_node = next(node for node in exported if node.iads_role is IadsRole.SAM)
    assert sam_node.connections["PowerSource"] == [power.groups[0].units[0].unit_name]
    assert all(node.player is Player.RED for node in exported)
    assert moving.groups[0].group_name not in {node.dcs_name for node in exported}


def test_captures_remove_enemy_dependencies_and_connect_new_friendly_sites() -> None:
    sam = site("SAM")
    captured = site("CAPTURED", IadsRole.POWER_SOURCE, 1000)
    own = site("BLUE SAM", x=2000, side=Player.BLUE)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, captured, own]))
    assert links(network, sam) == {captured}
    captured.control_point.captured = Player.BLUE
    network.update_tgo(captured, GameUpdateEvents())
    assert links(network, sam) == set()
    assert links(network, own) == {captured}


def test_destroyed_power_stays_a_failed_dependency_after_rebuilding() -> None:
    sam, power = site("SAM"), site("POWER", IadsRole.POWER_SOURCE, 1000)
    power.groups[0].units[0].alive = False
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, power]))
    assert links(network, sam) == {power}
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is IadsState.DARK
    network.initialize_network(iter([sam, power]))
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is IadsState.DARK
    power.groups[0].units[0].alive = True
    network.initialize_network(iter([sam, power]))
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is not IadsState.DARK


def test_changed_ranges_take_effect_on_the_next_rebuild_including_the_boundary() -> (
    None
):
    settings = Settings()
    settings.set_plugin_option("skynetiads.commsRangeNm", 10)
    sam = site("SAM", settings=settings)
    tower = site("TOWER", IadsRole.CONNECTION_NODE, 10 * 1852, settings=settings)
    centre = site("COMMAND", IadsRole.COMMAND_CENTER, 12 * 1852, settings=settings)
    power = site("POWER", IadsRole.POWER_SOURCE, settings=settings)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, tower, centre, power]))
    assert links(network, sam) == {tower, power}
    assert candidates(network, sam) == {tower}
    settings.set_plugin_option("skynetiads.commsRangeNm", 12)
    network.initialize_network(iter([sam, tower, centre, power]))
    assert links(network, sam) == {tower, power}
    assert candidates(network, sam) == {tower, centre}


def test_saved_authored_links_are_discarded_and_not_serialized_again() -> None:
    sam, power = site("SAM"), site("POWER", IadsRole.POWER_SOURCE, 200_000)
    network = IadsNetwork(True)
    state = network.__getstate__()
    state["iads_config"] = {"SAM": ["POWER"]}
    network.__setstate__(state)
    game: Any = NS(theater=NS(iads_network=network, ground_objects=iter([sam, power])))
    migrator = Migrator.__new__(Migrator)
    migrator.game = game
    migrator._rebuild_iads_topology()
    assert links(network, sam) == set()
    assert "iads_config" not in network.__dict__
    assert "iads_config" not in network.__getstate__()


def test_both_sides_rebuild_before_threat_zones_and_planning() -> None:
    sam, tower = site("SAM"), site("TOWER", IadsRole.CONNECTION_NODE, 1000)
    command = site("COMMAND", IadsRole.COMMAND_CENTER, 2000)
    power = site("POWER", IadsRole.POWER_SOURCE)
    network = IadsNetwork(True)
    steps = []

    def threats(events: Any) -> None:
        assert links(network, sam) == {tower, power}
        steps.append("threats")

    game: Any = NS(
        theater=NS(
            iads_network=network, ground_objects=iter([sam, tower, command, power])
        ),
        check_win_loss=lambda: TurnState.CONTINUE,
        set_bullseye=lambda: None,
        game_stats=NS(update=lambda game: None),
        compute_threat_zones=threats,
        blue=NS(initialize_turn=lambda *args: steps.append("blue")),
        red=NS(initialize_turn=lambda *args: steps.append("red")),
        plan_ground_war=lambda: None,
        compute_unculled_zones=lambda events: None,
        turn=1,
    )
    Game.initialize_turn(game, GameUpdateEvents())
    assert steps == ["threats", "blue", "red"]


def test_campaign_files_no_longer_define_static_topology() -> None:
    for path in Path("resources/campaigns").glob("*.yaml"):
        assert "iads_config" not in yaml.safe_load(
            path.read_text(encoding="utf-8")
        ), path
