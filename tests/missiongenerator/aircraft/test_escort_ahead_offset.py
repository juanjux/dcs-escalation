"""An escort asked to arrive AHEAD of its package now actually gets there first.

The DCS Escort task ties a flight to the one it protects from the join point on, so
an "ahead" offset used to be spent orbiting the join: the escort crossed the target
with its package however early it set off. Pushing the formation station forward does
not help either -- DCS clamps the offset, flown 12-09-2026 and less than a minute of
lead to show for it.

What works, and what these tests pin, is holding the task back: the escort keeps its
head start and the task takes over when the flight it protects reaches its ingress.
Delete the ``start_after_time`` call in ``configure_escort_tasks`` and the first two
tests fail.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from dcs.task import ControlledTask

from game.ato import FlightType
from game.missiongenerator.aircraft.waypoints.joinpoint import JoinPointBuilder
from game.utils import feet, nautical_miles

NOW = datetime(2020, 1, 1, 11, 0)
PACKAGE_INGRESS = datetime(2020, 1, 1, 11, 20)


def _doctrine() -> Any:
    return SimpleNamespace(
        escort_engagement_range=nautical_miles(30),
        escort_spacing=feet(2000),
        sead_escort_engagement_range=nautical_miles(30),
        sead_escort_spacing=feet(2000),
    )


def _builder(
    flight_type: FlightType,
    offset: timedelta,
    package_ingress: datetime | None = PACKAGE_INGRESS,
    own_ingress: datetime | None = None,
) -> JoinPointBuilder:
    primary = SimpleNamespace(
        group_id=7,
        flight_plan=SimpleNamespace(ingress_time=package_ingress),
    )
    if package_ingress is None:
        del primary.flight_plan.ingress_time
    own_plan = SimpleNamespace(tot_offset=offset)
    if own_ingress is not None:
        own_plan.ingress_time = own_ingress

    settings = SimpleNamespace(ai_unlimited_fuel=False, plugins={})
    game = SimpleNamespace(settings=settings)
    coalition = SimpleNamespace(game=game, doctrine=_doctrine())

    package = SimpleNamespace(primary_flight=primary, target=SimpleNamespace())
    builder = JoinPointBuilder.__new__(JoinPointBuilder)
    builder.now = NOW
    builder.package = package  # type: ignore[assignment]
    builder.flight = SimpleNamespace(  # type: ignore[assignment]
        is_helo=False,
        flight_type=flight_type,
        flight_plan=own_plan,
        package=package,
        coalition=coalition,
        squadron=SimpleNamespace(coalition=coalition),
    )
    return builder


def _waypoint() -> Any:
    return SimpleNamespace(tasks=[])


def _escort_task(waypoint: Any) -> ControlledTask:
    tasks = [t for t in waypoint.tasks if isinstance(t, ControlledTask)]
    assert len(tasks) == 1
    return tasks[0]


def _start_time(waypoint: Any) -> int | None:
    condition = _escort_task(waypoint).params.get("condition")
    return None if condition is None else condition.get("time")


def test_escort_ahead_waits_for_the_package_ingress() -> None:
    waypoint = _waypoint()
    _builder(FlightType.ESCORT, timedelta(minutes=-3)).add_tasks(waypoint)

    # 11:00 to 11:20: the escort flies its own route for twenty minutes, keeping the
    # three-minute head start, and only then takes up station.
    assert _start_time(waypoint) == 20 * 60


def test_sead_escort_ahead_waits_too() -> None:
    # Both escort roles funnel through configure_escort_tasks, and the player can set
    # an ahead offset on either, so both have to honour it.
    waypoint = _waypoint()
    _builder(FlightType.SEAD_ESCORT, timedelta(minutes=-3)).add_tasks(waypoint)

    assert _start_time(waypoint) == 20 * 60


def test_escort_on_time_starts_at_the_join() -> None:
    waypoint = _waypoint()
    _builder(FlightType.ESCORT, timedelta()).add_tasks(waypoint)

    assert _start_time(waypoint) is None


def test_escort_behind_starts_at_the_join() -> None:
    # "Behind" always worked -- the escort task cannot pull a flight forward, only
    # hold it back -- so nothing about it changes.
    waypoint = _waypoint()
    _builder(FlightType.ESCORT, timedelta(minutes=4)).add_tasks(waypoint)

    assert _start_time(waypoint) is None


def test_escort_of_a_flight_with_no_ingress_gives_back_the_head_start() -> None:
    """A tanker or an AWACS orbits a racetrack and flies no ingress at all.

    There is no moment to hand over on, so use the escort's own: its ingress is the
    package's less the head start, so adding the head start back lands on the same
    place in the package's timeline.
    """
    waypoint = _waypoint()
    _builder(
        FlightType.ESCORT,
        timedelta(minutes=-3),
        package_ingress=None,
        own_ingress=datetime(2020, 1, 1, 11, 17),
    ).add_tasks(waypoint)

    assert _start_time(waypoint) == 20 * 60


def test_a_handover_before_the_mission_starts_is_dropped() -> None:
    # A negative mission time is a trigger DCS never fires, which would leave the
    # escort unglued for the whole mission. Escort from the join instead.
    waypoint = _waypoint()
    _builder(
        FlightType.ESCORT,
        timedelta(minutes=-3),
        package_ingress=datetime(2020, 1, 1, 10, 50),
    ).add_tasks(waypoint)

    assert _start_time(waypoint) is None


def test_the_split_flag_still_ends_the_escort() -> None:
    # The head start is the only thing that changes; the escort still breaks off with
    # the package at the split.
    waypoint = _waypoint()
    builder = _builder(FlightType.ESCORT, timedelta(minutes=-3))
    builder.add_tasks(waypoint)

    stop = _escort_task(waypoint).params["stopCondition"]
    assert stop["userFlag"] == f"split-{id(builder.package)}"
