"""Tests for FormationAttackBuilder.strike_targets_for.

This helper turns a ground objective's individual units into the per-target
list used both by the kneeboard target page (with coordinates) and by the
per-target TARGET_POINT waypoints, keeping the two in lockstep for Strike,
DEAD and SEAD.
"""

from types import SimpleNamespace

from game.ato.flighttype import FlightType
from game.ato.flightplans.formationattack import FormationAttackBuilder
from game.ato.flightplans.strike import Builder as StrikeBuilder
from game.ato.flightplans.waypointbuilder import StrikeTarget


class _FakeType:
    def __init__(self, id_: str) -> None:
        self.id = id_


class _FakeUnit:
    """Stands in for a vehicle TheaterUnit, which has a unit_type, so .type.id is used.

    Statics have unit_type None and carry the objective in their name instead.
    """

    def __init__(
        self,
        id_: str,
        unit_type: object | None = object(),
        name: str | None = None,
    ) -> None:
        self.type = _FakeType(id_)
        self.unit_type = unit_type
        self.name = id_ if name is None else name


class _FakeLocation:
    def __init__(self, units: list[_FakeUnit]) -> None:
        self.strike_targets = units


def test_one_target_per_alive_unit_with_indexed_names() -> None:
    location = _FakeLocation(
        [_FakeUnit("SA-10 ln"), _FakeUnit("SA-10 tr"), _FakeUnit("SA-10 cp")]
    )

    targets = FormationAttackBuilder.strike_targets_for(location)  # type: ignore[arg-type]

    assert [t.name for t in targets] == [
        "SA-10 ln #0",
        "SA-10 tr #1",
        "SA-10 cp #2",
    ]
    # Each StrikeTarget references the originating unit, so the waypoint and the
    # kneeboard row describe the same target.
    assert [t.target for t in targets] == location.strike_targets


def test_no_targets_when_objective_has_no_units() -> None:
    assert FormationAttackBuilder.strike_targets_for(_FakeLocation([])) == []  # type: ignore[arg-type]


def test_target_waypoints_fall_back_to_area_when_no_live_targets() -> None:
    """An objective with all units destroyed yields an empty target list.

    The layout must still get one (area) target waypoint, otherwise
    ``tot_waypoint`` -- which indexes ``targets[0]`` -- raises IndexError while
    planning a Strike/DEAD/SEAD against a fully destroyed objective (regression).
    """
    builder = StrikeBuilder.__new__(StrikeBuilder)  # skip IBuilder.__init__
    builder.flight = SimpleNamespace(  # type: ignore[assignment]
        flight_type=FlightType.STRIKE,
        package=SimpleNamespace(target=object()),
    )
    wp_builder = SimpleNamespace(
        strike_point=lambda target: ("point", target),
        strike_area=lambda location: "area",
    )

    # Empty list (all targets dead) and None both fall back to one area waypoint.
    assert builder._target_waypoints(wp_builder, []) == ["area"]  # type: ignore[arg-type]
    assert builder._target_waypoints(wp_builder, None) == ["area"]  # type: ignore[arg-type]

    # With live targets, one waypoint per target is produced.
    targets = [StrikeTarget("a #0", object()), StrikeTarget("b #1", object())]  # type: ignore[arg-type]
    result = builder._target_waypoints(wp_builder, targets)  # type: ignore[arg-type]
    assert result == [("point", targets[0]), ("point", targets[1])]


def test_a_static_is_named_after_its_objective_not_its_type() -> None:
    # A static has no unit_type and carries the campaign designer's name, which beats
    # repeating the DCS type in a target list. A vehicle alongside it keeps its type.
    location = _FakeLocation(
        [
            _FakeUnit("Workshop A", unit_type=None, name="Factory Zaragoza-2"),
            _FakeUnit("SA-10 ln"),
        ]
    )

    targets = FormationAttackBuilder.strike_targets_for(location)  # type: ignore[arg-type]

    assert [t.name for t in targets] == ["Factory Zaragoza-2 #0", "SA-10 ln #1"]


def test_one_of_several_target_points_can_be_dropped() -> None:
    """A strike spreads itself over one waypoint per target, and dropping one is the
    player saying he does not want that building. The rule existed in the flight
    editor but asked a freshly built TARGET AREA waypoint whose own `targets` are
    units, so it never once fired."""
    from types import SimpleNamespace

    from game.ato.flightplans.formationattack import FormationAttackFlightPlan
    from game.ato.flightwaypoint import FlightWaypoint
    from game.ato.flightwaypointtype import FlightWaypointType
    from game.utils import meters

    def _target(name: str) -> FlightWaypoint:
        return FlightWaypoint(
            name,
            FlightWaypointType.TARGET_POINT,
            SimpleNamespace(x=0.0, y=0.0),  # type: ignore[arg-type]
            meters(0),
        )

    # Two target points on identical buildings: equal by value, not the same
    # waypoint, which is why the rule has to use identity.
    first, second = _target("Warehouse"), _target("Warehouse")
    assert first == second

    plan = FormationAttackFlightPlan.__new__(FormationAttackFlightPlan)
    plan.layout = SimpleNamespace(targets=[first, second])

    assert plan.can_delete_waypoint(first)
    assert plan.delete_waypoint(first)
    assert [id(t) for t in plan.layout.targets] == [id(second)]


def test_the_last_target_point_cannot_be_dropped() -> None:
    """An attack with nothing to attack is the degrade-to-custom path, not this."""
    from types import SimpleNamespace

    from game.ato.flightplans.formationattack import FormationAttackFlightPlan
    from game.ato.flightwaypoint import FlightWaypoint
    from game.ato.flightwaypointtype import FlightWaypointType
    from game.utils import meters

    only = FlightWaypoint(
        "T1",
        FlightWaypointType.TARGET_POINT,
        SimpleNamespace(x=0.0, y=0.0),  # type: ignore[arg-type]
        meters(0),
    )
    plan = FormationAttackFlightPlan.__new__(FormationAttackFlightPlan)
    plan.layout = SimpleNamespace(targets=[only], can_delete_waypoint=lambda _w: False)

    assert not plan.can_delete_waypoint(only)
