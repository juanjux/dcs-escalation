from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel

from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import reserve_armor_for
from game.missiongenerator.motorpoolpopulator import (
    MotorpoolPopulator,
    motorpools_at,
    select_capped,
)
from game.server.leaflet import LeafletPoint
from game.theater.iadsnetwork.iadsstate import IadsStatus
from game.theater.theatergroundobject import MotorpoolGroundObject, ShipGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject


class AggregateGroundUnitEntry(BaseModel):
    unit_type: str
    display_name: str
    count: int


class TgoJs(BaseModel):
    id: UUID
    name: str
    control_point_name: str
    category: str
    blue: bool
    position: LeafletPoint
    units: list[str]  # TODO: Event stream
    reserve_units: list[str]
    expected_inventory: list[AggregateGroundUnitEntry]
    unrendered_reserve: list[AggregateGroundUnitEntry]
    in_transit_units: list[AggregateGroundUnitEntry]
    threat_ranges: list[float]  # TODO: Event stream
    detection_ranges: list[float]  # TODO: Event stream
    # How far this site denies GPS, in metres, when it is a live jamming site and the
    # plugin is on. Its own reach, not its threat: a jamming site's threat ring is
    # whatever point defence it carries, a couple of miles, which is not the circle
    # anyone is looking for.
    jamming_range: Optional[float]
    dead: bool  # TODO: Event stream
    # Whether the group can be rebuilt or repaired, so the map's "destroyed
    # (non-repairable)" layer must NOT hide it even when dead: re-purchasable
    # groups (SAM/EWR/armor), or buildings the building-repair feature can rebuild.
    # (Wire name kept as `purchasable` for the JS client; value is tgo.repairable.)
    purchasable: bool
    # Repairs pending on this group's dead units. The client shows the health bar
    # ORANGE (instead of the damaged yellow) while this is true, for partial and
    # fully-dead groups alike.
    repairing: bool
    sidc: str  # TODO: Event stream
    task: Optional[tuple[str, str]]
    mobile: bool
    destination: Optional[LeafletPoint]
    # What the IADS will do with this site when the mission starts: "networked",
    # "autonomous" or "dark", or None for anything that is not part of an IADS. Derived
    # from the network, because DCS never reports it back.
    iads_state: Optional[str]
    # Why, in a line, for the tooltip.
    iads_reason: Optional[str]
    # Nothing left that can find a target for itself.
    iads_blind: bool

    class Config:
        title = "Tgo"

    @staticmethod
    def _jamming_range_of(tgo: TheaterGroundObject) -> Optional[float]:
        """Metres of GPS denial, or None. Ground truth, the same record the runtime
        gets, so the ring the map draws is the bubble the weapons actually eat."""
        from game.gpsjamming import jamming_reach_for

        game = getattr(
            getattr(getattr(tgo, "control_point", None), "coalition", None),
            "game",
            None,
        )
        if game is None:
            return None
        reach = jamming_reach_for(game, tgo)
        return reach.meters if reach is not None else None

    @staticmethod
    def _iads_status(tgo: TheaterGroundObject) -> Optional[IadsStatus]:
        """What Skynet will do with this site, if it is in an IADS at all.

        Reached through the theater rather than passed in, because single-TGO updates
        come through the event stream one at a time. The network caches the answer for
        the whole map and throws it away when anything dies, so asking per site is
        cheap.
        """
        theater = getattr(getattr(tgo, "control_point", None), "theater", None)
        network = getattr(theater, "iads_network", None)
        if network is None:
            return None
        return network.state_map.status_for(tgo)

    @staticmethod
    def _aggregate_entries(
        counts: dict[GroundUnitType, int],
    ) -> list[AggregateGroundUnitEntry]:
        return [
            AggregateGroundUnitEntry(
                unit_type=unit_type.variant_id,
                display_name=unit_type.display_name,
                count=count,
            )
            for unit_type, count in sorted(
                counts.items(), key=lambda item: item[0].variant_id
            )
            if count > 0
        ]

    @staticmethod
    def for_tgo(tgo: TheaterGroundObject) -> TgoJs:
        # Only include non-zero ranges: a zero-radius circle renders as a stray
        # dot (normally hidden under the unit icon, but visible once the icon is
        # hidden by the destroyed-object layers). Matches ControlPointJs.
        threat_ranges = [
            meters
            for meters in (group.max_threat_range().meters for group in tgo.groups)
            if meters > 0
        ]
        detection_ranges = [
            meters
            for meters in (group.max_detection_range().meters for group in tgo.groups)
            if meters > 0
        ]
        jamming_range = TgoJs._jamming_range_of(tgo)
        if tgo.control_point.captured.is_blue:
            blue = True
        else:
            blue = False
        mobile = isinstance(tgo, ShipGroundObject) and blue
        destination: Optional[LeafletPoint] = None
        if (
            isinstance(tgo, ShipGroundObject)
            and blue
            and tgo.target_position is not None
        ):
            destination = LeafletPoint.from_latlng(tgo.target_position.latlng())
        iads = TgoJs._iads_status(tgo)
        reserve_units: list[str] = []
        expected_inventory: list[AggregateGroundUnitEntry] = []
        unrendered_reserve: list[AggregateGroundUnitEntry] = []
        in_transit_units: list[AggregateGroundUnitEntry] = []
        if isinstance(tgo, MotorpoolGroundObject):
            MotorpoolPopulator(
                tgo.control_point.coalition.game
            ).populate_control_points([tgo.control_point])
            reserve_units = [unit.display_name for unit in tgo.units]
            motorpools = motorpools_at(tgo.control_point)
            if motorpools and motorpools[0] is tgo:
                reserve = reserve_armor_for(tgo.control_point)
                pending_orders = tgo.control_point.ground_unit_orders.units
                current_inventory = {
                    unit_type: tgo.control_point.base.total_units_of_type(unit_type)
                    for unit_type in set(tgo.control_point.base.armor)
                    | set(pending_orders)
                }
                expected_inventory = TgoJs._aggregate_entries(
                    {
                        unit_type: count
                        + tgo.control_point.ground_unit_orders.pending_orders(unit_type)
                        for unit_type, count in current_inventory.items()
                    }
                )
                settings = tgo.control_point.coalition.game.settings
                selected = (
                    select_capped(reserve, settings.motorpool_spawn_cap)
                    if settings.motorpool_enabled
                    else {}
                )
                unrendered_reserve = TgoJs._aggregate_entries(
                    {
                        unit_type: count - selected.get(unit_type, 0)
                        for unit_type, count in reserve.items()
                    }
                )
                transit: defaultdict[GroundUnitType, int] = defaultdict(int)
                for coalition in tgo.control_point.coalition.game.coalitions:
                    for transfer in coalition.transfers:
                        if transfer.origin != tgo.control_point:
                            continue
                        for unit_type, count in transfer.units.items():
                            transit[unit_type] += count
                in_transit_units = TgoJs._aggregate_entries(dict(transit))
        return TgoJs(
            id=tgo.id,
            name=tgo.name,
            control_point_name=tgo.control_point.name,
            category=tgo.category,
            blue=blue,
            position=tgo.position.latlng(),
            units=[unit.display_name for unit in tgo.units],
            reserve_units=reserve_units,
            expected_inventory=expected_inventory,
            unrendered_reserve=unrendered_reserve,
            in_transit_units=in_transit_units,
            threat_ranges=threat_ranges,
            detection_ranges=detection_ranges,
            jamming_range=jamming_range,
            dead=tgo.is_dead,
            purchasable=tgo.repairable,
            repairing=tgo.has_pending_repairs,
            sidc=str(tgo.sidc()),
            task=(
                (
                    tgo.groups[0].ground_object.task.description,
                    tgo.groups[0].ground_object.task.role.value,
                )
                if tgo.groups and tgo.groups[0].ground_object.task is not None
                else None
            ),
            mobile=mobile,
            destination=destination,
            iads_state=iads.state.value if iads is not None else None,
            iads_reason=iads.reason if iads is not None else None,
            iads_blind=iads is not None and iads.blind,
        )

    @staticmethod
    def all_in_game(game: Game) -> list[TgoJs]:
        tgos = []
        for control_point in game.theater.controlpoints:
            for tgo in control_point.connected_objectives:
                if not tgo.is_control_point:
                    tgos.append(TgoJs.for_tgo(tgo))
        return tgos
