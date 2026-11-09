from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING, Iterator, Optional
from uuid import UUID

from game.data.units import UnitClass
from game.dcs.groundunittype import GroundUnitType
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import IadsStateMap, IadsStatus
from game.theater.iadsnetwork.power import integrated_power_units
from game.theater.theatergroundobject import (
    IadsBuildingGroundObject,
    IadsGroundObject,
    NavalGroundObject,
    TheaterGroundObject,
)
from game.theater.theatergroup import IadsGroundGroup
from game.theater.player import Player
from game.point_with_heading import PointWithHeading
from game.theater.iadsnetwork.topology import sparse_connections, radio_candidates

if TYPE_CHECKING:
    from game.game import Game
    from game.sim import GameUpdateEvents


class IadsNetworkException(Exception):
    pass


# Roles whose objects are buildings. A destroyed one has to keep reaching Skynet, or the
# element vanishes from its table and its absence reads as "no such dependency", which
# for command centres means the coalition regains command by losing its last one. These
# are all statics or scenery, so dcs_name_for_group has a name for them when nothing is
# alive; the roles that are not on this list are vehicle groups, where the same lookup
# raises instead.
STATIC_BACKED_ROLES = frozenset(
    {IadsRole.COMMAND_CENTER, IadsRole.CONNECTION_NODE, IadsRole.POWER_SOURCE}
)


def _settings_of(tgo: TheaterGroundObject) -> Any:
    """This campaign's settings, reached through the objective that needs them.

    The network is built from a list of objectives and never handed the game, and
    the two ranges below are plugin options rather than constants. None for a test
    double that stops short of a game, which then gets the defaults.
    """
    coalition = getattr(tgo.control_point, "coalition", None)
    game = getattr(coalition, "game", None)
    return getattr(game, "settings", None)


def brings_its_own_power(group: IadsGroundGroup) -> bool:
    """Whether this site generates its own electricity.

    A Patriot battery deploys with an EPP-III, a SAMP/T with its MGE: the power is
    part of the site, not something it is fed. Bombing the substation that happens to
    be nearest does nothing to it, and until now it switched it off.

    Read from the unit class the campaign data already carries, rather than a list of
    ids in Python: a mod that ships a generator is classed Power like the rest, and
    starts working the day it is registered.

    Alive units only. Mission data also identifies these generators so losing
    one inside DCS switches the site to its grid supply, if available.
    """
    return any(
        unit.alive
        and unit.unit_type is not None
        and unit.unit_type.unit_class is UnitClass.POWER
        for unit in group.units
    )


@dataclass
class SkynetNode:
    """Dataclass for a SkynetNode used in the LUA Data table by the luagenerator"""

    dcs_name: str
    player: Player
    iads_role: IadsRole
    properties: dict[str, str] = field(default_factory=dict)
    connections: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    independent_comms: bool = False
    requires_power: bool = False
    local_power_sources: list[str] = field(default_factory=list)
    radio_candidates: list[tuple[str, int]] | None = None
    topology_key: str = ""
    power_only: bool = False
    static_members: list[str] = field(default_factory=list)

    @staticmethod
    def dcs_name_for_group(group: IadsGroundGroup) -> str:
        if group.iads_role in STATIC_BACKED_ROLES:
            # Infrastructure keeps one identity as individual buildings are lost.
            return group.units[0].unit_name
        if group.iads_role in [
            IadsRole.EWR,
            IadsRole.COMMAND_CENTER,
            IadsRole.CONNECTION_NODE,
            IadsRole.POWER_SOURCE,
        ]:
            # Use UnitName for EWR, CommandCenter, Comms, Power
            for unit in group.units:
                # Check for alive units in the group
                if unit.alive:
                    return unit.unit_name
            if group.units[0].is_static:
                # Statics will be placed as dead unit
                return group.units[0].unit_name
            # If no alive unit is available and not static raise error
            raise IadsNetworkException(f"{group.name} has no skynet usable units")
        else:
            # Use the GroupName for SAMs, SAMAsEWR and PDs
            return group.group_name

    @classmethod
    def from_group(cls, group: IadsGroundGroup) -> SkynetNode:
        node = cls(
            cls.dcs_name_for_group(group),
            group.ground_object.coalition.player,
            group.iads_role,
        )
        node.independent_comms = isinstance(group.ground_object, NavalGroundObject)
        if group.iads_role in STATIC_BACKED_ROLES:
            node.static_members = [unit.unit_name for unit in group.units]
        unit_type = group.units[0].unit_type
        if unit_type is not None and isinstance(unit_type, GroundUnitType):
            node.properties = unit_type.skynet_properties.to_dict()
        return node


class IadsNetworkNode:
    """IadsNetworkNode which particicpates to the IADS Network and has connections to Power Sources, Comms or Point Defenses. A network node can be a SAM System, EWR or Command Center"""

    def __init__(self, group: IadsGroundGroup, requires_power: bool = False) -> None:
        self.group = group
        self.requires_power = requires_power
        self.connections: dict[UUID, IadsGroundGroup] = {}
        # None retains authored/legacy graph semantics. Empty means managed but
        # currently without any in-range radio infrastructure.
        self.radio_candidates: list[tuple[IadsGroundGroup, int]] | None = None

    def __str__(self) -> str:
        return self.group.group_name

    @property
    def is_empty_site(self) -> bool:
        """A topology-only node, with no deployed group or units."""
        return not self.group.units and not self.group.ground_object.groups

    def add_connection_for_tgo(self, tgo: TheaterGroundObject) -> None:
        """Add all possible connections for the given TGO to the node"""
        for group in tgo.groups:
            if isinstance(group, IadsGroundGroup) and group.iads_role.participate:
                self.add_connection_for_group(group)

    def add_connection_for_group(self, group: IadsGroundGroup) -> None:
        """Add connection for the given GroundGroup with unique ID"""
        if any(existing is group for existing in self.connections.values()):
            return
        self.connections[uuid.uuid4()] = group


class IadsNetwork:
    """Coalition-separated IADS topology derived from current sites and distances."""

    def __init__(
        self, advanced: bool, iads_data: list[str | dict[str, list[str]]] | None = None
    ) -> None:
        self.advanced_iads = advanced
        self.ground_objects: dict[str, TheaterGroundObject] = {}
        self.nodes: list[IadsNetworkNode] = []
        # The optional second argument is accepted for older callers, never used
        # to restore authored links. Saved topology is rebuilt by the migrator.

        self._state_map: Optional[IadsStateMap] = None

    def __getstate__(self) -> dict[str, Any]:
        # Derived from the nodes, so it is rebuilt rather than carried in the save.
        state = self.__dict__.copy()
        state.pop("iads_config", None)
        state["_state_map"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        state.pop("iads_config", None)
        state.setdefault("_state_map", None)
        self.__dict__.update(state)

    @property
    def state_map(self) -> IadsStateMap:
        """What Skynet will do with each site: networked, autonomous or dark.

        Worked out once and kept until something changes the network, because every
        site's answer depends on every other site's.
        """
        if self._state_map is None:
            self._state_map = IadsStateMap(self)
        return self._state_map

    def invalidate_state_map(self) -> None:
        self._state_map = None

    def effective_connections(
        self, node: IadsNetworkNode
    ) -> dict[UUID, IadsGroundGroup]:
        connectivity = self.state_map.connectivity
        return (
            connectivity.effective_connections(node)
            if connectivity is not None
            else node.connections
        )

    def skynet_nodes(self, game: Game) -> list[SkynetNode]:
        """Get all skynet nodes from the IADS Network"""
        skynet_nodes: list[SkynetNode] = []
        for node in self.nodes:
            if not any(
                node.group.ground_object.is_friendly(side)
                for side in (Player.BLUE, Player.RED)
            ):
                continue
            if getattr(node.group.ground_object, "in_transit", False):
                continue
            if game.iads_considerate_culling(node.group.ground_object):
                # Skip culled ground objects
                continue

            # Outside the Skynet radius: the site is in the mission and fights, it
            # is just not in the network. Only radars are ever culled this way; see
            # Game.skynet_culled for why the infrastructure has to stay.
            if game.skynet_culled(node.group.ground_object):
                continue

            all_dead = not any([x.alive for x in node.group.units])
            if all_dead and node.group.iads_role not in STATIC_BACKED_ROLES:
                continue

            # SkynetNode.from_group(node.group) may raise an exception
            #  (originating from SkynetNode.dcs_name_for_group)
            # but if it does, we want to know because it's supposed to be impossible afaict
            skynet_node = SkynetNode.from_group(node.group)
            skynet_node.topology_key = node.group.ground_object.original_name
            skynet_node.power_only = bool(
                getattr(node.group.ground_object, "carries_gps_jammer", False)
            )
            candidates = getattr(node, "radio_candidates", None)
            if candidates is not None:
                skynet_node.radio_candidates = [
                    (SkynetNode.dcs_name_for_group(group), distance)
                    for group, distance in candidates
                    if group.ground_object.is_friendly(skynet_node.player)
                    and not game.iads_considerate_culling(group.ground_object)
                    and not getattr(group.ground_object, "in_transit", False)
                    and (
                        group.alive_units > 0 or group.iads_role in STATIC_BACKED_ROLES
                    )
                ]
            skynet_node.requires_power = self.advanced_iads and not self._is_ship(node)
            integrated = integrated_power_units(node.group)
            if skynet_node.requires_power:
                skynet_node.local_power_sources = [
                    unit.unit_name
                    for unit in node.group.units
                    if unit.unit_type is not None
                    and unit.unit_type.unit_class is UnitClass.POWER
                ]
                skynet_node.local_power_sources.extend(
                    unit.unit_name for unit in integrated
                )
            for connection in self.effective_connections(node).values():
                if integrated and connection.iads_role is IadsRole.POWER_SOURCE:
                    continue
                if getattr(connection.ground_object, "in_transit", False):
                    continue
                # A destroyed building has to keep reaching Skynet. Dropping it here left
                # the element with an empty list, and genericCheckOneObjectIsAlive reads
                # an empty list as alive -- so bombing a power station switched its SAMs
                # back on next mission instead of keeping them dark. DCS reports a static
                # spawned dead as getByName=ok, isExist=false, life=0, which is exactly
                # what Skynet needs to see. Vehicle-backed roles still drop out: their
                # groups have no name once every unit is gone.
                if (
                    not any([x.alive for x in connection.units])
                    and connection.iads_role not in STATIC_BACKED_ROLES
                ):
                    continue
                # The Skynet radius is deliberately not asked about here. A node we
                # kept keeps every dependency it has, in range or not, alive or
                # destroyed: an empty list is what Skynet reads as "powered" and
                # "connected", so dropping a dead power station 11 km further out
                # than its SAM would switch that SAM back on. Only the mission-wide
                # cull applies, because that one really does remove the object.
                if connection.ground_object.is_friendly(
                    skynet_node.player
                ) and not game.iads_considerate_culling(connection.ground_object):
                    skynet_node.connections[connection.iads_role.value].append(
                        SkynetNode.dcs_name_for_group(connection)
                    )
            skynet_nodes.append(skynet_node)
        return skynet_nodes

    def update_tgo(self, tgo: TheaterGroundObject, events: GameUpdateEvents) -> None:
        """Update the IADS Network for the given TGO, and anything it drags with it."""
        # One site's power station going down changes what half the network is doing,
        # so the derived state is thrown away wholesale rather than patched -- and
        # every site whose answer changed is pushed to the map. Without that second
        # half, bombing a substation leaves its SAMs drawing confident threat rings
        # until the campaign is reloaded, because nothing touched THOSE objects.
        before = {obj: status for obj, status in self.state_map}
        connectivity = self.state_map.connectivity
        before_links = (
            {
                (node.group.ground_object, cid): connectivity.link_operational(
                    node, group
                )
                for node in self.nodes
                for cid, group in connectivity.effective_connections(node).items()
            }
            if connectivity is not None
            else None
        )
        self.invalidate_state_map()
        try:
            self._update_tgo(tgo, events)
        finally:
            self._push_state_changes(tgo, before, events, before_links)

    def _push_state_changes(
        self,
        tgo: TheaterGroundObject,
        before: dict[TheaterGroundObject, IadsStatus],
        events: GameUpdateEvents,
        before_links: dict[tuple[TheaterGroundObject, UUID], bool] | None = None,
    ) -> None:
        after = {obj: status for obj, status in self.state_map}
        changed = {
            obj
            for obj in before.keys() | after.keys()
            if before.get(obj) != after.get(obj)
        }
        for obj in changed:
            events.update_tgo(obj)
        # A link is drawn live or cut from both of its ends, so every node touching
        # something that changed is redrawn: a command centre going down cuts the links
        # of the sites that report to it, which are their nodes, not its own.
        changed.add(tgo)
        connectivity = self.state_map.connectivity
        after_links = (
            {
                (node.group.ground_object, cid): connectivity.link_operational(
                    node, group
                )
                for node in self.nodes
                for cid, group in connectivity.effective_connections(node).items()
            }
            if connectivity is not None and before_links is not None
            else {}
        )
        if before_links is not None:
            for _source, cid in before_links.keys() - after_links.keys():
                events.delete_iads_connection(cid)
        for node in self.nodes:
            # Relays have no radar status, but a remote outage can change their
            # outgoing links without changing either endpoint's physical health.
            link_changed = (
                before_links is not None
                and connectivity is not None
                and {
                    cid: active
                    for (source, cid), active in before_links.items()
                    if source is node.group.ground_object
                }
                != {
                    cid: active
                    for (source, cid), active in after_links.items()
                    if source is node.group.ground_object
                }
            )
            if link_changed:
                events.update_tgo(node.group.ground_object)
            if (
                node.group.ground_object in changed
                or any(
                    group.ground_object in changed
                    for group in self.effective_connections(node).values()
                )
                or link_changed
            ):
                events.update_iads_node(node)

    def _update_tgo(self, tgo: TheaterGroundObject, events: GameUpdateEvents) -> None:
        self.ground_objects[tgo.original_name] = tgo
        # Remove existing nodes for the given tgo. Iterate a copy: removing from the
        # list being walked skips the element after each hit, so a TGO with more than
        # one node kept a stale one.
        for cn in list(self.nodes):
            if cn.group.ground_object == tgo:
                self.nodes.remove(cn)
                events.updated_iads.discard(cn)
                for cID in cn.connections:
                    events.delete_iads_connection(cID)

        # Incoming links must not retain groups replaced by a repair or purchase.
        # A capture also removes links to the previous owner's infrastructure.
        for other in self.nodes:
            for cid, group in list(other.connections.items()):
                if group.ground_object is tgo and (
                    not self.advanced_iads
                    or not self._is_friendly(other, tgo)
                    or not any(group is current for current in tgo.groups)
                ):
                    del other.connections[cid]
                    events.delete_iads_connection(cid)
                    events.update_iads_node(other)

        node = self.node_for_tgo(tgo)
        if node is None:
            # Not participating
            if self.advanced_iads:
                self._rebuild_advanced_connections(events)
            return
        events.update_iads_node(node)
        if self.advanced_iads:
            self._rebuild_advanced_connections(events)

    def node_for_group(self, group: IadsGroundGroup) -> IadsNetworkNode:
        """Get existing node from the iads network or create a new node"""
        for cn in self.nodes:
            if cn.group == group:
                return cn

        node = IadsNetworkNode(
            group,
            requires_power=self.advanced_iads
            and not isinstance(group.ground_object, NavalGroundObject),
        )
        if self.advanced_iads and not isinstance(
            group.ground_object, NavalGroundObject
        ):
            node.radio_candidates = []
        self.nodes.append(node)
        return node

    def node_for_tgo(self, tgo: TheaterGroundObject) -> Optional[IadsNetworkNode]:
        """Get existing node from the iads network or create a new node"""
        for cn in self.nodes:
            if cn.group.ground_object == tgo:
                return cn

        # Create new connection_node if none exists
        # A destroyed site used to be taken out of the network altogether, which took
        # its links off the map with it: a link whose POWER STATION died drew broken,
        # and a link whose SAM died simply vanished -- so the state you most want to
        # see was the one state never drawn. A site with nothing alive still gets a
        # node, and its links go dashed like any other break.
        #
        # Whoever is alive still leads, though. A site whose SAM is dead but whose
        # point defence is not keeps being led by that point defence, which is how it
        # goes on reaching Skynet and fighting; handing the lead to the dead group
        # would have taken a live Vulcan out of the IADS.
        #
        # What Skynet is given barely changes: skynet_nodes drops a node whose group is
        # entirely dead, except for the static-backed roles, where being missing is read
        # as "no such dependency". That exception is the second thing this fixes -- a
        # command centre bombed flat used to leave the network, and Skynet's
        # isCommandCenterUsable() returns true on an empty table, so losing the last
        # command centre handed command back.
        groups = [g for g in tgo.groups if isinstance(g, IadsGroundGroup)]
        leaders = [g for g in groups if g.iads_role.participate and g.alive_units > 0]
        if not leaders:
            leaders = [g for g in groups if g.iads_role.participate]

        node: Optional[IadsNetworkNode] = None
        for group in groups:
            if not node and group in leaders:
                # Primary Node
                node = self.node_for_group(group)
            elif node and group.iads_role == IadsRole.POINT_DEFENSE:
                # Point Defense Node for this TGO
                node.add_connection_for_group(group)

        if node is None:
            if isinstance(tgo, IadsGroundObject) and not tgo.groups:
                # Keep the emplacement in the graph without creating equipment.
                # This group is not added to the TGO or exported to a mission.
                group = IadsGroundGroup(
                    0,
                    tgo.name,
                    PointWithHeading.from_point(tgo.position, tgo.heading),
                    [],
                    tgo,
                )
                group.iads_role = (
                    IadsRole.EWR if tgo.category == "ewr" else IadsRole.SAM
                )
                return self.node_for_group(group)
            logging.debug(f"TGO {tgo.name} not participating to IADS")
        return node

    def initialize_network(
        self,
        ground_objects: Iterator[TheaterGroundObject],
        events: GameUpdateEvents | None = None,
    ) -> None:
        """Rebuild from current objects, discarding old groups, positions and links."""
        if events is not None:
            for node in self.nodes:
                for connection_id in self.effective_connections(node):
                    events.delete_iads_connection(connection_id)
            events.updated_iads.clear()
        self.nodes = []
        self.ground_objects = {}
        for tgo in ground_objects:
            self.ground_objects[tgo.original_name] = tgo
        if self.advanced_iads:
            self.initialize_network_from_range()

        # basic mode if no advanced iads support or network init created no connections
        if not self.nodes:
            self.initialize_basic_iads()
        self.invalidate_state_map()
        if events is not None:
            for node in self.nodes:
                events.update_iads_node(node)
                events.update_tgo(node.group.ground_object)

    def initialize_basic_iads(self) -> None:
        """Initialize the IADS Network in basic mode (SAM & EWR only)"""
        for go in self.ground_objects.values():
            if isinstance(go, IadsGroundObject):
                self.node_for_tgo(go)

    def enrol_sites_that_arrived_late(self) -> list[str]:
        """Wire any site that belongs in the network and has no grid link.

        A save in progress gains ground objects after its network was built -- a GPS
        jamming site every faction gained, a kind of objective added since -- and the
        rebuild that enrols unnamed sites runs once. Anything registered after it sat
        in the theater with nothing to cue it and no plant to bomb.

        Rebuild once after finding all unwired sites. Power stations deliberately
        have no outgoing feeds and do not trigger repeated topology rebuilds.
        """
        pending = []
        new_infrastructure = False
        for go in self.ground_objects.values():
            if not self._belongs_in_the_network(go):
                continue
            present = any(node.group.ground_object is go for node in self.nodes)
            node = self.node_for_tgo(go)
            if (
                not present
                and node is not None
                and node.group.iads_role in STATIC_BACKED_ROLES
            ):
                new_infrastructure = True
            if (
                node is None
                or self._is_ship(node)
                or node.group.iads_role is IadsRole.POWER_SOURCE
                or (present and getattr(node, "radio_candidates", None) is not None)
                or self._has_grid(node)
            ):
                continue
            pending.append(node)
        if pending or new_infrastructure:
            for node in pending:
                node.radio_candidates = []
            self._rebuild_advanced_connections()
        return [
            node.group.ground_object.name for node in pending if self._has_grid(node)
        ]

    @staticmethod
    def _has_grid(node: IadsNetworkNode) -> bool:
        """Whether the node is already wired to a comms tower or a power station.

        Its own point defence does not count: a site that only points at itself is
        what an unwired one looks like.
        """
        return any(
            group.iads_role.is_comms_or_power for group in node.connections.values()
        ) or bool(getattr(node, "radio_candidates", None))

    @staticmethod
    def _belongs_in_the_network(go: TheaterGroundObject) -> bool:
        """The same test the range-built network applies."""
        if isinstance(go, (IadsGroundObject, NavalGroundObject)):
            return True
        return (
            isinstance(go, IadsBuildingGroundObject)
            and IadsRole.for_category(go.category) in STATIC_BACKED_ROLES
        )

    def initialize_network_from_range(self) -> None:
        """Build a sparse topology after all participating sites have a node."""
        for go in self.ground_objects.values():
            if self._belongs_in_the_network(go):
                self.node_for_tgo(go)
        self._rebuild_advanced_connections()

    def _is_friendly(self, node: IadsNetworkNode, tgo: TheaterGroundObject) -> bool:
        return any(
            node.group.ground_object.is_friendly(side) and tgo.is_friendly(side)
            for side in (Player.BLUE, Player.RED)
        )

    @staticmethod
    def _is_ship(node: IadsNetworkNode) -> bool:
        """A ship: it makes its own power and carries its own radios.

        Wired by range, a ship was tied to whatever plant stood on the coast where it
        started, and stayed tied to it wherever it sailed: bombing a power station
        ashore switched off a carrier 96 nm out.
        """
        return isinstance(node.group.ground_object, NavalGroundObject)

    def renew_stale_nodes(self) -> list[str]:
        """Rebuild the nodes of the sites whose groups were replaced under them.

        A site rebuilt through the OPFOR AI API kept its node on the group it no longer
        had: Skynet was handed a group the mission does not contain, the site read as
        standing whatever became of the new one, and the new one was left out.
        """
        from game.sim.gameupdateevents import GameUpdateEvents

        stale = {
            id(node.group.ground_object): node.group.ground_object
            for node in self.nodes
            if not node.is_empty_site
            and not any(
                group is node.group for group in node.group.ground_object.groups
            )
        }
        events = GameUpdateEvents()
        for tgo in stale.values():
            self.update_tgo(tgo, events)
        return sorted(tgo.name for tgo in stale.values())

    def restore_empty_sites(self) -> list[str]:
        """Restore topology for empty air-defence sites in existing saves."""
        from game.sim.gameupdateevents import GameUpdateEvents

        restored = []
        present = {id(node.group.ground_object) for node in self.nodes}
        for tgo in self.ground_objects.values():
            if (
                isinstance(tgo, IadsGroundObject)
                and not tgo.groups
                and id(tgo) not in present
            ):
                self.update_tgo(tgo, GameUpdateEvents())
                restored.append(tgo.name)
        return sorted(restored)

    def unwire_ships(self) -> list[str]:
        """Remove shore dependencies retained in old saves from all ships."""
        unwired = []
        for node in self.nodes:
            tgo = node.group.ground_object
            if not self._is_ship(node):
                continue
            grid = [
                cid
                for cid, group in node.connections.items()
                if group.iads_role.is_comms_or_power
            ]
            for cid in grid:
                del node.connections[cid]
            if grid:
                unwired.append(tgo.name)
        if unwired:
            self.invalidate_state_map()
        return unwired

    def _rebuild_advanced_connections(
        self, events: GameUpdateEvents | None = None
    ) -> None:
        """Recompute selected links, keeping the IDs of unchanged connections."""
        by_object = {n.group.ground_object: n for n in self.nodes}
        objects = [
            obj
            for obj in self.ground_objects.values()
            if not isinstance(obj, NavalGroundObject)
            and not getattr(obj, "in_transit", False)
            and (
                obj in by_object
                or IadsRole.for_category(obj.category) in STATIC_BACKED_ROLES
            )
        ]

        def friendly(left: TheaterGroundObject, right: TheaterGroundObject) -> bool:
            node = by_object.get(left)
            if node is None:
                node = self.node_for_tgo(left)
            return node is not None and self._is_friendly(node, right)

        plan = sparse_connections(objects, friendly, _settings_of)
        candidates = radio_candidates(objects, friendly, _settings_of)
        # New infrastructure can arrive after the consumer was registered.
        for target in {
            target for choices in candidates.values() for target, _ in choices
        }:
            if target not in by_object:
                target_node = self.node_for_tgo(target)
                if target_node is not None:
                    by_object[target] = target_node
        for node in self.nodes:
            obj = node.group.ground_object
            previous_candidates = getattr(node, "radio_candidates", None)
            if previous_candidates is None and not self._is_ship(node):
                continue
            node.radio_candidates = (
                None
                if self._is_ship(node)
                else [
                    (by_object[target].group, distance)
                    for target, distance in candidates.get(obj, [])
                    if target in by_object
                ]
            )
            integrated = bool(integrated_power_units(node.group))
            wanted = [
                group
                for obj in plan.get(node.group.ground_object, [])
                for group in obj.groups
                if isinstance(group, IadsGroundGroup)
                and group.iads_role.participate
                and not integrated
            ]
            changed = node.radio_candidates != previous_candidates
            for cid, group in list(node.connections.items()):
                if group.iads_role in STATIC_BACKED_ROLES and not any(
                    group is target for target in wanted
                ):
                    del node.connections[cid]
                    if events is not None:
                        events.delete_iads_connection(cid)
                    changed = True
            for group in wanted:
                if not any(group is current for current in node.connections.values()):
                    node.add_connection_for_group(group)
                    changed = True
            if changed and events is not None:
                events.update_iads_node(node)
        self.invalidate_state_map()
