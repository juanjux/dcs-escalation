"""The map's IADS links say whether they work.

A link to a command centre drew as working whenever both ends stood, so a radar with its
comms tower destroyed still showed a live line to its command centre, while Skynet
reaches a site only through its comms and hears nothing from it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from game.server.iadsnetwork.models import IadsConnectionJs
from game.theater.iadsnetwork.iadsrole import IadsRole


def _group(role: IadsRole, alive: bool = True, category: str = "aa") -> Any:
    tgo = SimpleNamespace(
        id=uuid4(),
        category=category,
        is_friendly=lambda player: True,
        position=SimpleNamespace(latlng=lambda: {"lat": 0.0, "lng": 0.0}),
    )
    return SimpleNamespace(
        iads_role=role,
        alive_units=1 if alive else 0,
        units=[],
        ground_object=tgo,
    )


def _node(group: Any, *connections: Any) -> Any:
    return SimpleNamespace(group=group, connections={uuid4(): c for c in connections})


def _command_link(radar: Any, network: Any) -> Any:
    [link] = [
        link
        for link in IadsConnectionJs.connections_for_node(radar, network)
        if not link.is_power and link.connected == network.centre.ground_object.id
    ]
    return link


def _network(tower_alive: bool, centre_powered: bool = True) -> Any:
    centre = _group(IadsRole.COMMAND_CENTER, category="commandcenter")
    plant = _group(IadsRole.POWER_SOURCE, alive=centre_powered, category="power")
    tower = _group(IadsRole.CONNECTION_NODE, alive=tower_alive, category="comms")
    radar = _node(_group(IadsRole.EWR, category="ewr"), tower, centre)
    return SimpleNamespace(
        nodes=[radar, _node(centre, plant)], centre=centre, radar=radar
    )


def test_a_site_with_its_comms_up_reaches_its_command_centre() -> None:
    network = _network(tower_alive=True)

    assert _command_link(network.radar, network).active


def test_a_site_with_its_comms_cut_does_not() -> None:
    network = _network(tower_alive=False)

    assert not _command_link(network.radar, network).active


def test_a_command_centre_with_no_power_is_reached_by_nobody() -> None:
    network = _network(tower_alive=True, centre_powered=False)

    assert not _command_link(network.radar, network).active
