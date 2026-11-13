"""Tests for the escort-hold placement of EscortFlightPlan.Builder.

An escort tasked to protect an AWACS or tanker must hold on that flight's
racetrack orbit, which is stationed far from the package's target reference.
``_racetrack_hold_point`` returns the racetrack center for such (patrolling)
primaries and ``None`` for everything else. Attack escorts hold at their ingress;
transport escorts retain their drop-off protection.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from dcs.mapping import Point

from game.ato.flightplans.airassault import AirAssaultLayout
from game.ato.flightplans.airlift import AirliftLayout
from game.ato.flightplans.escort import Builder
from game.ato.flightplans.patrolling import PatrollingLayout
from game.ato.flighttype import FlightType
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.packagewaypoints import PackageWaypoints
from game.theater.player import Player
from game.utils import feet, nautical_miles


def _patrolling_primary(start: Point, end: Point) -> SimpleNamespace:
    layout = object.__new__(PatrollingLayout)
    layout.patrol_start = SimpleNamespace(position=start)
    layout.patrol_end = SimpleNamespace(position=end)

    class _Plan:
        def is_patrol(self, _fp: object) -> bool:
            return True

        @property
        def layout(self) -> PatrollingLayout:
            return layout

    return SimpleNamespace(flight_plan=_Plan())


def test_hold_anchors_on_racetrack_center_for_patrolling_primary() -> None:
    primary = _patrolling_primary(Point(100000, 0, None), Point(100000, 60000, None))

    hold = Builder._racetrack_hold_point(primary)

    assert hold is not None
    assert hold.x == 100000
    assert hold.y == 30000


def test_no_racetrack_hold_for_non_patrolling_primary() -> None:
    class _Plan:
        def is_patrol(self, _fp: object) -> bool:
            return False

        @property
        def layout(self) -> object:
            raise AssertionError("layout must not be read for non-patrol primaries")

    primary = SimpleNamespace(flight_plan=_Plan())

    assert Builder._racetrack_hold_point(primary) is None


def test_no_racetrack_hold_without_primary_flight() -> None:
    assert Builder._racetrack_hold_point(None) is None


def _attack_builder(
    side: Player = Player.BLUE,
    is_helo: bool = False,
    escort_type: FlightType = FlightType.ESCORT,
) -> Any:
    home = Point(0, 0, None)
    waypoints = PackageWaypoints(
        join=Point(20000, 0, None),
        ingress=Point(100000, 0, None),
        initial=Point(180000, 0, None),
        split=Point(100000, 20000, None),
        refuel=home,
    )
    package = SimpleNamespace(
        primary_flight=SimpleNamespace(
            flight_type=FlightType.STRIKE,
            flight_plan=SimpleNamespace(is_patrol=lambda plan: False),
        ),
        waypoints=waypoints,
        waypoints_need_regeneration=lambda: False,
        target=SimpleNamespace(
            name="Target", position=Point(200000, 0, None), strike_targets=[]
        ),
    )
    coalition = SimpleNamespace(
        player=side,
        game=SimpleNamespace(settings=SimpleNamespace(heli_combat_alt_agl=500)),
        doctrine=SimpleNamespace(
            min_combat_altitude=feet(500), max_combat_altitude=feet(40000)
        ),
        opponent=SimpleNamespace(threat_zone=None),
        nav_mesh=SimpleNamespace(shortest_path=lambda start, end: [start, end]),
        bullseye=SimpleNamespace(position=home),
    )
    flight = SimpleNamespace(
        package=package,
        coalition=coalition,
        flight_type=escort_type,
        is_helo=is_helo,
        is_c130j=False,
        plane_altitude_offset=1000,
        unit_type=SimpleNamespace(
            preferred_cruise_altitude=feet(20000),
            preferred_combat_altitude=feet(20000),
        ),
        departure=SimpleNamespace(position=home),
        arrival=SimpleNamespace(position=home),
        divert=None,
    )
    builder: Any = Builder(flight)  # type: ignore[arg-type]
    builder._hold_point = lambda _: Point(10000, 0, None)
    builder._get_split = lambda: waypoints.split
    builder._build_refuel = lambda waypoint_builder: None
    return builder


@pytest.mark.parametrize("side", [Player.BLUE, Player.RED])
@pytest.mark.parametrize("is_helo", [False, True])
@pytest.mark.parametrize("escort_type", [FlightType.ESCORT, FlightType.SEAD_ESCORT])
def test_attack_escort_hold_is_at_ingress_not_near_target(
    side: Player, is_helo: bool, escort_type: FlightType
) -> None:
    builder = _attack_builder(side, is_helo, escort_type)

    layout = builder.layout()

    assert layout.initial.name == "ESCORT HOLD"
    assert layout.initial.position == layout.ingress.position
    assert layout.initial.position != builder.package.waypoints.initial
    assert layout.initial.position != layout.targets[0].position
    assert layout.initial.alt == (feet(500) if is_helo else feet(21000))
    assert layout.initial.alt_type == ("RADIO" if is_helo else "BARO")
    assert not layout.initial.only_for_player
    assert layout.ingress.only_for_player and layout.targets[0].only_for_player
    assert layout.initial.position.distance_to_point(layout.targets[0].position) >= (
        nautical_miles(5).meters - 1e-6
    )
    assert layout.join.position.distance_to_point(builder.package.target.position) > (
        layout.initial.position.distance_to_point(builder.package.target.position)
    )


@pytest.mark.parametrize("primary_type", [FlightType.AEWC, FlightType.REFUELING])
def test_built_patrol_escort_still_holds_at_protected_racetrack(
    primary_type: FlightType,
) -> None:
    builder = _attack_builder()
    start, end = Point(30000, 40000, None), Point(60000, 40000, None)
    primary = _patrolling_primary(start, end)
    primary.flight_type = primary_type
    builder.package.primary_flight = primary

    layout = builder.layout()

    assert layout.initial.position == start.midpoint(end)
    assert layout.initial.position != layout.ingress.position


def test_non_formation_escort_still_holds_at_ingress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _attack_builder()
    waypoints = builder.package.waypoints
    builder.package.waypoints_need_regeneration = lambda: True
    builder.package.primary_flight.flight_plan.layout = SimpleNamespace(
        departure=SimpleNamespace(position=builder.flight.departure.position)
    )
    monkeypatch.setattr(PackageWaypoints, "create", lambda *args, **kwargs: waypoints)

    layout = builder.layout()

    assert layout.hold is None
    assert layout.initial.position == layout.ingress.position
    assert layout.initial.position != layout.targets[0].position


@pytest.mark.parametrize("primary", [None, "self"])
def test_escort_without_a_protected_flight_uses_ingress(primary: str | None) -> None:
    builder = _attack_builder()
    builder.package.primary_flight = builder.flight if primary else None

    layout = builder.layout()

    assert layout.initial.position == layout.ingress.position


@pytest.mark.parametrize("primary_type", [FlightType.AIR_ASSAULT, FlightType.TRANSPORT])
def test_transport_escort_still_protects_the_dropoff(primary_type: FlightType) -> None:
    builder = _attack_builder(is_helo=True)
    dropoff = FlightWaypoint(
        "DROPOFF", FlightWaypointType.DROPOFF_ZONE, Point(195000, 0, None)
    )
    primary_layout: Any = object.__new__(
        AirAssaultLayout if primary_type is FlightType.AIR_ASSAULT else AirliftLayout
    )
    primary_layout.drop_off = dropoff
    primary_layout.arrival = FlightWaypoint(
        "ARRIVAL", FlightWaypointType.LANDING_POINT, Point(10000, 0, None)
    )
    primary_layout.pickup = None
    primary_layout.pickup_ascent = None
    primary_layout.drop_off_ascent = dropoff
    builder.package.primary_flight = SimpleNamespace(
        flight_type=primary_type,
        flight_plan=SimpleNamespace(
            is_patrol=lambda plan: False, layout=primary_layout
        ),
    )

    layout = builder.layout()

    assert layout.initial.position == dropoff.position
    assert layout.split.position == primary_layout.arrival.position
