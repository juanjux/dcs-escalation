"""What Skynet will do with each site, worked out before the mission runs.

Skynet decides a site's state inside DCS and never reports it back, but it decides it
from things Escalation already knows, so the same answer can be reached here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterator, Optional

from game.data.units import UnitClass
from game.theater.iadsnetwork.iadsrole import IadsRole

if TYPE_CHECKING:
    from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.theater.theatergroup import IadsGroundGroup


#: Skynet's own name for "go autonomous and stay switched off". No stock unit asks for
#: it, but a mod can, and then losing the network switches the site off rather than
#: setting it loose.
AUTONOMOUS_STATE_DARK = "SkynetIADSAbstractRadarElement.AUTONOMOUS_STATE_DARK"


class IadsState(Enum):
    #: Fed by an early-warning radar and under a command centre. It holds its fire
    #: until the network hands it a target, and that is when it is most dangerous.
    NETWORKED = "networked"

    #: Cut off from the network but still powered. It fights on whatever its own radar
    #: can see, which is a good deal less than the network was giving it.
    AUTONOMOUS = "autonomous"

    #: Switched off. Skynet will not bring the radar up, so the site is silent for the
    #: whole mission unless it is repaired first.
    DARK = "dark"

    #: Nothing left of it. Kept apart from DARK because the two want opposite things
    #: said about them: a site with no power keeps a threat ring it cannot enforce and
    #: needs that ring taken away, while a destroyed one has already lost its ring and
    #: what the map still has to show is whatever survives around it -- the point
    #: defence of a flattened battery is alive and will shoot.
    DESTROYED = "destroyed"


@dataclass(frozen=True)
class IadsStatus:
    state: IadsState

    #: Why, in a line, ready to put in a tooltip or hand to a planner.
    reason: str

    #: Nothing left that can find a target for itself. A networked site can still be
    #: handed one; an autonomous one has nothing to look with.
    blind: bool

    @property
    def notable(self) -> bool:
        """Whether the state is worth reporting.

        Destroyed is not: the health bar and the API already say so, and repeating it
        would put a line on most of the wrecks in a long campaign.

        """
        if self.state is IadsState.DESTROYED:
            return False
        return self.state is not IadsState.NETWORKED or self.blind


def _own_generator(group: IadsGroundGroup) -> Optional[str]:
    """The name of the generator this site deploys with, if it still has one.

    The name rather than a flag, because a battery running on its own power has one
    truck worth bombing and the name says which.

    """
    for unit in group.units:
        if (
            unit.alive
            and unit.unit_type is not None
            and unit.unit_type.unit_class is UnitClass.POWER
        ):
            return str(unit.unit_type.display_name)
    return None


def _detection_range(group: IadsGroundGroup) -> float:
    """Metres this site can see for itself.

    Asked of the range rather than of a list of radar classes: a HAWK that has lost its
    AN/MPQ-50 still has an MPQ-46 with 90 km, and a NASAMS that has lost its MPQ-64 sees
    nothing despite having launchers and a command post.

    """
    return max((unit.detection_range.meters for unit in group.units), default=0.0)


def _goes_dark_when_autonomous(group: IadsGroundGroup) -> bool:
    for unit in group.units:
        if unit.unit_type is None:
            continue
        properties = getattr(unit.unit_type, "skynet_properties", None)
        if properties is None:
            continue
        if getattr(properties, "autonomous_behaviour", None) == AUTONOMOUS_STATE_DARK:
            return True
    return False


class IadsStateMap:
    """The state of every site in one network, worked out in one pass."""

    def __init__(self, network: IadsNetwork) -> None:
        self._by_tgo: dict[TheaterGroundObject, IadsStatus] = {}
        self._build(network)

    def status_for(self, tgo: TheaterGroundObject) -> Optional[IadsStatus]:
        """The site's state, or None if it is not part of an IADS at all."""
        return self._by_tgo.get(tgo)

    def __iter__(self) -> Iterator[tuple[TheaterGroundObject, IadsStatus]]:
        return iter(self._by_tgo.items())

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _mains_are_up(node: IadsNetworkNode) -> bool:
        """Whether the grid still reaches this site. Nothing to do with its own
        generator: an empty list of power sources is what Skynet reads as powered."""
        sources = [
            group
            for group in node.connections.values()
            if group.iads_role is IadsRole.POWER_SOURCE
        ]
        return not sources or any(group.alive_units > 0 for group in sources)

    @staticmethod
    def _connected(node: IadsNetworkNode) -> bool:
        comms = [
            group
            for group in node.connections.values()
            if group.iads_role is IadsRole.CONNECTION_NODE
        ]
        return not comms or any(group.alive_units > 0 for group in comms)

    def _build(self, network: IadsNetwork) -> None:
        by_side: dict[bool, list[IadsNetworkNode]] = {}
        for node in network.nodes:
            side = node.group.ground_object.control_point.captured.is_blue
            by_side.setdefault(side, []).append(node)
        for nodes in by_side.values():
            self._build_side(nodes)

    def _build_side(self, nodes: list[IadsNetworkNode]) -> None:
        mains = {id(node): self._mains_are_up(node) for node in nodes}
        generators = {id(node): _own_generator(node.group) for node in nodes}
        powered = {
            id(node): mains[id(node)] or generators[id(node)] is not None
            for node in nodes
        }
        connected = {id(node): self._connected(node) for node in nodes}

        command_centres = [
            node for node in nodes if node.group.iads_role is IadsRole.COMMAND_CENTER
        ]
        # No command centre at all reads as "command is fine": an empty table is what
        # isCommandCenterUsable() answers true to.
        has_command = not command_centres or any(
            node.group.alive_units > 0 and powered[id(node)] and connected[id(node)]
            for node in command_centres
        )

        parents = [
            node
            for node in nodes
            if node.group.iads_role in (IadsRole.EWR, IadsRole.SAM_AS_EWR)
            and node.group.alive_units > 0
            and powered[id(node)]
            and connected[id(node)]
        ]

        for node in nodes:
            if node.group.iads_role in (
                IadsRole.CONNECTION_NODE,
                IadsRole.POWER_SOURCE,
            ):
                # Infrastructure. It has no radar to switch on or off.
                continue
            self._by_tgo[node.group.ground_object] = self._status_for_node(
                node,
                powered[id(node)],
                connected[id(node)],
                has_command,
                parents,
                # Only worth mentioning when the grid has actually failed: a battery
                # whose substation is standing is not running on its generator.
                generators[id(node)] if not mains[id(node)] else None,
            )

    def _status_for_node(
        self,
        node: IadsNetworkNode,
        powered: bool,
        connected: bool,
        has_command: bool,
        parents: list[IadsNetworkNode],
        own_generator: Optional[str] = None,
    ) -> IadsStatus:
        role = node.group.iads_role

        if node.group.alive_units == 0:
            # Nothing left to be blind with, and nothing to switch on. What the map
            # shows about a wreck is that it is a wreck.
            return IadsStatus(IadsState.DESTROYED, "Destroyed.", False)

        # A command centre is a building and a GPS jammer is a truck with an antenna.
        # Neither ever had a search radar, so having none is not news about them.
        jams_gps = bool(getattr(node.group.ground_object, "carries_gps_jammer", False))
        blind = (
            role is not IadsRole.COMMAND_CENTER
            and not jams_gps
            and _detection_range(node.group) <= 0
        )

        if not powered:
            # Skynet's goLive() refuses outright without power, so this is the one
            # answer that needs nothing else asked about the site.
            consequence = (
                "so it directs nobody"
                if role is IadsRole.COMMAND_CENTER
                else "so it stays switched off"
            )
            return IadsStatus(
                IadsState.DARK,
                "No power: its substation is down and it carries no generator, "
                f"{consequence}.",
                blind,
            )

        mains_note = (
            f" Its substation is down; it runs on its own {own_generator}, "
            "which can be bombed like anything else."
            if own_generator is not None
            else ""
        )

        if jams_gps:
            # A GPS jammer sits in an early-warning slot but is not a radar: nobody
            # cues it, it reports to nobody, and it denies its bubble for as long as
            # its trucks are alive. Losing the network costs it nothing, so neither the
            # violet bar nor the "no radar of its own" line belongs on it. Power is the
            # one thing it does want, and that was answered above.
            return IadsStatus(
                IadsState.NETWORKED,
                "Jamming GPS; it needs no network." + mains_note,
                False,
            )

        if role is IadsRole.COMMAND_CENTER:
            if not connected:
                # Same test has_command applies to it -- getUsableAbstractRadarElemtentsOfTable
                # wants an active connection node as well as power -- so saying it is
                # directing the network here would contradict every site that has just
                # been told there is no command centre standing.
                return IadsStatus(
                    IadsState.AUTONOMOUS,
                    "Comms cut: it directs nobody." + mains_note,
                    blind,
                )
            return IadsStatus(
                IadsState.NETWORKED, "Directing the network." + mains_note, blind
            )

        if role is IadsRole.EWR:
            if not connected:
                return IadsStatus(
                    IadsState.AUTONOMOUS,
                    "Comms cut: it still sees, but what it sees reaches nobody."
                    + mains_note,
                    blind,
                )
            return IadsStatus(
                IadsState.NETWORKED, "Feeding the network." + mains_note, blind
            )

        # A SAM, or a SAM standing in for an early-warning radar.
        if not connected:
            reason = "Comms cut: nothing reaches it from the network."
        elif not has_command:
            reason = "No command centre left standing to direct it."
        else:
            covering = sorted(
                self._name(parent)
                for parent in parents
                if parent is not node and self._covers(parent, node)
            )
            if covering:
                return IadsStatus(
                    IadsState.NETWORKED,
                    f"Cued by {', '.join(covering)}." + mains_note,
                    blind,
                )
            reason = "No early-warning radar covers it any more."

        if _goes_dark_when_autonomous(node.group):
            return IadsStatus(
                IadsState.DARK,
                f"{reason} Set to stay dark when it loses the network." + mains_note,
                blind,
            )
        if blind:
            return IadsStatus(
                IadsState.AUTONOMOUS,
                f"{reason} Its own search radar is gone, so it has nothing to look "
                "with." + mains_note,
                blind,
            )
        return IadsStatus(
            IadsState.AUTONOMOUS,
            f"{reason} Fighting on its own radar." + mains_note,
            blind,
        )

    @staticmethod
    def _name(node: IadsNetworkNode) -> str:
        return node.group.ground_object.name

    @staticmethod
    def _covers(parent: IadsNetworkNode, child: IadsNetworkNode) -> bool:
        reach = _detection_range(parent.group)
        if reach <= 0:
            return False
        return reach >= parent.group.ground_object.position.distance_to_point(
            child.group.ground_object.position
        )
