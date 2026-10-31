"""Shared package routes preserve individual procedures, timing and mission roles."""

from copy import deepcopy
import pickle
from types import SimpleNamespace as NS
from typing import Any
from uuid import uuid4

from dcs import Point
import pytest

from game.agent import planner, schemas
from game.ato.flightplans.patrolling import PatrollingLayout
from game.ato.flighttype import FlightType
from game.ato.flightwaypoint import FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType as Wpt
from game.ato.package import Package
from game.ato import sharedroute
from game.db import Database
from game.server.waypoints import routes
from game.sim import GameUpdateEvents
from game.utils import feet


class FlightStub:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


_TERRAIN: Any = None


class Plan:
    def __init__(self, layout: PatrollingLayout) -> None:
        self.layout = layout
        self.tot_offset = 0

    @property
    def waypoints(self) -> list[FlightWaypoint]:
        return list(self.layout.iter_waypoints())


def _wpt(kind: Wpt, x: float = 0, name: str = "") -> FlightWaypoint:
    return FlightWaypoint(name or kind.name, kind, Point(x, x, _TERRAIN), feet(20000))


def _package(task: FlightType = FlightType.BARCAP) -> Any:
    package: Any = Package(NS(name="Test target"), Database())  # type: ignore[arg-type]
    for index in range(2):
        layout = PatrollingLayout(
            departure=_wpt(Wpt.TAKEOFF, index * 100),
            arrival=_wpt(Wpt.LANDING_POINT, index * 100),
            divert=_wpt(Wpt.DIVERT, index * 200),
            bullseye=_wpt(Wpt.BULLSEYE),
            custom_waypoints=[],
            nav_to=[_wpt(Wpt.NAV, index * 10)],
            nav_from=[_wpt(Wpt.NAV, index * 20), _wpt(Wpt.NAV, index * 30, "ALIGN")],
            patrol_start=_wpt(Wpt.PATROL_TRACK, index * 1000),
            patrol_end=_wpt(Wpt.PATROL, index * 2000),
        )
        package.flights.append(
            FlightStub(
                id=uuid4(),
                flight_type=task,
                flight_plan=Plan(layout),
                package=package,
                state=NS(is_waiting_for_start=True),
                blue=False,
            )
        )
    return package


@pytest.mark.parametrize("task", list(FlightType))
def test_task_defaults(task: FlightType) -> None:
    package = _package(task)
    assert sharedroute.enabled(package) is (task in sharedroute.DEFAULT_TASKS)


def test_secondary_edits_share_coordinates_and_altitudes_not_procedures_or_timing() -> (
    None
):
    package = _package()
    first, second = package.flights
    original_departure = first.flight_plan.layout.departure.position
    original_alignment = first.flight_plan.layout.nav_from[-1]
    first.flight_plan.tot_offset = -10
    second.flight_plan.layout.patrol_start.position = Point(42, 50, _TERRAIN)
    second.flight_plan.layout.patrol_start.alt = feet(25000)
    second.flight_plan.layout.nav_to[0].position = Point(43, 51, _TERRAIN)
    assert sharedroute.synchronize(package, second) == [first]
    assert first.flight_plan.layout.patrol_start.position.x == 42
    assert first.flight_plan.layout.patrol_start.alt == feet(25000)
    assert first.flight_plan.layout.nav_to[0].position.x == 43
    assert first.flight_plan.layout.departure.position is original_departure
    assert first.flight_plan.layout.nav_from[-1] is original_alignment
    assert first.flight_plan.tot_offset == -10
    assert (
        first.flight_plan.layout.patrol_start
        is not second.flight_plan.layout.patrol_start
    )


def test_navigation_lists_are_shared_even_when_generated_lengths_differ() -> None:
    package = _package()
    first, second = package.flights
    first.flight_plan.layout.nav_to.append(_wpt(Wpt.NAV, 99))
    sharedroute.synchronize(package)
    assert [w.position.x for w in second.flight_plan.layout.nav_to] == [0, 99]
    sharedroute.set_enabled(package, False)
    second.flight_plan.layout.nav_to[0].position = Point(75, 0, _TERRAIN)
    assert sharedroute.synchronize(package, second) == []
    assert first.flight_plan.layout.nav_to[0].position.x == 0


@pytest.mark.parametrize("task", [FlightType.ESCORT, FlightType.SEAD_ESCORT])
def test_escort_types_disable_route_and_explain_why(task: FlightType) -> None:
    package = _package()
    package.flights[1].flight_type = task
    assert not sharedroute.enabled(package)
    assert "dedicated" in (sharedroute.unavailable_reason(package) or "")
    with pytest.raises(ValueError, match="dedicated"):
        sharedroute.set_enabled(package, True)


def test_extra_mission_waypoints_disable_sharing_without_changing_the_route() -> None:
    package = _package()
    package.flights[1].flight_plan.layout.refuel = _wpt(Wpt.REFUEL)
    assert "different mission waypoints" in (
        sharedroute.unavailable_reason(package) or ""
    )
    assert sharedroute.synchronize(package) == []


def test_flag_persists_and_legacy_routes_are_not_silently_replaced() -> None:
    package = _package(FlightType.STRIKE)
    sharedroute.set_enabled(package, True)
    restored = pickle.loads(pickle.dumps(package))
    assert sharedroute.enabled(restored)
    state = package.__dict__.copy()
    state.pop("single_route_for_all_flights")
    legacy = Package.__new__(Package)
    legacy.__setstate__(state)
    assert not sharedroute.enabled(legacy)


def test_map_drag_from_secondary_publishes_other_flights() -> None:
    package = _package()
    first, second = package.flights
    waypoint = second.flight_plan.layout.patrol_end
    waypoint.position = Point(120, 230, _TERRAIN)
    events = GameUpdateEvents()
    routes.update_package_waypoints_if_primary_flight(waypoint, second, events)
    assert first.flight_plan.layout.patrol_end.position.x == 120
    assert first in events.updated_flights


@pytest.mark.parametrize("side", ["blue", "red"])
def test_api_toggle_and_waypoint_edits_share_routes(
    side: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _package(FlightType.STRIKE)
    first, second = package.flights
    game: Any = NS(coalition_for=lambda player: NS(ato=NS(packages=[package])))
    sent: list[Any] = []
    monkeypatch.setattr(planner, "_push_map_events", sent.append)
    monkeypatch.setattr(planner, "flight_for_side", lambda *args: second)
    result = planner.set_package_shared_route(game, side, 0, True)
    assert result.ok, result.error
    assert sent[-1].updated_flights == {first, second}
    index = (
        second.flight_plan.waypoints.index(second.flight_plan.layout.patrol_start) + 1
    )
    result = planner.edit_waypoint(game, side, str(second.id), index, alt_m=6000)
    assert result.ok, result.error
    assert first.flight_plan.layout.patrol_start.alt.meters == 6000
    assert first in sent[-1].updated_flights
    assert planner.set_package_shared_route(game, side, -1, True).ok is False


def test_api_schema_accepts_override_and_keeps_automatic_default() -> None:
    spec = schemas.PackageSpec(target_id="x", flights=[])
    assert spec.single_route_for_all_flights is None
    assert (
        spec.model_copy(
            update={"single_route_for_all_flights": False}
        ).single_route_for_all_flights
        is False
    )


def test_map_altitude_edits_publish_every_affected_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.server import EventStream

    package = _package()
    first, second = package.flights
    point = second.flight_plan.layout.patrol_start
    index = second.flight_plan.waypoints.index(point) + 1
    game: Any = NS(db=NS(flights=NS(get=lambda uid: second)))
    sent: list[Any] = []
    monkeypatch.setattr(
        routes, "_package_model_of", lambda flight: NS(update_tot=lambda: None)
    )
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    routes.edit_waypoint(second.id, index, routes.WaypointEdit(altitude_ft=26000), game)
    assert first.flight_plan.layout.patrol_start.alt == feet(26000)
    assert sent[-1].updated_flights == {first, second}


def test_package_spec_can_disable_default_sharing_before_timing() -> None:
    from datetime import datetime

    package = _package()
    package.set_tot_asap = lambda now: None
    planner._apply_tot(
        package,
        schemas.PackageSpec(
            target_id="x", flights=[], single_route_for_all_flights=False
        ),
        datetime(2026, 10, 30),
    )
    assert not sharedroute.enabled(package)
    assert package.single_route_for_all_flights is False


def test_incompatible_explicit_package_spec_is_refused() -> None:
    from datetime import datetime

    package = _package(FlightType.SEAD_ESCORT)
    with pytest.raises(ValueError, match="dedicated waypoints"):
        planner._apply_tot(
            package,
            schemas.PackageSpec(
                target_id="x", flights=[], single_route_for_all_flights=True
            ),
            datetime(2026, 10, 30),
        )


def test_regeneration_uses_built_primary_route_without_recursively_building() -> None:
    from game.ato.flightplans.ibuilder import IBuilder

    class Builder(IBuilder[Any, Any]):
        def build(self, dump_debug_info: bool = False) -> Any:
            return Plan(deepcopy(second.flight_plan.layout))

        def _generate_package_waypoints_if_needed(self, dump_debug_info: bool) -> None:
            pass

    package = _package()
    first, second = package.flights
    original = first.flight_plan.layout.patrol_start.position.x
    # A regenerated secondary plan has fresh route coordinates.
    second.flight_plan = Plan(deepcopy(second.flight_plan.layout))
    second.flight_plan.layout.patrol_start.position = Point(999, 999, _TERRAIN)
    second.coalition = NS(game=NS(settings=NS(align_before_landing=False)))
    builder = Builder(second)
    second._flight_plan_builder = builder
    builder.regenerate()
    assert builder.get_or_build().layout.patrol_start.position.x == original
