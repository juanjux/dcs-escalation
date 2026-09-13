from __future__ import annotations

from enum import Enum

from typing import Any

from game.data.groups import GroupTask
from game.utils import Distance, meters, nautical_miles

#: What the two reach when Escalation works a network out by distance rather than
#: reading it from the campaign. Plugin options, so a theatre whose infrastructure is
#: further apart than this can say so.
DEFAULT_COMMS_RANGE_NM = 15.0
DEFAULT_POWER_RANGE_NM = 35.0


class IadsRole(Enum):
    #: A radar SAM that should be controlled by Skynet.
    SAM = "Sam"

    #: A radar SAM that should be controlled and used as an EWR by Skynet.
    SAM_AS_EWR = "SamAsEwr"

    #: An air defense unit that should be used as point defense by Skynet.
    POINT_DEFENSE = "PD"

    #: An ewr unit that should provide information to the Skynet IADS.
    EWR = "Ewr"

    #: IADS Elements which allow the advanced functions of Skynet.
    CONNECTION_NODE = "ConnectionNode"
    POWER_SOURCE = "PowerSource"
    COMMAND_CENTER = "CommandCenter"

    #: All other types of groups that might be present in a SAM TGO. This includes
    #: SHORADS, AAA, supply trucks, etc. Anything that shouldn't be controlled by Skynet
    #: should use this role.
    NO_BEHAVIOR = "NoBehavior"

    @classmethod
    def for_task(cls, task: GroupTask) -> IadsRole:
        if task == GroupTask.COMMS:
            return cls.CONNECTION_NODE
        elif task == GroupTask.POWER:
            return cls.POWER_SOURCE
        elif task == GroupTask.COMMAND_CENTER:
            return cls.COMMAND_CENTER
        elif task == GroupTask.POINT_DEFENSE:
            return cls.POINT_DEFENSE
        elif task == GroupTask.LORAD:
            return cls.SAM_AS_EWR
        elif task == GroupTask.MERAD:
            return cls.SAM
        elif task == GroupTask.SHORAD:
            return cls.SAM
        elif task in [
            GroupTask.EARLY_WARNING_RADAR,
            GroupTask.NAVY,
            GroupTask.AIRCRAFT_CARRIER,
            GroupTask.HELICOPTER_CARRIER,
            GroupTask.AAA,
        ]:
            return cls.EWR
        return cls.NO_BEHAVIOR

    @classmethod
    def for_category(cls, category: str) -> IadsRole:
        if category == "comms":
            return cls.CONNECTION_NODE
        elif category == "power":
            return cls.POWER_SOURCE
        elif category == "commandcenter":
            return cls.COMMAND_CENTER
        return cls.NO_BEHAVIOR

    def connection_range(self, settings: Any = None) -> Distance:
        """How far this piece of infrastructure feeds, by distance.

        Only consulted when the network is computed rather than read from the
        campaign: a designer who wires an IADS by hand says what is connected to
        what, and no range is applied to it.
        """
        if self == IadsRole.CONNECTION_NODE:
            return nautical_miles(
                _range_option(settings, "commsRangeNm", DEFAULT_COMMS_RANGE_NM)
            )
        if self == IadsRole.POWER_SOURCE:
            return nautical_miles(
                _range_option(settings, "powerRangeNm", DEFAULT_POWER_RANGE_NM)
            )
        return meters(0)

    @property
    def participate(self) -> bool:
        # Returns true if the Role participates in the skynet
        # This will exclude NoBehaviour and PD for the time beeing
        return self not in [
            IadsRole.NO_BEHAVIOR,
            IadsRole.POINT_DEFENSE,
        ]

    @property
    def is_comms_or_power(self) -> bool:
        return self in [
            IadsRole.POWER_SOURCE,
            IadsRole.CONNECTION_NODE,
        ]


def _range_option(settings: Any, mnemonic: str, default: float) -> float:
    """The plugin option, or the default for a settings object that never had it."""
    if settings is None:
        return default
    value = settings.plugin_option_or(f"skynetiads.{mnemonic}", default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
