"""Independent air defences need command links, but not external electricity."""

from typing import Any
from operator import attrgetter
from types import SimpleNamespace

from dcs.vehicles import AirDefence, Unarmed
import pytest

from game.data.radar_db import LAUNCHER_TRACKER_PAIRS, SELF_CONTAINED_AIR_DEFENCES
from game.server.tgos.models import TgoJs
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsexplain import describe
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, mains_are_up
from game.theater.iadsnetwork.power import integrated_power_units
from game.theater.player import Player
from game.theater.theatergroup import IadsGroundGroup, TheaterUnit
from pydcs_extensions import chinesemilitaryassetspack as cmap
from pydcs_extensions import russianmilitaryassetspack as rmap
from pydcs_extensions import ukmilitaryassetspack as ukmap
from pydcs_extensions import usamilitaryassetspack as usamap
from tests.test_iads_automatic_topology import links, site
from tests.test_iads_relay_connectivity import chain, node, state


@pytest.mark.parametrize(
    "kind", sorted(SELF_CONTAINED_AIR_DEFENCES, key=attrgetter("id"))
)
def test_integrated_units_work_without_a_power_station(kind: Any) -> None:
    sam = site("INTEGRATED")
    unit = sam.groups[0].units[0]
    unit.type = kind
    network = IadsNetwork(True)
    network.initialize_network(iter([sam]))
    assert integrated_power_units(sam.groups[0]) == [unit]
    assert mains_are_up(node(network, sam))
    assert state(network, sam) is IadsState.AUTONOMOUS
    power = next(
        link for link in describe(sam, network).links if link.caption == "POWER"
    )
    assert power.chip == "OWN POWER"
    assert "do not need an external power station" in power.note


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("kind", [AirDefence.x_2S6_Tunguska, usamap.CH_Centurion_C_RAM])
def test_grid_failure_does_not_disable_integrated_sites(
    side: Player, kind: Any
) -> None:
    network, objects = chain(side)
    sam, plant = objects[3], objects[5]
    sam.groups[0].units[0].type = kind
    regular = site("DEPENDENT BATTERY", x=60_002, side=side)
    network.initialize_network(iter([*objects, regular]))
    assert state(network, sam) is IadsState.NETWORKED
    assert plant not in links(network, sam)
    assert plant in links(network, regular)
    plant.groups[0].units[0].alive = False
    network.update_tgo(plant, GameUpdateEvents())
    assert state(network, sam) is IadsState.AUTONOMOUS
    assert state(network, regular) is IadsState.DARK
    connectivity = network.state_map.connectivity
    assert connectivity is not None and connectivity.powered(node(network, sam))


@pytest.mark.parametrize("lost", [0, 1])
def test_integrated_sites_still_lose_command_or_comms(lost: int) -> None:
    network, objects = chain()
    sam = objects[3]
    sam.groups[0].units[0].type = AirDefence.x_2S6_Tunguska
    network.initialize_network(iter(objects))
    assert state(network, sam) is IadsState.NETWORKED
    objects[lost].groups[0].units[0].alive = False
    network.update_tgo(objects[lost], GameUpdateEvents())
    assert state(network, sam) is IadsState.AUTONOMOUS
    assert mains_are_up(node(network, sam))
    objects[lost].groups[0].units[0].alive = True
    network.update_tgo(objects[lost], GameUpdateEvents())
    assert state(network, sam) is IadsState.NETWORKED


@pytest.mark.parametrize(
    "kind",
    [
        AirDefence.Kub_2P25_ln,
        AirDefence.HQ_7_LN_SP,
        AirDefence.NASAMS_LN_B,
        AirDefence.Patriot_ln,
        AirDefence.SA_11_Buk_LN_9A310M1,
        cmap.CH_HQ22_LN,
        rmap.CH_BukM3_9A317M,
        rmap.CH_S350_50P6_9M96D,
        ukmap.CH_SkySabreLN,
    ],
)
def test_dependent_launchers_are_not_made_independent(kind: Any) -> None:
    sam = site("BATTERY")
    sam.groups[0].units[0].type = kind
    network = IadsNetwork(True)
    network.initialize_network(iter([sam]))
    assert not integrated_power_units(sam.groups[0])
    assert state(network, sam) is IadsState.DARK


@pytest.mark.parametrize("alive", [True, False])
@pytest.mark.parametrize(
    "part", [AirDefence.Kub_1S91_str, AirDefence.SA_11_Buk_CC_9S470M1]
)
def test_point_defence_does_not_power_a_mixed_battery(alive: bool, part: Any) -> None:
    sam = site("MIXED")
    group = sam.groups[0]
    group.units[0].type = part
    group.units[0].alive = alive
    group.units.append(
        TheaterUnit(2, "TUNGUSKA", AirDefence.x_2S6_Tunguska, group.position, sam)
    )
    network = IadsNetwork(True)
    network.initialize_network(iter([sam]))
    assert not integrated_power_units(group)
    assert state(network, sam) is IadsState.DARK


def test_support_trucks_do_not_remove_integrated_power() -> None:
    sam = site("OSA")
    group = sam.groups[0]
    group.units[0].type = AirDefence.Osa_9A33_ln
    group.units.append(TheaterUnit(2, "TRUCK", Unarmed.Ural_375, group.position, sam))
    assert integrated_power_units(group) == [group.units[0]]


def test_integrated_power_lasts_only_while_a_combat_vehicle_survives() -> None:
    sam = site("TUNGUSKAS")
    group = sam.groups[0]
    group.units[0].type = AirDefence.x_2S6_Tunguska
    group.units.extend(
        [
            TheaterUnit(2, "SECOND", AirDefence.x_2S6_Tunguska, group.position, sam),
            TheaterUnit(3, "TRUCK", Unarmed.Ural_375, group.position, sam),
        ]
    )
    network = IadsNetwork(True)
    network.initialize_network(iter([sam]))
    group.units[0].alive = False
    assert mains_are_up(node(network, sam))
    group.units[1].alive = False
    assert not mains_are_up(node(network, sam))


def test_moving_integrated_site_is_relocating_not_unpowered() -> None:
    sam = site("TUNGUSKA")
    sam.groups[0].units[0].type = AirDefence.x_2S6_Tunguska
    sam.in_transit = True
    network = IadsNetwork(True)
    network.initialize_network(iter([sam]))
    assert mains_are_up(node(network, sam))
    status = network.state_map.status_for(sam)
    assert status is not None and status.state is IadsState.RELOCATING
    assert describe(sam, network).verdict == "RELOCATING"
    sam.in_transit = False
    network.initialize_network(iter([sam]))
    assert state(network, sam) is IadsState.AUTONOMOUS


def test_legacy_grid_links_do_not_override_integrated_power() -> None:
    network, objects = chain()
    sam, plant = objects[3], objects[5]
    # A saved node can retain an old electrical dependency until the next rebuild.
    sam.groups[0].units[0].type = AirDefence.x_2S6_Tunguska
    assert plant.groups[0] in node(network, sam).connections.values()
    plant.groups[0].units[0].alive = False
    network.invalidate_state_map()
    assert mains_are_up(node(network, sam))
    assert state(network, sam) is IadsState.AUTONOMOUS
    assert plant not in links(network, sam)


def test_separate_tracking_radars_always_exclude_integrated_power() -> None:
    assert not SELF_CONTAINED_AIR_DEFENCES.intersection(LAUNCHER_TRACKER_PAIRS)


def test_dark_primary_battery_keeps_only_surviving_point_defence_ranges() -> None:
    sam = site("WOLVERINE")
    sam.control_point.name = "BASE"
    plant = site("POWER", IadsRole.POWER_SOURCE)
    battery = sam.groups[0]
    battery.units.append(
        TheaterUnit(2, "LAUNCHER", AirDefence.Kub_2P25_ln, battery.position, sam)
    )
    tor = TheaterUnit(3, "TOR", AirDefence.Tor_9A331, battery.position, sam)
    shilka = TheaterUnit(4, "SHILKA", AirDefence.ZSU_23_4_Shilka, battery.position, sam)
    point_defence = IadsGroundGroup(
        2, "POINT DEFENCE", battery.position, [tor, shilka], sam
    )
    point_defence.iads_role = IadsRole.POINT_DEFENSE
    sam.groups.append(point_defence)

    network = IadsNetwork(True)
    sam.control_point.theater = SimpleNamespace(iads_network=network)
    sam.control_point.coalition.game.theater = sam.control_point.theater
    network.initialize_network(iter([sam, plant]))
    before = TgoJs.for_tgo(sam)
    assert before.threat_ranges == [
        battery.max_threat_range().meters,
        tor.threat_range.meters,
    ]
    assert before.detection_ranges == [
        battery.max_detection_range().meters,
        tor.detection_range.meters,
    ]

    plant.groups[0].units[0].alive = False
    events = GameUpdateEvents()
    network.update_tgo(plant, events)
    assert sam in events.updated_tgos
    dark = TgoJs.for_tgo(sam)
    assert dark.iads_state == "dark"
    assert dark.threat_ranges == [tor.threat_range.meters]
    assert dark.detection_ranges == [tor.detection_range.meters]
    assert (
        dark.iads_reason
        and "Local point defences remain operational" in dark.iads_reason
    )

    tor.alive = False
    assert TgoJs.for_tgo(sam).threat_ranges == [shilka.threat_range.meters]
    shilka.alive = False
    assert TgoJs.for_tgo(sam).threat_ranges == []
    assert TgoJs.for_tgo(sam).detection_ranges == []
