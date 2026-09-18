"""What feeds a site, link by link.

``IadsStateMap`` answers what Skynet will do with a site. This answers why: which radar
cues it, which command centre directs it, what powers it, and the state of each of those
links. The same rows serve both sides -- on an own site they are what to repair, on an
enemy site what to bomb -- so the notes are written differently for each.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.iadsnetwork.iadsstate import (
    IadsStatus,
    comms_up,
    covers,
    detection_range,
    mains_are_up,
    own_generator,
)

if TYPE_CHECKING:
    from game.theater.iadsnetwork.iadsnetwork import IadsNetwork, IadsNetworkNode
    from game.theater.theatergroundobject import TheaterGroundObject


class LinkTone(Enum):
    """How the link is doing, for whoever paints it."""

    GOOD = "good"
    WARN = "warn"
    BAD = "bad"

    #: Neither good nor bad: a link the site does not need, or one that only exists
    #: while something is in the air.
    INFO = "info"


@dataclass(frozen=True)
class Place:
    """An objective named in a row, and the objective itself when there is one."""

    name: str
    objective: Optional[TheaterGroundObject] = None


@dataclass(frozen=True)
class IadsLink:
    """One row: a kind of link, what is at the other end, and how it is doing."""

    #: What kind of link this is, for the label column.
    caption: str

    #: What is at the other end, usually the name of one or more objectives.
    title: str

    #: Why it is in that state, or what breaking it costs.
    note: str

    #: The verdict for this row alone.
    chip: str

    tone: LinkTone

    #: The objectives the title names, for whoever wants to open them. Empty when the
    #: row names no objective ("No grid link in this layout").
    places: tuple[Place, ...] = ()

    #: How many more there are than the row names, when the list is too long to read.
    more: int = 0


class NoNetwork(Enum):
    """Why a site has no network behind it, when it has none."""

    #: Skynet is switched off in the options, so nothing is networked this campaign.
    PLUGIN_OFF = "plugin off"

    #: The campaign has no IADS at all.
    CAMPAIGN = "campaign"

    #: There is a network, and this site is not in it.
    STANDALONE = "standalone"


_WITHOUT_A_NETWORK = {
    NoNetwork.PLUGIN_OFF: (
        "Skynet is switched off in the options: no site is networked this campaign."
    ),
    NoNetwork.CAMPAIGN: (
        "This campaign has no IADS: every site fights on its own radar."
    ),
    NoNetwork.STANDALONE: "Never part of an IADS: it fights on its own radar, always.",
}


@dataclass(frozen=True)
class IadsPicture:
    status: Optional[IadsStatus]

    #: What this site gives the network: whom it cues, directs, holds up.
    gives: tuple[IadsLink, ...] = ()

    #: What it needs from elsewhere: early warning, command, comms, power.
    gets: tuple[IadsLink, ...] = ()

    #: Set when there is no network behind this site, and why.
    off: Optional[NoNetwork] = None

    #: What to say instead of a site's own state: infrastructure has none, it just
    #: holds other things up.
    headline: Optional[str] = None

    @property
    def links(self) -> tuple[IadsLink, ...]:
        return self.gives + self.gets

    @property
    def verdict(self) -> str:
        if self.status is None and self.headline is not None:
            return "INFRASTRUCTURE"
        if self.off is NoNetwork.STANDALONE:
            return "STANDALONE"
        if self.off is not None:
            return "NO IADS"
        assert self.status is not None
        return self.status.state.name

    @property
    def summary(self) -> str:
        if self.headline is not None:
            return self.headline
        if self.off is not None:
            return _WITHOUT_A_NETWORK[self.off]
        assert self.status is not None
        return self.status.reason


def describe(
    tgo: TheaterGroundObject,
    network: IadsNetwork,
    awacs: Sequence[str] = (),
    friendly: bool = True,
    plugin_enabled: bool = True,
) -> IadsPicture:
    """The chain behind one site.

    ``awacs`` is the AEW&C flights on station this turn, which Skynet counts as
    early-warning radars for as long as they fly. Passed in rather than read here: the
    network knows nothing about the air tasking order. ``plugin_enabled`` is the
    skynetiads plugin option, for the same reason.
    """
    if not plugin_enabled:
        return IadsPicture(None, off=NoNetwork.PLUGIN_OFF)
    if not network.nodes:
        return IadsPicture(None, off=NoNetwork.CAMPAIGN)

    node = _node_for(tgo, network)
    if node is None:
        fed = _feeds(tgo, network)
        if fed:
            # A comms tower or a substation is not a site with a state of its own: it
            # is what other sites are standing on.
            return _infrastructure(tgo, fed, friendly)
        return IadsPicture(None, off=NoNetwork.STANDALONE)

    status = network.state_map.status_for(tgo)
    siblings = _same_side(node, network)
    role = node.group.iads_role
    gives: list[IadsLink] = []
    gets: list[IadsLink] = []

    if getattr(tgo, "carries_gps_jammer", False):
        gives.append(
            IadsLink(
                caption="JAMMING",
                title="GPS-guided weapons go wide inside its bubble",
                note="the weapons only: aircraft and their navigation are unaffected",
                chip="ON ITS OWN",
                tone=LinkTone.GOOD,
            )
        )
    elif role is IadsRole.EWR:
        gives.append(_cues_link(node, siblings, friendly))
        gives.append(_command_link(node, siblings, friendly))
    elif role is IadsRole.COMMAND_CENTER:
        gives.append(_directs_link(node, siblings, friendly))
    else:
        if role is IadsRole.SAM_AS_EWR:
            gives.append(_cues_link(node, siblings, friendly))
        gets.append(_early_warning_link(node, siblings, friendly))
        if awacs:
            gets.append(_awacs_link(awacs))
        gets.append(_command_link(node, siblings, friendly))

    if not getattr(tgo, "carries_gps_jammer", False):
        # Nothing is handed to a jammer, so the comms that would hand it are not its
        # business.
        comms = _comms_link(node, friendly)
        if comms is not None:
            gets.append(comms)
    gets.extend(_power_links(node, friendly))
    return IadsPicture(status, tuple(gives), tuple(gets))


# -------------------------------------------------------------------- the rows


def _early_warning_link(
    node: IadsNetworkNode, siblings: list[IadsNetworkNode], friendly: bool
) -> IadsLink:
    covering = [
        other
        for other in siblings
        if other is not node
        and other.group.iads_role in (IadsRole.EWR, IadsRole.SAM_AS_EWR)
        and covers(other, node)
    ]
    live = [other for other in covering if _is_live(other)]

    if live:
        ranges = " / ".join(
            f"{detection_range(other.group) / 1852:.0f} nm" for other in live
        )
        return IadsLink(
            places=_places_of([other.group.ground_object for other in live]),
            caption="EARLY WARNING",
            title=" · ".join(sorted(_name(other) for other in live)),
            note=(
                f"{len(live)} radar{'s' if len(live) > 1 else ''} cover it · {ranges}"
                if friendly
                else f"kill {'them' if len(live) > 1 else 'it'} and this site goes "
                "autonomous"
            ),
            chip="CUEING",
            tone=LinkTone.GOOD,
        )

    if not covering:
        return IadsLink(
            caption="EARLY WARNING",
            title="Nothing covers this site",
            note="no radar in the network reaches it, so it sees only what its own "
            "radar sees",
            chip="NO COVER",
            tone=LinkTone.WARN,
        )

    nearest = covering[0]
    return IadsLink(
        places=_places_of([other.group.ground_object for other in covering]),
        caption="EARLY WARNING",
        title=" · ".join(sorted(_name(other) for other in covering)),
        note=_why_down(nearest),
        chip=_down_chip(nearest),
        tone=LinkTone.BAD if nearest.group.alive_units == 0 else LinkTone.WARN,
    )


def _cues_link(
    node: IadsNetworkNode, siblings: list[IadsNetworkNode], friendly: bool
) -> IadsLink:
    """For a radar the row flips: whom it cues, not who cues it."""
    covered_nodes = [
        other
        for other in siblings
        if other is not node
        and other.group.iads_role in (IadsRole.SAM, IadsRole.SAM_AS_EWR)
        and covers(node, other)
    ]
    covered_objectives = [other.group.ground_object for other in covered_nodes]
    covered = sorted(_name(other) for other in covered_nodes)
    if not comms_up(node):
        return IadsLink(
            caption="CUES",
            title="Nobody" if not covered else " · ".join(covered),
            note="it still sees, but its comms are cut and what it sees reaches nobody",
            chip="REACHES NOBODY",
            tone=LinkTone.WARN,
        )
    if not covered:
        return IadsLink(
            caption="CUES",
            title="No site in range",
            note="nothing of its own side sits inside its cover",
            chip="NOBODY",
            tone=LinkTone.INFO,
        )
    return IadsLink(
        places=_places_of(covered_objectives),
        more=max(0, len(covered_objectives) - NAMES_SHOWN),
        caption="CUES",
        title=_some_of(covered),
        note=(
            "they go autonomous if this radar dies"
            if friendly
            else "kill it and all of them go autonomous"
        ),
        chip=f"{len(covered)} SITE{'S' if len(covered) > 1 else ''}",
        tone=LinkTone.GOOD,
    )


def _directs_link(
    node: IadsNetworkNode, siblings: list[IadsNetworkNode], friendly: bool
) -> IadsLink:
    """What a command centre is for: the sites it directs."""
    directed_nodes = [
        other
        for other in siblings
        if other is not node
        and other.group.iads_role in (IadsRole.SAM, IadsRole.SAM_AS_EWR, IadsRole.EWR)
    ]
    directed_objectives = [other.group.ground_object for other in directed_nodes]
    directed = sorted(_name(other) for other in directed_nodes)
    if not directed:
        return IadsLink(
            caption="DIRECTS",
            title="Nothing on this side",
            note="no radar or battery of its own side is in the network",
            chip="NOBODY",
            tone=LinkTone.INFO,
        )
    return IadsLink(
        places=_places_of(directed_objectives),
        more=max(0, len(directed_objectives) - NAMES_SHOWN),
        caption="DIRECTS",
        title=_some_of(directed),
        note=(
            "they go autonomous if every command centre falls"
            if friendly
            else "kill the last command centre and all of them go autonomous"
        ),
        chip=f"{len(directed)} SITE{'S' if len(directed) > 1 else ''}",
        tone=LinkTone.GOOD,
    )


def _comms_link(node: IadsNetworkNode, friendly: bool) -> Optional[IadsLink]:
    """The comms this site hangs off, when the campaign gave it any."""
    nodes = [
        group
        for group in node.connections.values()
        if group.iads_role is IadsRole.CONNECTION_NODE
    ]
    if not nodes:
        return None
    names = _some_of(sorted(group.ground_object.name for group in nodes))
    if any(group.alive_units > 0 for group in nodes):
        return IadsLink(
            places=_places_of([group.ground_object for group in nodes]),
            caption="COMMS",
            title=names,
            note=(
                "the network reaches it"
                if friendly
                else "kill them all and it is cut off from the network"
            ),
            chip="UP",
            tone=LinkTone.GOOD,
        )
    return IadsLink(
        places=_places_of([group.ground_object for group in nodes]),
        caption="COMMS",
        title=names,
        note="destroyed: nothing reaches this site from the network",
        chip="CUT",
        tone=LinkTone.BAD,
    )


def _awacs_link(awacs: Sequence[str]) -> IadsLink:
    return IadsLink(
        caption="EARLY WARNING",
        title=" · ".join(awacs),
        note="counts as an early-warning radar while it flies",
        chip="CUES WHEN AIRBORNE",
        tone=LinkTone.INFO,
    )


def _command_link(
    node: IadsNetworkNode, siblings: list[IadsNetworkNode], friendly: bool
) -> IadsLink:
    caption = "COMMAND"
    centres = [
        other
        for other in siblings
        if other.group.iads_role is IadsRole.COMMAND_CENTER and other is not node
    ]
    if not centres:
        # An empty table is what Skynet's isCommandCenterUsable() answers true to.
        return IadsLink(
            caption=caption,
            title="No command centre in this network",
            note="the site needs none to be directed",
            chip="NOT NEEDED",
            tone=LinkTone.INFO,
        )

    live = [other for other in centres if _is_live(other)]
    if live:
        return IadsLink(
            places=_places_of([other.group.ground_object for other in live]),
            caption=caption,
            title=" · ".join(sorted(_name(other) for other in live)),
            note=(
                "powered, comms up"
                if friendly
                else "kill the last one standing and every site it directs goes "
                "autonomous"
            ),
            chip="REPORTS TO" if node.group.iads_role is IadsRole.EWR else "DIRECTING",
            tone=LinkTone.GOOD,
        )

    nearest = centres[0]
    return IadsLink(
        places=_places_of([other.group.ground_object for other in centres]),
        caption=caption,
        title=" · ".join(sorted(_name(other) for other in centres)),
        note=_why_down(nearest),
        chip=_down_chip(nearest),
        tone=LinkTone.BAD if nearest.group.alive_units == 0 else LinkTone.WARN,
    )


def _power_links(node: IadsNetworkNode, friendly: bool) -> list[IadsLink]:
    sources = [
        group
        for group in node.connections.values()
        if group.iads_role is IadsRole.POWER_SOURCE
    ]
    generator = own_generator(node.group)
    links: list[IadsLink] = []

    if not sources:
        links.append(
            IadsLink(
                caption="POWER",
                title="No grid link in this layout",
                note="nothing off-site can switch it off",
                chip="POWERED",
                tone=LinkTone.INFO,
            )
        )
    elif mains_are_up(node):
        links.append(
            IadsLink(
                places=_places_of([group.ground_object for group in sources]),
                caption="POWER",
                title=" · ".join(sorted(group.ground_object.name for group in sources)),
                note=(
                    "the grid reaches it"
                    if friendly or generator is not None
                    else "kill it and the site goes dark"
                ),
                chip="GRID UP",
                tone=LinkTone.GOOD,
            )
        )
    else:
        links.append(
            IadsLink(
                places=_places_of([group.ground_object for group in sources]),
                caption="POWER",
                title=" · ".join(sorted(group.ground_object.name for group in sources)),
                note=(
                    "its substation is down; the site runs on its own generator"
                    if generator is not None
                    else "its substation is down and the site stays switched off"
                ),
                chip="GRID DOWN",
                tone=LinkTone.WARN if generator is not None else LinkTone.BAD,
            )
        )

    if generator is not None:
        running = bool(sources) and not mains_are_up(node)
        links.append(
            IadsLink(
                caption="OWN POWER",
                title=generator,
                note=(
                    "one truck: bombing it switches the site off"
                    if not friendly
                    else "keeps the site up while the grid is down"
                ),
                chip="RUNNING ON IT" if running else "GENERATOR",
                tone=LinkTone.WARN if running else LinkTone.INFO,
            )
        )
    return links


def _feeds(tgo: TheaterGroundObject, network: IadsNetwork) -> list[IadsNetworkNode]:
    """The sites this piece of infrastructure is wired to."""
    return [
        node
        for node in network.nodes
        if any(group.ground_object is tgo for group in node.connections.values())
    ]


#: What a piece of infrastructure does for the sites behind it.
INFRASTRUCTURE_CAPTIONS = {
    IadsRole.POWER_SOURCE: "POWERS",
    IadsRole.CONNECTION_NODE: "CONNECTS",
}


def _infrastructure_role(tgo: TheaterGroundObject) -> Optional[IadsRole]:
    for group in tgo.groups:
        role = getattr(group, "iads_role", None)
        if role in (IadsRole.POWER_SOURCE, IadsRole.CONNECTION_NODE):
            assert isinstance(role, IadsRole)
            return role
    return None


def _what_falls_over(tgo: TheaterGroundObject, count: int) -> str:
    """What the sites behind this piece of infrastructure lose with it."""
    them = "they" if count > 1 else "it"
    role = _infrastructure_role(tgo)
    if role is IadsRole.POWER_SOURCE:
        return f"bomb it and {them} go dark, unless {them} carry a generator"
    if role is IadsRole.CONNECTION_NODE:
        return f"bomb it and {them} go autonomous, losing comms among {them}"
    return f"bomb it and {them} lose the network"


def _infrastructure(
    tgo: TheaterGroundObject, fed: list[IadsNetworkNode], friendly: bool
) -> IadsPicture:
    alive = any(unit.alive for group in tgo.groups for unit in group.units)
    names = sorted(_name(node) for node in fed)
    if alive:
        headline = f"Holding up {len(fed)} site{'s' if len(fed) > 1 else ''}."
        note = _what_falls_over(tgo, len(fed))
        chip_text = f"{len(fed)} SITE{'S' if len(fed) > 1 else ''}"
        tone = LinkTone.GOOD
    else:
        headline = "Destroyed: what it held up is on its own."
        note = "nothing reaches them through it any more"
        chip_text = "CUT"
        tone = LinkTone.BAD
    role = _infrastructure_role(tgo)
    link = IadsLink(
        places=_places_of([node.group.ground_object for node in fed]),
        caption=INFRASTRUCTURE_CAPTIONS.get(role, "FEEDS") if role else "FEEDS",
        title=_some_of(names),
        note=note,
        chip=chip_text,
        tone=tone,
    )
    return IadsPicture(None, gives=(link,), headline=headline)


# --------------------------------------------------------------------- helpers


def _node_for(
    tgo: TheaterGroundObject, network: IadsNetwork
) -> Optional[IadsNetworkNode]:
    for node in network.nodes:
        if node.group.ground_object is tgo:
            return node
    return None


def _same_side(node: IadsNetworkNode, network: IadsNetwork) -> list[IadsNetworkNode]:
    side = node.group.ground_object.control_point.captured
    return [
        other
        for other in network.nodes
        if other.group.ground_object.control_point.captured == side
    ]


def _is_live(node: IadsNetworkNode) -> bool:
    return (
        node.group.alive_units > 0
        and (mains_are_up(node) or own_generator(node.group) is not None)
        and comms_up(node)
    )


def _down_chip(node: IadsNetworkNode) -> str:
    if node.group.alive_units == 0:
        return "DESTROYED"
    if not comms_up(node):
        return "LINK CUT"
    return "NO POWER"


def _why_down(node: IadsNetworkNode) -> str:
    if node.group.alive_units == 0:
        return "destroyed"
    if not comms_up(node):
        cut = sorted(
            group.ground_object.name
            for group in node.connections.values()
            if group.iads_role is IadsRole.CONNECTION_NODE and group.alive_units == 0
        )
        where = f" ({' · '.join(cut)})" if cut else ""
        return f"it stands, but its comms node is destroyed{where}, so nothing reaches"
    return "it stands, but it has no power, so it is switched off"


#: How many objectives a row names before it starts counting them instead.
NAMES_SHOWN = 4


def _places_of(
    objectives: Sequence[TheaterGroundObject], most: int = NAMES_SHOWN
) -> tuple[Place, ...]:
    """The first few objectives named in a row, in the order the title lists them."""
    named = sorted(objectives, key=lambda tgo: str(tgo.name))
    return tuple(Place(str(tgo.name), tgo) for tgo in named[:most])


def _some_of(names: list[str], most: int = NAMES_SHOWN) -> str:
    """The names, or how many there are once a list stops being readable."""
    if len(names) <= most:
        return " · ".join(names)
    return f"{' · '.join(names[:most])} and {len(names) - most} more"


def _name(node: IadsNetworkNode) -> str:
    return str(node.group.ground_object.name)
