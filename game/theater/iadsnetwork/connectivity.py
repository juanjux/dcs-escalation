"""Operational radio paths through powered relays to friendly command centres."""

from __future__ import annotations

from typing import Collection, TYPE_CHECKING
from uuid import UUID, NAMESPACE_OID, uuid5

from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.topology import Components

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
        self._automatic: dict[
            bool, tuple[dict[int, IadsGroundGroup], dict[int, frozenset[int]]]
        ] = {}

    @staticmethod
    def managed(node: IadsNetworkNode) -> bool:
        return getattr(node, "radio_candidates", None) is not None

    @staticmethod
    def topology_key(node: IadsNetworkNode) -> str:
        return node.group.ground_object.original_name

    def _build_automatic(self, operational: bool) -> None:
        """Build a live sparse forest, then one uplink for each consumer."""
        parents: dict[int, IadsGroundGroup] = {}
        roots: dict[int, frozenset[int]] = {}
        routers = sorted(
            (
                n
                for n in self.nodes
                if self.managed(n)
                and n.group.iads_role in RADIO_ROLES
                and (not operational or self.available(n))
            ),
            key=self.topology_key,
        )
        indices = {id(n): i for i, n in enumerate(routers)}
        edges: dict[tuple[str, str], tuple[int, int, int]] = {}
        for left in routers:
            for group, distance in left.radio_candidates or []:
                right = self.by_object.get(group.ground_object)
                if (
                    right is None
                    or id(right) not in indices
                    or not self.same_side(left, right)
                ):
                    continue
                a, b = sorted((self.topology_key(left), self.topology_key(right)))
                if a != b:
                    edges[(b, a)] = (distance, indices[id(left)], indices[id(right)])
        components = Components(len(routers))
        adjacent: dict[int, list[IadsNetworkNode]] = {id(n): [] for n in routers}
        for _key, (_distance, left_index, right_index) in sorted(
            edges.items(), key=lambda item: (item[1][0], *item[0])
        ):
            if components.join(left_index, right_index):
                adjacent[id(routers[left_index])].append(routers[right_index])
                adjacent[id(routers[right_index])].append(routers[left_index])
        sectors: dict[int, list[IadsNetworkNode]] = {}
        for i, router in enumerate(routers):
            sectors.setdefault(components.root(i), []).append(router)
        for sector in sectors.values():
            commands = [
                n for n in sector if n.group.iads_role is IadsRole.COMMAND_CENTER
            ]
            commands_in_sector = frozenset(id(n) for n in commands)
            for router in sector:
                roots[id(router)] = commands_in_sector
            root = min(commands or sector, key=self.topology_key)
            pending = [root]
            visited = {id(root)}
            while pending:
                current = pending.pop()
                for neighbor in sorted(adjacent[id(current)], key=self.topology_key):
                    if id(neighbor) not in visited:
                        visited.add(id(neighbor))
                        parents[id(neighbor)] = current.group
                        pending.append(neighbor)
        for node in self.nodes:
            if (
                not self.managed(node)
                or node.group.iads_role in RADIO_ROLES
                or getattr(node.group.ground_object, "carries_gps_jammer", False)
                or (operational and not self.available(node))
            ):
                continue
            for group, _distance in node.radio_candidates or []:
                other = self.by_object.get(group.ground_object)
                if (
                    other is not None
                    and self.same_side(node, other)
                    and roots.get(id(other))
                ):
                    parents[id(node)] = other.group
                    roots[id(node)] = roots[id(other)]
                    break
        self._automatic[operational] = parents, roots

    def radio_parent(
        self, node: IadsNetworkNode, operational: bool = True
    ) -> IadsGroundGroup | None:
        if operational not in self._automatic:
            self._build_automatic(operational)
        return self._automatic[operational][0].get(id(node))

    def effective_connections(
        self, node: IadsNetworkNode
    ) -> dict[UUID, IadsGroundGroup]:
        """Physical dependencies and the single currently selected radio uplink."""
        from .power import integrated_power_units

        integrated = bool(integrated_power_units(node.group))
        physical = {
            cid: group
            for cid, group in node.connections.items()
            if not (integrated and group.iads_role is IadsRole.POWER_SOURCE)
        }
        if not self.managed(node):
            return physical
        connections = {
            cid: group
            for cid, group in physical.items()
            if group.iads_role not in RADIO_ROLES
        }
        # Empty emplacements keep one inactive reservation for later deployment.
        parent = self.radio_parent(node, operational=not node.is_empty_site)
        if parent is not None:
            source = node.group.ground_object.id
            target = parent.ground_object.id
            cid = uuid5(NAMESPACE_OID, f"iads-radio:{source}:{target}:{parent.id}")
            connections[cid] = parent
        return connections

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
        if self.managed(node) and not self.independent(node):
            if operational not in self._automatic:
                self._build_automatic(operational)
            return self._automatic[operational][1].get(id(node), frozenset())
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
            for group in self.effective_connections(current).values():
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
        if getattr(node.group.ground_object, "carries_gps_jammer", False):
            return self.available(node)
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
        if any(
            getattr(n.group.ground_object, "carries_gps_jammer", False)
            for n in (left, right)
        ):
            return False
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
