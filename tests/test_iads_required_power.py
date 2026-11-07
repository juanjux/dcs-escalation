"""Advanced land sites fail closed without a real electrical supply."""

from types import SimpleNamespace
from typing import Any

from dcs.vehicles import AirDefence
import pytest

from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.iadsnetwork.iadsexplain import describe, LinkTone
from game.theater.iadsnetwork.iadsnetwork import IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsState, mains_are_up
from game.theater.player import Player
from game.theater.theatergroup import TheaterUnit
from tests.test_iads_automatic_topology import site
from tests.test_iads_relay_connectivity import node, state


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize(
    "role",
    [IadsRole.SAM, IadsRole.EWR, IadsRole.COMMAND_CENTER, IadsRole.CONNECTION_NODE],
)
def test_no_power_links_is_not_independent_power(side: Player, role: IadsRole) -> None:
    obj = site("UNFED", role, side=side)
    network = IadsNetwork(True)
    network.initialize_network(iter([obj]))
    current = node(network, obj)
    assert not mains_are_up(current)
    assert network.state_map.connectivity is not None
    assert not network.state_map.connectivity.powered(current)
    if role is not IadsRole.CONNECTION_NODE:
        assert state(network, obj) is IadsState.DARK
    power = next(
        link for link in describe(obj, network).links if link.caption == "POWER"
    )
    assert power.tone is LinkTone.BAD
    assert power.chip != "POWERED"


def test_basic_iads_keeps_native_independent_power() -> None:
    sam = site("BASIC")
    network = IadsNetwork(False)
    network.initialize_network(iter([sam]))
    assert mains_are_up(node(network, sam))
    assert state(network, sam) is not IadsState.DARK


def add_generator(obj: Any) -> TheaterUnit:
    generator = TheaterUnit(
        42,
        "LOCAL GENERATOR",
        AirDefence.Patriot_EPP,
        obj.groups[0].position,
        obj,
    )
    obj.groups[0].units.append(generator)
    return generator


def test_generator_loss_and_redundant_external_power() -> None:
    sam = site("SAM")
    generator = add_generator(sam)
    plant = site("POWER", IadsRole.POWER_SOURCE)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, plant]))
    assert state(network, sam) is not IadsState.DARK
    generator.alive = False
    network.update_tgo(sam, GameUpdateEvents())
    assert state(network, sam) is not IadsState.DARK
    plant.groups[0].units[0].alive = False
    network.update_tgo(plant, GameUpdateEvents())
    assert state(network, sam) is IadsState.DARK
    generator.alive = True
    network.update_tgo(sam, GameUpdateEvents())
    assert state(network, sam) is not IadsState.DARK


def test_export_retains_generator_names_and_grid_backup() -> None:
    sam = site("SAM")
    generator = add_generator(sam)
    plant = site("POWER", IadsRole.POWER_SOURCE)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, plant]))
    game: Any = SimpleNamespace(
        iads_considerate_culling=lambda _: False, skynet_culled=lambda _: False
    )
    exported = next(
        n for n in network.skynet_nodes(game) if n.iads_role is IadsRole.SAM
    )
    assert exported.requires_power
    assert exported.local_power_sources == [generator.unit_name]
    assert exported.connections["PowerSource"] == [plant.groups[0].units[0].unit_name]


def test_out_of_range_or_enemy_power_does_not_power_the_site() -> None:
    sam = site("SAM")
    far = site("FAR POWER", IadsRole.POWER_SOURCE, 35 * 1852 + 1)
    enemy = site("ENEMY POWER", IadsRole.POWER_SOURCE, side=Player.BLUE)
    network = IadsNetwork(True)
    network.initialize_network(iter([sam, far, enemy]))
    assert state(network, sam) is IadsState.DARK
