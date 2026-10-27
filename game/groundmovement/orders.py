"""Saved planning reservations. Dispatch and inventory transfers are separate."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Mapping, TYPE_CHECKING
from uuid import UUID, uuid4

from game.groundmovement.mobility import MobilityMode
from game.groundmovement.settings import enabled
from game.theater.player import Player

if TYPE_CHECKING:
    from game.groundmovement.dispatch import ArmorTransit
    from game.dcs.groundunittype import GroundUnitType
    from game.settings import Settings


class MovementSource(Enum):
    ARMOR = "armor"
    SAM = "sam"
    BASE = "base"


class DestinationKind(Enum):
    POSITION = "position"
    BASE = "base"
    FRONTLINE = "frontline"


@dataclass(frozen=True)
class GroundPosition:
    x: float
    z: float

    def __post_init__(self) -> None:
        if any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in (self.x, self.z)
        ):
            raise ValueError("Ground positions require finite coordinates")


@dataclass(frozen=True)
class MovementDestination:
    kind: DestinationKind
    position: GroundPosition
    target_id: UUID | None = None
    opposing_base_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DestinationKind):
            raise ValueError("Unknown movement destination kind")
        if (self.kind is DestinationKind.POSITION) != (self.target_id is None):
            raise ValueError("Base and frontline destinations require a base ID")
        if (self.kind is DestinationKind.FRONTLINE) != (
            self.opposing_base_id is not None
        ):
            raise ValueError("A frontline destination requires both base IDs")
        if (
            self.opposing_base_id is not None
            and self.opposing_base_id == self.target_id
        ):
            raise ValueError("A frontline needs two different bases")


@dataclass(frozen=True)
class TransportManifest:
    unit_ids: tuple[int, ...]
    # One (piece ID, tractor ID) pair per towed piece; loaded from mission start.
    towing: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        ids = set(self.unit_ids)
        pieces, tractors = [p for p, _ in self.towing], [t for _, t in self.towing]
        if not ids or len(ids) != len(self.unit_ids):
            raise ValueError("A transport manifest requires distinct units")
        if any(type(unit_id) is not int or unit_id < 0 for unit_id in ids):
            raise ValueError("Invalid ground unit ID")
        if (
            len(set(pieces)) != len(pieces)
            or len(set(tractors)) != len(tractors)
            or set(pieces) & set(tractors)
            or not (set(pieces) | set(tractors)) <= ids
        ):
            raise ValueError("Each towed piece requires its own included tractor")


def plan_transport(
    units: Mapping[int, GroundUnitType], selected: Iterable[int]
) -> TransportManifest:
    """Add only the available tractors needed by the selected detachment."""
    selected_ids = tuple(selected)
    if not selected_ids or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("Select distinct ground units")
    if any(type(i) is not int or i not in units for i in selected_ids):
        raise ValueError("A selected unit is unavailable or already reserved")
    pieces = []
    for unit_id in selected_ids:
        mobility = units[unit_id].ground_mobility
        if mobility.mode in (MobilityMode.UNKNOWN, MobilityMode.FIXED):
            raise ValueError(
                f"Mobility is not available for {units[unit_id].display_name}"
            )
        if mobility.mode is MobilityMode.TOWED:
            pieces.append(unit_id)
    selected_set = set(selected_ids)
    tractors = sorted(
        (i for i in units if units[i].ground_mobility.can_tow),
        key=lambda i: (i not in selected_set, i),
    )
    if len(pieces) > len(tractors):
        raise ValueError(
            f"{len(pieces)} towed pieces require {len(pieces)} tractors; "
            f"only {len(tractors)} are available. Select a smaller detachment."
        )
    towing = tuple(zip(sorted(pieces), tractors[: len(pieces)]))
    moving = tuple(sorted(selected_set | {tractor for _, tractor in towing}))
    return TransportManifest(moving, towing)


@dataclass(frozen=True)
class GroundMovementOrder:
    id: UUID
    source_id: UUID
    source_kind: MovementSource
    owner: Player
    origin: GroundPosition
    destination: MovementDestination
    manifest: TransportManifest
    created_turn: int
    cancelled: bool = False
    completed: bool = False

    def status(self, settings: Settings) -> str:
        if self.cancelled:
            return "cancelled"
        if self.completed:
            return "completed"
        return "planned" if enabled(settings) else "paused"


@dataclass
class GroundMovementOrders:
    orders: dict[UUID, GroundMovementOrder] = field(default_factory=dict)
    transits: dict[UUID, ArmorTransit] = field(default_factory=dict)

    def __setstate__(self, state: dict[str, object]) -> None:
        self.__dict__.update(state)
        self.__dict__.setdefault("transits", {})

    @property
    def reserved_unit_ids(self) -> set[int]:
        return {
            unit_id
            for order in self.orders.values()
            if not order.cancelled and not order.completed
            for unit_id in order.manifest.unit_ids
        }

    def plan(
        self,
        settings: Settings,
        *,
        source_id: UUID,
        source_kind: MovementSource,
        owner: Player,
        origin: GroundPosition,
        destination: MovementDestination,
        units: Mapping[int, GroundUnitType],
        selected: Iterable[int],
        turn: int,
    ) -> GroundMovementOrder:
        """Reserve source unit identities without moving or copying their inventory.

        This is an internal planning operation. Source ownership, destination
        ownership and terrain routes must be checked by dispatch before travel.
        """
        if not enabled(settings):
            raise ValueError("Ground Movement requires its plugin and Motor Pool")
        if not isinstance(source_kind, MovementSource) or owner not in (
            Player.BLUE,
            Player.RED,
        ):
            raise ValueError("Invalid ground movement source or owner")
        if type(turn) is not int or turn < 0:
            raise ValueError("Invalid movement turn")
        if (
            source_kind is MovementSource.SAM
            and destination.kind is not DestinationKind.POSITION
        ):
            raise ValueError(
                "SAM sites can relocate but cannot join bases or frontlines"
            )
        reserved = self.reserved_unit_ids
        manifest = plan_transport(
            {i: u for i, u in units.items() if i not in reserved}, selected
        )
        if source_kind is MovementSource.SAM and set(manifest.unit_ids) != set(units):
            raise ValueError("Partial SAM moves require an operational-site validation")
        order = GroundMovementOrder(
            uuid4(), source_id, source_kind, owner, origin, destination, manifest, turn
        )
        self.orders[order.id] = order
        return order

    def cancel(self, order_id: UUID) -> None:
        """Release a planning reservation; no travel or inventory has been applied."""
        if order_id in self.transits and not self.transits[order_id].finished:
            raise ValueError("Stop the dispatched detachment at its current position")
        self.orders[order_id] = replace(self.orders[order_id], cancelled=True)
