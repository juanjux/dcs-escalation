"""Operational radio paths through powered relays to friendly command centres."""

from __future__ import annotations

from typing import Collection, TYPE_CHECKING

from game.theater.iadsnetwork.iadsrole import IadsRole

if TYPE_CHECKING:
    from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import IadsGroundGroup


RADIO_ROLES = frozenset({IadsRole.CONNECTION_NODE, IadsRole.COMMAND_CENTER})


class IadsConnectivity:
    def __init__(
        self,
        network: IadsNetwork,
        destroyed: Collection[TheaterGroundObject] = (),
    ) -> None:
        from .iadsstate import mains_are_up, own_generator, standing

        self.nodes = list(network.nodes)
        self.by_object = {node.group.ground_object: node for node in self.nodes}
        self.live = {id(n): standing(n.group, destroyed) for n in self.nodes}
        self.power = {
            id(n): n.group.iads_role is IadsRole.POWER_SOURCE
            or mains_are_up(n, destroyed)
            or own_generator(n.group) is not None
            for n in self.nodes
        }
        self._roots: dict[tuple[int, bool], frozenset[int]] = {}

    @staticmethod
    def independent(node: IadsNetworkNode) -> bool:
        """Ships retain their independent radios rather than shore dependencies."""
        from game.theater.theatergroundobject import NavalGroundObject

        return isinstance(node.group.ground_object, NavalGroundObject)

    def powered(self, node: IadsNetworkNode) -> bool:
        return self.power.get(id(node), False)

    def available(self, node: IadsNetworkNode) -> bool:
        return self.live.get(id(node), False) and self.powered(node)

    @staticmethod
    def same_side(left: IadsNetworkNode, right: IadsNetworkNode) -> bool:
        side = left.group.ground_object.control_point.captured
        return not getattr(side, "is_neutral", False) and (
            side == right.group.ground_object.control_point.captured
        )

    def roots(self, node: IadsNetworkNode, operational: bool = True) -> frozenset[int]:
        key = id(node), operational
        if key in self._roots:
            return self._roots[key]
        if operational and not self.available(node):
            return frozenset()
        found: set[int] = set()
        pending = [node]
        if self.independent(node):
            pending = [
                n
                for n in self.nodes
                if n.group.iads_role is IadsRole.COMMAND_CENTER
                and self.same_side(node, n)
            ]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if id(current) in visited or not self.same_side(node, current):
                continue
            visited.add(id(current))
            if operational and not self.available(current):
                continue
            if current.group.iads_role is IadsRole.COMMAND_CENTER:
                found.add(id(current))
            for group in current.connections.values():
                if group.iads_role not in RADIO_ROLES:
                    continue
                other = self.by_object.get(group.ground_object)
                if other is not None:
                    pending.append(other)
        result = frozenset(found)
        self._roots[key] = result
        return result

    def centres_for(
        self, node: IadsNetworkNode, operational: bool = True
    ) -> list[IadsNetworkNode]:
        roots = self.roots(node, operational)
        return [n for n in self.nodes if id(n) in roots]

    def connected(self, node: IadsNetworkNode) -> bool:
        if self.independent(node) and self.available(node):
            centres = [
                n
                for n in self.nodes
                if n.group.iads_role is IadsRole.COMMAND_CENTER
                and self.same_side(node, n)
            ]
            return not centres or bool(self.roots(node))
        return bool(self.roots(node))

    def can_exchange(self, left: IadsNetworkNode, right: IadsNetworkNode) -> bool:
        if not self.same_side(left, right):
            return False
        if self.independent(left) or self.independent(right):
            return self.connected(left) and self.connected(right)
        return bool(self.roots(left) & self.roots(right))

    def link_operational(self, node: IadsNetworkNode, group: IadsGroundGroup) -> bool:
        from .iadsstate import standing

        other = self.by_object.get(group.ground_object)
        if other is None or not self.same_side(node, other):
            return False
        if not self.available(node) or not self.available(other):
            return False
        if group.iads_role is IadsRole.POWER_SOURCE:
            return True
        if group.iads_role in RADIO_ROLES:
            return self.can_exchange(node, other)
        return standing(group)
