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


def test_secondary_edits_share_coordinates_not_altitudes_procedures_or_timing() -> None:
    package = _package()
    first, second = package.flights
    original_departure = first.flight_plan.layout.departure.position
    original_alignment = first.flight_plan.layout.nav_from[-1]
    first.flight_plan.tot_offset = -10
    for point in second.flight_plan.waypoints:
        point.alt = feet(25000)
    second.flight_plan.layout.patrol_start.position = Point(42, 50, _TERRAIN)
    second.flight_plan.layout.patrol_start.alt = feet(25000)
    second.flight_plan.layout.nav_to[0].position = Point(43, 51, _TERRAIN)
    assert sharedroute.synchronize(package, second) == [first]
    assert first.flight_plan.layout.patrol_start.position.x == 42
    assert first.flight_plan.layout.patrol_start.alt == feet(20000)
    assert first.flight_plan.layout.nav_to[0].position.x == 43
    assert first.flight_plan.layout.nav_to[0].alt == feet(20000)
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
    result = planner.edit_waypoint(game, side, str(second.id), index, alt_m=8000)
    assert result.ok, result.error
    assert second.flight_plan.layout.patrol_start.alt.meters == 8000
    assert first.flight_plan.layout.patrol_start.alt == feet(20000)
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
    sharedroute.synchronize(package)
    point = second.flight_plan.layout.patrol_start
    index = second.flight_plan.waypoints.index(point) + 1
    game: Any = NS(db=NS(flights=NS(get=lambda uid: second)))
    sent: list[Any] = []
    monkeypatch.setattr(
        routes, "_package_model_of", lambda flight: NS(update_tot=lambda: None)
    )
    monkeypatch.setattr(EventStream, "put_nowait", sent.append)
    routes.edit_waypoint(second.id, index, routes.WaypointEdit(altitude_ft=26000), game)
    assert second.flight_plan.layout.patrol_start.alt == feet(26000)
    assert first.flight_plan.layout.patrol_start.alt == feet(20000)
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


def _route(flight: Any) -> list[FlightWaypoint]:
    return [w for w in flight.flight_plan.waypoints if sharedroute._flying(w)]


@pytest.mark.parametrize("is_helo, spacing", [(False, 1000), (True, 200)])
def test_equal_profiles_are_separated_without_drifting(
    is_helo: bool, spacing: int
) -> None:
    package = _package()
    package.flights.extend(deepcopy(package.flights[:2]))
    for flight in package.flights:
        flight.is_helo = is_helo
        for point in _route(flight):
            point.alt = feet(200 if is_helo else 20000)
            point.alt_type = "RADIO" if is_helo else "BARO"
    sharedroute.synchronize(package)
    heights = [[w.alt.feet for w in _route(f)] for f in package.flights]
    for index, profile in enumerate(heights):
        assert profile == pytest.approx(
            [(200 if is_helo else 20000) + index * spacing] * len(profile)
        )
    for source in package.flights:
        sharedroute.synchronize(package, source)
        assert [[w.alt.feet for w in _route(f)] for f in package.flights] == heights


@pytest.mark.parametrize("second_alt", [16000, 24000])
def test_already_separated_profiles_keep_all_their_heights(second_alt: int) -> None:
    package = _package()
    first, second = package.flights
    for point in _route(second):
        point.alt = feet(second_alt)
    sharedroute.synchronize(package)
    assert all(w.alt == feet(20000) for w in _route(first))
    assert all(w.alt == feet(second_alt) for w in _route(second))


def test_crossing_profiles_get_a_uniform_offset() -> None:
    package = _package()
    first, second = package.flights
    second.flight_plan.layout.patrol_start.alt = feet(19000)
    second.flight_plan.layout.patrol_end.alt = feet(21000)
    original = [w.alt.feet for w in _route(second)]
    sharedroute.synchronize(package)
    assert [w.alt.feet for w in _route(second)] == pytest.approx(
        [h + 2000 for h in original]
    )
    assert all(
        b.alt.feet - a.alt.feet >= 999.999
        for a, b in zip(_route(first), _route(second))
    )


def test_separation_uses_a_lower_level_at_the_doctrine_ceiling() -> None:
    package = _package()
    second = package.flights[1]
    second.coalition = NS(
        doctrine=NS(min_combat_altitude=feet(10000), max_combat_altitude=feet(20000))
    )
    sharedroute.synchronize(package)
    assert all(w.alt.feet == pytest.approx(19000) for w in _route(second))


def test_separation_keeps_heights_when_no_level_fits_the_doctrine(
    caplog: pytest.LogCaptureFixture,
) -> None:
    package = _package()
    second = package.flights[1]
    second.coalition = NS(
        doctrine=NS(min_combat_altitude=feet(20000), max_combat_altitude=feet(20000))
    )
    sharedroute.synchronize(package)
    assert all(w.alt == feet(20000) for w in _route(second))
    assert "Cannot vertically separate" in caplog.text


def test_separation_never_lowers_an_agl_leg_to_fit_below_the_ceiling() -> None:
    package = _package()
    second = package.flights[1]
    second.coalition = NS(
        doctrine=NS(min_combat_altitude=feet(10000), max_combat_altitude=feet(20000))
    )
    second.flight_plan.layout.nav_to[0].alt_type = "RADIO"
    second.flight_plan.layout.nav_to[0].alt = feet(200)
    sharedroute.synchronize(package)
    assert second.flight_plan.layout.patrol_start.alt == feet(20000)
    assert second.flight_plan.layout.nav_to[0].alt == feet(200)


def test_mixed_aircraft_and_helicopter_flights_use_the_larger_gap() -> None:
    package = _package()
    first, second = package.flights
    first.is_helo = True
    second.is_helo = False
    sharedroute.synchronize(package)
    assert all(
        b.alt.feet - a.alt.feet == pytest.approx(1000)
        for a, b in zip(_route(first), _route(second))
    )


def test_nav_insertions_use_the_receiving_flights_own_profile() -> None:
    package = _package()
    first, second = package.flights
    for point in _route(second):
        point.alt = feet(25000)
    first.flight_plan.layout.nav_to.append(_wpt(Wpt.NAV, 99))
    second.flight_plan.layout.nav_from.clear()
    sharedroute.synchronize(package)
    assert [w.position.x for w in second.flight_plan.layout.nav_to] == [0, 99]
    assert all(w.alt == feet(25000) for w in _route(second))


def test_separation_does_not_change_procedures_or_ground_elevations() -> None:
    package = _package()
    first, second = package.flights
    protected = []
    for flight in package.flights:
        layout = flight.flight_plan.layout
        point = _wpt(Wpt.TARGET_POINT)
        point.alt = feet(69)
        point.only_for_player = True
        layout.custom_waypoints.append(point)
        for point in (
            layout.departure,
            layout.arrival,
            layout.divert,
            layout.bullseye,
            layout.nav_from[-1],
            point,
        ):
            protected.append((point, point.alt, point.alt_type))
    sharedroute.synchronize(package)
    for point, altitude, reference in protected:
        assert (point.alt, point.alt_type) == (altitude, reference)
    assert second.flight_plan.layout.custom_waypoints[0].alt == feet(69)
    assert second.flight_plan.layout.patrol_start.alt.feet == pytest.approx(21000)


def test_height_references_are_preserved_and_not_compared_as_equal() -> None:
    package = _package()
    first, second = package.flights
    for point in _route(second):
        point.alt_type = "RADIO"
    sharedroute.synchronize(package)
    assert all(w.alt_type == "BARO" and w.alt == feet(20000) for w in _route(first))
    assert all(w.alt_type == "RADIO" and w.alt == feet(20000) for w in _route(second))


@pytest.mark.parametrize("share", [False, True])
def test_saved_profiles_are_separated_before_simulation_and_retiming(
    share: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime
    from game.sim import missionsimulation

    package = _package()
    package.single_route_for_all_flights = share
    game: Any = NS(
        coalitions=[NS(ato=NS(packages=[package]))],
        conditions=NS(start_time=datetime(2026, 11, 3)),
    )
    seen = []

    def record(*args: Any) -> None:
        seen.append(package.flights[1].flight_plan.layout.patrol_start.alt.feet)

    monkeypatch.setattr(missionsimulation, "retime_coordinated_packages", record)
    simulation: Any = object.__new__(missionsimulation.MissionSimulation)
    simulation.game = game
    simulation.aircraft_simulation = NS(begin_simulation=record)
    simulation.begin_simulation()
    assert seen == pytest.approx([21000 if share else 20000] * 2)


@pytest.mark.parametrize("manual", [False, True])
def test_exported_dcs_waypoints_keep_manual_or_separated_altitudes(
    manual: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime
    from dcs.point import MovingPoint
    from game.ato.traveltime import GroundSpeed
    from game.missiongenerator.aircraft.waypoints.pydcswaypointbuilder import (
        PydcsWaypointBuilder,
    )
    from game.utils import knots

    package = _package()
    if manual:
        for flight, height in zip(package.flights, (18000, 18500)):
            for waypoint in _route(flight):
                waypoint.apply_altitude_edit(feet(height))
        package = pickle.loads(pickle.dumps(package))
    sharedroute.synchronize(package)
    monkeypatch.setattr(GroundSpeed, "for_flight", lambda *args: knots(300))
    monkeypatch.setattr(PydcsWaypointBuilder, "add_tasks", lambda *args: None)
    exported = []
    for flight in package.flights:
        flight.is_helo = False
        flight.flight_plan.tot_for_waypoint = lambda w: None

        def add_waypoint(
            position: Point, altitude: float, **kwargs: Any
        ) -> MovingPoint:
            point = MovingPoint(position)
            point.alt = altitude  # type: ignore[assignment]  # pydcs infers int from its default.
            return point

        group: Any = NS(add_waypoint=add_waypoint)
        builder = PydcsWaypointBuilder(
            flight.flight_plan.layout.nav_to[0], group, flight, None, datetime(2026, 11, 3), None  # type: ignore[arg-type]
        )
        exported.append(builder.build())
    assert exported[0].position == exported[1].position
    assert exported[1].alt - exported[0].alt == pytest.approx(
        feet(500 if manual else 1000).meters
    )
    assert exported[0].alt_type == exported[1].alt_type == "BARO"


@pytest.mark.parametrize("side", ["blue", "red"])
def test_manual_profiles_survive_secondary_api_edits_and_saved_synchronization(
    side: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _package(FlightType.DEAD)
    sharedroute.set_enabled(package, True)
    monkeypatch.setattr(planner, "_push_map_events", lambda events: None)
    game: Any = NS()
    for flight, altitude in zip(package.flights, (18000, 18500)):
        monkeypatch.setattr(planner, "flight_for_side", lambda *args: flight)
        for point in _route(flight):
            index = flight.flight_plan.waypoints.index(point) + 1
            result = planner.edit_waypoint(
                game, side, str(flight.id), index, alt_m=feet(altitude).meters
            )
            assert result.ok, result.error
    expected = [
        [feet(18000).meters] * len(_route(package.flights[0])),
        [feet(18500).meters] * len(_route(package.flights[1])),
    ]
    assert [[w.alt.meters for w in _route(f)] for f in package.flights] == expected
    restored = pickle.loads(pickle.dumps(package))
    for source in [None, *restored.flights]:
        sharedroute.synchronize(restored, source)
        assert [[w.alt.meters for w in _route(f)] for f in restored.flights] == expected


def _edit_table(flight: Any, heights: list[float]) -> None:
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointList import (
        QFlightWaypointList,
    )

    points = flight.flight_plan.waypoints
    rows = [
        (
            NS(text=lambda w=w: w.display_name),
            NS(text=lambda height=height: str(height)),
        )
        for w, height in zip(points, heights)
    ]
    view: Any = NS(
        model=NS(
            rowCount=lambda: len(rows), item=lambda row, column: rows[row][column]
        ),
        waypoint_at_row=lambda row: points[row],
    )
    QFlightWaypointList.on_changed(view)


@pytest.mark.parametrize("bulk", [False, True])
def test_flight_editor_manual_profiles_override_automatic_separation(
    bulk: bool,
) -> None:
    from qt_ui.windows.mission.flight.waypoints.QFlightWaypointTab import (
        QFlightWaypointTab,
    )

    package = _package(FlightType.DEAD)
    sharedroute.set_enabled(package, True)
    for flight, height in zip(package.flights, (18000, 18500)):
        if bulk:
            view: Any = NS(
                flight=flight,
                bulk_altitude=NS(value=lambda: height),
                _is_bulk_editable=lambda w: w.waypoint_type
                not in QFlightWaypointTab.BULK_ALTITUDE_SKIP_TYPES,
                on_change=lambda: sharedroute.synchronize(package, flight),
            )
            QFlightWaypointTab.on_apply_bulk_altitude(view)
        else:
            _edit_table(
                flight,
                [
                    height if sharedroute._flying(w) else round(w.alt.feet)
                    for w in flight.flight_plan.waypoints
                ],
            )
            sharedroute.synchronize(package, flight)
    for flight, height in zip(package.flights, (18000, 18500)):
        assert all(
            w.alt == feet(height) and w.altitude_is_manual for w in _route(flight)
        )


def test_table_redraw_does_not_pin_or_round_automatic_altitudes() -> None:
    flight = _package().flights[0]
    flight.flight_plan.layout.nav_to[0].alt = feet(20000.4)
    before = [w.alt for w in flight.flight_plan.waypoints]
    _edit_table(flight, [round(w.alt.feet) for w in flight.flight_plan.waypoints])
    assert [w.alt for w in flight.flight_plan.waypoints] == before
    assert not any(w.altitude_is_manual for w in flight.flight_plan.waypoints)


def test_map_manual_altitude_and_reference_survive_secondary_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.server import EventStream

    package = _package()
    sharedroute.synchronize(package)
    monkeypatch.setattr(
        routes, "_package_model_of", lambda flight: NS(update_tot=lambda: None)
    )
    monkeypatch.setattr(EventStream, "put_nowait", lambda events: None)
    for flight, height in zip(package.flights, (18000, 18500)):
        point = flight.flight_plan.layout.patrol_start
        index = flight.flight_plan.waypoints.index(point) + 1
        game: Any = NS(db=NS(flights=NS(get=lambda uid: flight)))
        routes.edit_waypoint(
            flight.id,
            index,
            routes.WaypointEdit(altitude_ft=height, altitude_reference="RADIO"),
            game,
        )
    sharedroute.synchronize(package)
    for flight, height in zip(package.flights, (18000, 18500)):
        point = flight.flight_plan.layout.patrol_start
        assert point.alt == feet(height)
        assert point.alt_type == "RADIO"
        assert point.altitude_is_manual


def test_drag_preserves_each_receivers_manual_nav_heights_and_references() -> None:
    package = _package()
    first, second = package.flights
    first.flight_plan.layout.nav_to.append(_wpt(Wpt.NAV, 100))
    sharedroute.synchronize(package)
    first.flight_plan.layout.nav_to[0].apply_altitude_edit(feet(18000))
    first.flight_plan.layout.nav_to[1].apply_altitude_edit(feet(22000), "RADIO")
    # Move the first shared point closer to the receiving flight's second point.
    second.flight_plan.layout.nav_to[0].position = Point(99, 99, _TERRAIN)
    sharedroute.synchronize(package, second)
    one, two = first.flight_plan.layout.nav_to
    assert (one.alt, one.alt_type) == (feet(18000), "BARO")
    assert (two.alt, two.alt_type) == (feet(22000), "RADIO")
    assert one.position.x == 99
    assert all(w.altitude_is_manual for w in (one, two))
    assert not any(w.altitude_is_manual for w in _route(second))


def test_automatic_profiles_separate_around_a_manual_profile() -> None:
    package = _package()
    first, second = package.flights
    second.flight_plan.layout.patrol_start.apply_altitude_edit(feet(20000))
    sharedroute.synchronize(package, first)
    assert all(w.alt == feet(20000) for w in _route(second))
    assert [w.alt.feet for w in _route(first)] == pytest.approx(
        [21000] * len(_route(first))
    )


def test_manual_altitude_metadata_survives_copy_and_old_save_loading() -> None:
    waypoint = _wpt(Wpt.NAV)
    waypoint.apply_altitude_edit(feet(18000), "RADIO")
    cloned = deepcopy(waypoint)
    assert (cloned.alt, cloned.alt_type, cloned.altitude_is_manual) == (
        feet(18000),
        "RADIO",
        True,
    )
    state = waypoint.__dict__.copy()
    state.pop("altitude_is_manual")
    legacy = FlightWaypoint.__new__(FlightWaypoint)
    legacy.__setstate__(state)
    assert legacy.alt == feet(18000)
    assert not legacy.altitude_is_manual
