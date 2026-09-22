from types import SimpleNamespace

from game.ato.package import Package
from game.ato.packagewaypoints import PackageWaypoints
from game.data.doctrine import ALL_DOCTRINES
from game.utils import meters, nautical_miles


def _fake_package(waypoints: object, standoff: object) -> Package:
    # waypoints_need_regeneration/max_standoff_range only touch these attributes, so a
    # lightweight stand-in avoids building a whole campaign just to exercise the logic.
    return SimpleNamespace(  # type: ignore[return-value]
        waypoints=waypoints,
        max_standoff_range=lambda: standoff,
    )


def test_waypoints_regenerate_when_never_built() -> None:
    package = _fake_package(waypoints=None, standoff=nautical_miles(160))
    assert Package.waypoints_need_regeneration(package) is True


def test_waypoints_kept_when_standoff_range_unchanged() -> None:
    waypoints = SimpleNamespace(standoff_range=nautical_miles(160))
    package = _fake_package(waypoints=waypoints, standoff=nautical_miles(160))
    assert Package.waypoints_need_regeneration(package) is False


def test_waypoints_regenerate_when_standoff_range_changes() -> None:
    # Payload swapped from a Kh-22 (160nm) loadout to short-range bombs.
    waypoints = SimpleNamespace(standoff_range=nautical_miles(160))
    package = _fake_package(waypoints=waypoints, standoff=None)
    assert Package.waypoints_need_regeneration(package) is True

    # And the reverse: unranged loadout swapped up to a stand-off weapon.
    waypoints = SimpleNamespace(standoff_range=None)
    package = _fake_package(waypoints=waypoints, standoff=nautical_miles(160))
    assert Package.waypoints_need_regeneration(package) is True


def test_doctrine_unchanged_when_no_standoff_weapon() -> None:
    doctrine = ALL_DOCTRINES[0]
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, None, nautical_miles(300)
    )
    assert result is doctrine


def test_doctrine_ingress_lowered_to_a_short_weapon_range() -> None:
    """A flight of JDAMs has no business starting its run where a JSOW would.

    The doctrine's ceiling is where every straight-in package ends up, because the IP
    solver takes the point nearest the departure that the rules allow.
    """
    doctrine = ALL_DOCTRINES[0]
    short_range = doctrine.max_ingress_distance / 2
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, short_range, nautical_miles(300)
    )
    assert result.max_ingress_distance == short_range


def test_a_weapon_shorter_than_the_floor_brings_the_whole_ring_down() -> None:
    """An eight-mile Maverick should not start its run forty-five miles out.

    The ceiling cannot come down to meet the floor, because a ring with no width
    between them contains no points and every strategy fails, so both move
    together.
    """
    doctrine = ALL_DOCTRINES[0]
    reach = doctrine.min_ingress_distance / 2
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, reach, nautical_miles(300)
    )
    assert result.max_ingress_distance == reach
    assert result.max_ingress_distance > result.min_ingress_distance


def test_a_weapon_with_no_reach_at_all_leaves_the_doctrine_alone() -> None:
    """There is no reach to place the run at, and a ring of no width is not an
    answer."""
    doctrine = ALL_DOCTRINES[0]
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, meters(0), nautical_miles(300)
    )
    assert result.max_ingress_distance == doctrine.max_ingress_distance
    assert result.max_ingress_distance > result.min_ingress_distance


def test_doctrine_left_alone_when_the_target_is_nearer_than_the_minimum() -> None:
    """A CAS package from a base nine miles from the front line.

    The ingress window is the ring between the doctrine's minimum and maximum, and
    the distance to the target was shorter than the minimum, so clamping the ceiling
    up to the floor closed the ring: 'No solutions found for waypoint', and no CAS
    from that base at all.
    """
    doctrine = ALL_DOCTRINES[0]
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, nautical_miles(100), doctrine.min_ingress_distance - meters(1)
    )
    assert result.max_ingress_distance > result.min_ingress_distance


def test_the_ingress_window_is_never_closed() -> None:
    """Whatever the weapon and wherever the target, there is somewhere to put the IP."""
    for doctrine in ALL_DOCTRINES:
        for weapon_range in [meters(0), nautical_miles(3), nautical_miles(45)]:
            for distance in [meters(1), nautical_miles(9), nautical_miles(300)]:
                result = PackageWaypoints.doctrine_for_weapon_range(
                    doctrine, weapon_range, distance
                )
                assert (
                    result.max_ingress_distance > result.min_ingress_distance
                ), f"{doctrine.name}: {weapon_range} weapon, target {distance} away"


def test_doctrine_ingress_raised_to_standoff_range() -> None:
    # Regression for issue #34: a Kh-22-class range should widen the ingress distance.
    doctrine = ALL_DOCTRINES[0]
    standoff = doctrine.max_ingress_distance + nautical_miles(50)
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, standoff, nautical_miles(300)
    )
    assert result.max_ingress_distance == standoff


def test_doctrine_ingress_clamped_to_departure_target_distance() -> None:
    # Regression for Druss99's PR #888 review: a stand-off range longer than the
    # route itself must not push the ingress point past the departure (off the
    # route / off the map); it should clamp to the distance actually available.
    doctrine = ALL_DOCTRINES[0]
    distance_to_target = doctrine.max_ingress_distance + nautical_miles(20)
    standoff = distance_to_target + nautical_miles(500)
    result = PackageWaypoints.doctrine_for_weapon_range(
        doctrine, standoff, distance_to_target
    )
    assert result.max_ingress_distance == distance_to_target
    assert result.max_ingress_distance < standoff
