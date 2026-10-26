"""Native routes and loaded cargo for dispatched armor detachments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dcs import Point
from dcs.point import PointAction

from game.groundmovement.dispatch import active_transit, validate_transit
from game.groundmovement.orders import GroundPosition
from game.groundmovement.settings import distance_per_turn, enabled
from game.unitmap import TheaterUnitMapping
from game.utils import kph

if TYPE_CHECKING:
    from game.missiongenerator.tgogenerator import GroundObjectGenerator


def generate_armor_movement(generator: GroundObjectGenerator) -> None:
    game, tgo = generator.game, generator.ground_object
    transit = active_transit(game, tgo.id)
    if transit is None:
        raise ValueError("A moving detachment has no saved movement order")
    if generator.culled:
        return
    units = [u for u in tgo.units if u.alive and u.transported_by_id is None]
    if not units:
        return
    group = generator.create_vehicle_group(tgo.groups[0].group_name, units)
    origin = transit.journey.position
    dx, dz = origin.x - group.units[0].position.x, origin.z - group.units[0].position.y
    for unit in group.units:
        unit.position = Point(
            unit.position.x + dx, unit.position.y + dz, generator.m.terrain
        )
    group.points[0].position = Point(origin.x, origin.z, generator.m.terrain)
    # Cargo is not a second physical gun left firing at the departure point.
    native_by_id = {campaign.id: native for campaign, native in zip(units, group.units)}
    for cargo in tgo.units:
        if cargo.alive and cargo.transported_by_id is not None:
            tractor = native_by_id.get(cargo.transported_by_id)
            if tractor is None:
                raise ValueError("A surviving loaded piece has no surviving tractor")
            generator.unit_map.ground_transport_cargo.setdefault(
                str(tractor.name), []
            ).append(TheaterUnitMapping(cargo, tractor))
    journey = transit.journey
    points: tuple[GroundPosition, ...] = (origin,)
    allowed = enabled(game.settings)
    if allowed:
        try:
            validate_transit(game, transit)
        except (ValueError, PermissionError):
            allowed = False
    if allowed:
        points = journey.preview(
            distance_per_turn(game.settings, on_road=True),
            distance_per_turn(game.settings, on_road=False),
        )
    departure = group.points[0]
    if len(points) == 1:
        departure.speed = 0
        departure.action = PointAction.OffRoad
        return
    first = journey.route.segments[journey.segment_index]
    departure.action = PointAction.OnRoad if first.on_road else PointAction.OffRoad
    departure.speed = kph(40 if first.on_road else 20).meters_per_second
    departure.ETA_locked = False
    departure.speed_locked = True
    group.units[0].heading = departure.position.heading_between_point(
        Point(points[1].x, points[1].z, generator.m.terrain)
    )
    for index, point in enumerate(points[1:], journey.segment_index):
        on_road = journey.route.segments[index].on_road
        group.add_waypoint(
            Point(point.x, point.z, generator.m.terrain),
            speed=40 if on_road else 20,
            move_formation=PointAction.OnRoad if on_road else PointAction.OffRoad,
        )
