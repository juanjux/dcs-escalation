from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Optional, TYPE_CHECKING

from dcs import Point

from game.ato.flightplans.waypointbuilder import WaypointBuilder
from game.data.doctrine import Doctrine
from game.flightplan import JoinZoneGeometry
from game.flightplan.ipsolver import IpSolver
from game.flightplan.refuelzonegeometry import RefuelZoneGeometry
from game.persistency import waypoint_debug_directory
from game.utils import Distance, dcs_to_shapely_point
from game.utils import meters, nautical_miles

if TYPE_CHECKING:
    from game.ato import Package
    from game.coalition import Coalition


#: How far along the route home the package forms up. The join has to be early
#: enough that whatever joins there -- an escort, above all -- is with the package for
#: most of the trip, and it has to be on the route or the flight leaves its track to
#: reach it.
JOIN_FRACTION = 0.355


def join_along_route(
    coalition: Coalition, home: Point, ingress: Point
) -> Optional[Point]:
    """The point a third of the way along the route from home to the ingress.

    The route is the navmesh path, which is what the flight will fly, so a point on it
    costs nothing to reach. None when the navmesh cannot path between the two, and the
    caller falls back to the zone geometry.
    """
    try:
        path = coalition.nav_mesh.shortest_path(home, ingress)
    except Exception:
        return None
    if len(path) < 2:
        return None

    legs = [(a, b, a.distance_to_point(b)) for a, b in zip(path, path[1:])]
    total = sum(leg for _, _, leg in legs)
    if not total:
        return None

    # Never so far along that it lands on top of the ingress.
    join_distance = coalition.doctrine.join_distance.meters
    wanted = min(total * JOIN_FRACTION, max(total - join_distance, 0.0))

    walked = 0.0
    for a, b, leg in legs:
        if walked + leg >= wanted:
            if not leg:
                return a
            return a.point_from_heading(a.heading_between_point(b), wanted - walked)
        walked += leg
    return path[-2]


#: Where the inner edge of the IP ring goes when the outer edge has come below the
#: doctrine's own floor. It only has to leave the solver somewhere to look: the
#: solver takes the point furthest from the target that the rules allow, which is
#: the outer edge, so this value decides nothing except that the ring is not empty.
INGRESS_RING_FLOOR = 0.6


@dataclass
class PackageWaypoints:
    join: Point
    ingress: Point
    initial: Point
    split: Point
    refuel: Point

    #: The package's longest stand-off launch range at the time these waypoints were
    #: built. Used to detect when a payload change invalidates the ingress point.
    standoff_range: Optional[Distance] = None

    @staticmethod
    def doctrine_for_weapon_range(
        doctrine: Doctrine,
        weapon_range: Optional[Distance],
        distance_to_target: Distance,
    ) -> Doctrine:
        """Put the attack run where the package can actually shoot from.

        The ingress point is where the attack task begins, so it belongs at the range
        the weapons are used from -- in both directions. A Tu-16 with Kh-22s has no
        business being dragged in to the doctrine's ingress point, and a flight of
        JDAMs has none starting its run forty-five miles out, which is where the
        doctrine's ceiling puts every straight-in package: the IP solver takes the
        point nearest the departure that the rules allow, and on a straight route
        that is always the furthest one from the target.

        Only what is known moves it. A weapon with no range in its data -- a dumb
        bomb, a rocket -- leaves the doctrine alone.

        Bounded above by the distance to the target: some IpSolver strategies (the
        backtracking fallbacks used when the primary ones find no safe IP) do not
        otherwise bound the search area, and a 200 nm missile on a much shorter route
        could send the IP far off the route or off the map.

        Under the doctrine's own floor the whole ring comes down, not the ceiling
        alone. The solver looks for the IP between the minimum and maximum ingress
        distance, and a ring whose inner and outer radius are equal contains no
        points, so lowering the ceiling to meet the floor made the package
        unplannable and the previous answer was to leave the ceiling alone. That
        put an eight-mile Maverick's attack run forty-five miles out. Both radii
        move together instead.
        """
        if weapon_range is None:
            return doctrine
        wanted = min(weapon_range, distance_to_target)
        if not wanted:
            # No reach to place the run at, so the doctrine keeps its own figures
            # rather than being given a ring of no width.
            return doctrine
        if wanted <= doctrine.min_ingress_distance:
            return replace(
                doctrine,
                max_ingress_distance=wanted,
                min_ingress_distance=wanted * INGRESS_RING_FLOOR,
            )
        if wanted == doctrine.max_ingress_distance:
            return doctrine
        return replace(doctrine, max_ingress_distance=wanted)

    @staticmethod
    def create(
        package: Package, coalition: Coalition, dump_debug_info: bool
    ) -> PackageWaypoints:
        origin = package.departure_closest_to_target()

        standoff_range = package.max_standoff_range()
        distance_to_target = meters(
            origin.position.distance_to_point(package.target.position)
        )
        doctrine = PackageWaypoints.doctrine_for_weapon_range(
            coalition.doctrine, standoff_range, distance_to_target
        )

        # Start by picking the best IP for the attack.
        ip_solver = IpSolver(
            dcs_to_shapely_point(origin.position),
            dcs_to_shapely_point(package.target.position),
            doctrine,
            coalition.opponent.threat_zone.air_defenses,
        )
        ip_solver.set_debug_properties(
            waypoint_debug_directory() / "IP", coalition.game.theater.terrain
        )
        ingress_point_shapely = ip_solver.solve()
        if dump_debug_info:
            ip_solver.dump_debug_info()

        ingress_point = origin.position.new_in_same_map(
            ingress_point_shapely.x, ingress_point_shapely.y
        )

        tgt_point = package.target.position
        initial_point = PackageWaypoints.get_initial_point(ingress_point, tgt_point)

        join_point = (
            join_along_route(coalition, origin.position, ingress_point)
            or JoinZoneGeometry(
                package.target.position,
                origin.position,
                ingress_point,
                coalition,
            ).find_best_join_point()
        )

        # Join/split are derived from this base join_point. JoinZoneGeometry
        # fixes the base join distance between 35% and 36% of the home-to-target
        # leg, and WaypointBuilder.perturb then applies a small offset to
        # produce the final join/split waypoints.

        refuel_point = RefuelZoneGeometry(
            origin.position,
            join_point,
            coalition,
        ).find_best_refuel_point()

        # And the split point based on the best route from the IP. Since that's no
        # different than the best route *to* the IP, this is the same as the join point.
        # TODO: Estimate attack completion point based on the IP and split from there?
        return PackageWaypoints(
            WaypointBuilder.perturb(join_point),
            ingress_point,
            initial_point,
            WaypointBuilder.perturb(join_point),
            refuel_point,
            standoff_range,
        )

    @staticmethod
    def get_initial_point(ingress_point: Point, tgt_point: Point) -> Point:
        hdg = tgt_point.heading_between_point(ingress_point)
        # Generate a waypoint randomly between 7 & 9 NM
        dist = nautical_miles(random.random() * 2 + 7).meters
        initial_point = tgt_point.point_from_heading(hdg, dist)
        return initial_point
