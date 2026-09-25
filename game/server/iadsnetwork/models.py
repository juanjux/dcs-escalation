from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from game.server.leaflet import LeafletPoint
from game.theater.player import Player
from game.theater.iadsnetwork.iadsnetwork import IadsNetworkNode, IadsNetwork
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import comms_up, mains_are_up, own_generator
from game.theater.theatergroup import IadsGroundGroup


class IadsConnectionJs(BaseModel):
    id: UUID
    points: list[LeafletPoint]
    node: UUID
    connected: UUID
    active: bool
    blue: bool
    is_power: bool

    class Config:
        title = "IadsConnection"

    @staticmethod
    def connections_for_tgo(
        tgo_id: UUID, network: IadsNetwork
    ) -> list[IadsConnectionJs]:
        for node in network.nodes:
            if node.group.ground_object.id == tgo_id:
                return IadsConnectionJs.connections_for_node(node, network)
        return []

    @staticmethod
    def connections_for_node(
        network_node: IadsNetworkNode, network: IadsNetwork
    ) -> list[IadsConnectionJs]:
        iads_connections = []
        tgo = network_node.group.ground_object
        for id, connection in network_node.connections.items():
            if connection.ground_object.is_friendly(Player.BLUE) != tgo.is_friendly(
                Player.BLUE
            ):
                continue  # Skip connections which are not from same coalition
            if tgo.is_friendly(Player.BLUE):
                blue = True
            elif tgo.is_friendly(Player.RED):
                blue = False
            else:
                continue  # Skip neutral
            iads_connections.append(
                IadsConnectionJs(
                    id=id,
                    points=[
                        tgo.position.latlng(),
                        connection.ground_object.position.latlng(),
                    ],
                    node=tgo.id,
                    connected=connection.ground_object.id,
                    active=(
                        network_node.group.alive_units > 0
                        and connection.alive_units > 0
                        and (
                            connection.iads_role is not IadsRole.COMMAND_CENTER
                            or _reaches_command(network_node, connection, network)
                        )
                    ),
                    blue=blue,
                    is_power="power"
                    in [tgo.category, connection.ground_object.category],
                )
            )
        return iads_connections


def _reaches_command(
    node: IadsNetworkNode, centre: IadsGroundGroup, network: IadsNetwork
) -> bool:
    """Whether the link to a command centre works. A site reaches it only through its
    own comms, and a command centre with no power or no comms directs nobody."""
    if not comms_up(node):
        return False
    for other in network.nodes:
        if other.group is centre:
            powered = mains_are_up(other) or own_generator(other.group) is not None
            return powered and comms_up(other)
    return True


class IadsNetworkJs(BaseModel):
    advanced: bool
    connections: list[IadsConnectionJs]

    class Config:
        title = "IadsNetwork"

    @staticmethod
    def from_network(network: IadsNetwork) -> IadsNetworkJs:
        iads_connections = []
        for connection in network.nodes:
            if not connection.group.iads_role.participate:
                continue  # Skip
            iads_connections.extend(
                IadsConnectionJs.connections_for_node(connection, network)
            )
        return IadsNetworkJs(
            advanced=network.advanced_iads, connections=iads_connections
        )
