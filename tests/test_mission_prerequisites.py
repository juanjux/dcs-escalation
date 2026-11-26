from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from uuid import uuid4

import pytest

from game.ato.flighttype import FlightType
from game.ato.package import Package
from game.ato.prerequisites import (
    add,
    depends_on_text,
    outcome_flag,
    required_by,
    validate,
)
from game.db import Database


def package(name: str, hour: int) -> Any:
    target: Any = SimpleNamespace(name=name)
    result = Package(target, Database())
    result.time_over_target = datetime(2000, 1, 1, hour)
    return result


def flight(package: Any, role: FlightType = FlightType.SEAD) -> Any:
    result = SimpleNamespace(
        package=package,
        id=uuid4(),
        flight_type=role,
        custom_name="Test",
        flight_plan=SimpleNamespace(tot=package.time_over_target),
    )
    package.flights.append(result)
    package._db.add(result.id, result)
    return result


def test_multiple_links_and_internal_providers() -> None:
    a, b, c = packages = [package(n, h) for h, n in enumerate("ABC", 1)]
    external = flight(a)
    internal, other = flight(b, FlightType.SWEEP), flight(b, FlightType.DEAD)
    member = flight(b, FlightType.STRIKE)
    dependent = flight(c)
    add(b, external, packages)
    add(b, internal, packages)
    add(b, other, packages)
    add(c, internal, packages)
    add(c, external, packages)
    assert required_by(member) == [external.id, internal.id, other.id]
    assert required_by(internal) == required_by(other) == [external.id]
    assert required_by(dependent) == [internal.id, external.id]
    with pytest.raises(ValueError, match="Circular"):
        add(a, dependent, packages)
    assert not a.prerequisite_flights
    with pytest.raises(ValueError, match="already"):
        add(b, external, packages)


def test_checks_later_edits_and_ato_membership() -> None:
    a, b = packages = [package("Source", 1), package("Follow", 2)]
    provider = flight(a)
    member = flight(b, FlightType.STRIKE)
    with pytest.raises(ValueError, match="eligible"):
        add(b, member, packages)
    with pytest.raises(ValueError, match="missing"):
        add(b, flight(package("Other coalition", 1)), packages)
    add(b, provider, packages)
    provider.flight_plan.tot += timedelta(hours=1)
    with pytest.raises(ValueError, match="later"):
        validate(packages)
    a.flights.remove(provider)
    with pytest.raises(ValueError, match="missing"):
        validate(packages)
    assert "Removed flight" in depends_on_text(member)


def test_old_coordinated_save_keeps_its_scheduled_time() -> None:
    original = package("Demo", 10)
    state = vars(original).copy()
    state.pop("prerequisite_flights")
    state["auto_coordinated"] = True
    loaded = Package.__new__(Package)
    loaded.__setstate__(state)
    assert loaded.time_over_target == original.time_over_target
    assert not loaded.auto_asap
    assert loaded.prerequisite_flights == []


@pytest.mark.parametrize("first", [1, 2])
def test_generated_scenario_waits_and_propagates_results(
    tmp_path: Path, first: int
) -> None:
    from zipfile import ZipFile
    from dcs import Mission, Point, lua
    from dcs.action import Coalition
    from dcs.planes import TF_51D
    from dcs.terrain import Caucasus
    from game.ato.flightwaypointtype import FlightWaypointType as Wpt
    from game.missiongenerator.prerequisites import (
        configure_wait,
        generate_events,
    )
    from game.utils import knots

    a, b, c = packages = [package(n, h) for h, n in enumerate("ABC", 1)]
    db: Database[Any] = Database()
    for item in packages:
        item._db = db
    s1, s2, member = flight(a), flight(b), flight(c, FlightType.STRIKE)
    add(b, s1, packages)
    add(c, s1, packages)
    add(c, s2, packages)
    terrain = Caucasus()
    mission = Mission(terrain)
    pos = Point(0, 0, terrain)
    group = mission.flight_group_inflight(
        mission.country("USA"), "Training", TF_51D, pos, 1200
    )
    from game.ato.flightplans.custom import CustomFlightPlan, CustomLayout
    from game.ato.flightwaypoint import FlightWaypoint
    from game.utils import feet

    def waypoint(kind: Wpt, x: float) -> FlightWaypoint:
        return FlightWaypoint(kind.name, kind, Point(x, 0, terrain), feet(3000))

    member.flight_plan = CustomFlightPlan(
        member,
        CustomLayout(
            waypoint(Wpt.TAKEOFF, 0),
            [waypoint(Wpt.NAV, 1000), waypoint(Wpt.LANDING_POINT, 3000)],
        ),
    )
    member.points = member.flight_plan.waypoints[1:]
    wait_point = member.points[0]
    assert wait_point.waypoint_type is Wpt.PREREQUISITE_WAIT
    assert wait_point.position.x == pytest.approx(500)
    wait_point.position = Point(600, 80, terrain)
    assert member.flight_plan.waypoints[1] is wait_point
    member.unit_type = SimpleNamespace(preferred_patrol_speed=lambda alt: knots(160))
    generated = [
        (src, group.add_waypoint(src.position, 1200, name=src.name))
        for src in member.points
    ]
    configure_wait(member, group, generated)
    generate_events(mission, packages, Coalition.Blue, reports=True)
    path = tmp_path / "prerequisites.miz"
    mission.save(str(path))
    with ZipFile(path) as archive:
        data = lua.loads(archive.read("mission").decode("utf-8"))["mission"]
    countries = data["coalition"]["blue"]["country"].values()
    usa = next(c for c in countries if c["name"] == "USA")
    wait = usa["plane"]["group"][1]["route"]["points"][2]
    assert wait["name"] == "Wait for DEAD/Fighter Sweep"
    actions = wait["task"]["params"]["tasks"]
    assert actions[1]["params"]["stopCondition"]["userFlag"] == f"end-wait-{member.id}"
    assert "goToWaypointIndex=4" in actions[2]["params"]["action"]["params"]["command"]

    # Execute the exported ONCE conditions and flag actions in reverse order to
    # exercise propagation across DCS trigger ticks, including early results.
    rules = list(data["trigrules"].values())
    flags: dict[str, int] = {}

    def tick() -> None:
        for rule in reversed(rules.copy()):
            if all(
                flags.get(cond["flag"], 0) == cond["value"]
                for cond in rule["rules"].values()
            ):
                for action in rule["actions"].values():
                    if action["predicate"] == "a_set_flag_value":
                        flags[action["flag"]] = action["value"]
                rules.remove(rule)

    flags[outcome_flag(s2.id)] = 1
    tick()
    assert f"end-wait-{member.id}" not in flags
    flags[outcome_flag(s1.id)] = first
    for _ in range(5):
        tick()
    assert flags[f"prerequisites-{member.id}"] == first
    assert flags[f"end-wait-{member.id}"] == 1
    assert flags[f"prerequisite-result-{s2.id}"] == first

    vm = pytest.importorskip("lupa.lua51").LuaRuntime()
    vm.globals().flagValue = flags[f"prerequisites-{member.id}"]
    vm.execute("""
        trigger = {misc = {getUserFlag = function() return flagValue end}}
        local controller = {setCommand = function(_, command)
            nextPoint = command.params.goToWaypointIndex
        end}
        Group = {getByName = function()
            return {isExist = function() return true end, getController = function() return controller end}
        end}
    """)
    vm.execute(actions[2]["params"]["action"]["params"]["command"])
    assert vm.globals().nextPoint == (4 if first == 2 else None)


def test_duplicate_remaps_internal_flights_and_keeps_external_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.ato.flight import Flight

    a, b = packages = [package("First", 1), package("Second", 2)]
    source = flight(a)
    same_package = flight(b)
    member = flight(b, FlightType.STRIKE)
    add(b, source, packages)
    add(b, same_package, packages)
    for original in b.flights:
        original.flight_plan.layout = SimpleNamespace(prerequisite_wait=None)

    def copy(original: Any) -> Any:
        return SimpleNamespace(
            id=uuid4(),
            flight_type=original.flight_type,
            flight_plan=SimpleNamespace(),
            label_formation_waypoints=lambda: None,
        )

    monkeypatch.setattr(Flight, "clone_flight", staticmethod(copy))
    clone = Package.clone_package(b)
    assert clone.prerequisite_flights == [source.id, clone.flights[0].id]
    assert required_by(clone.flights[0]) == [source.id]
    assert same_package.id not in required_by(clone.flights[1])
    assert b.prerequisite_flights == required_by(member)
