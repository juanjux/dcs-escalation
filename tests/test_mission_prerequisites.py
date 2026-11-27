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


def test_generated_objective_conditions(tmp_path: Path) -> None:
    from zipfile import ZipFile
    from dcs import Mission, lua
    from dcs.terrain import Caucasus
    from game.data.units import UnitClass
    from game.missiongenerator.flightoutcomes import inject, objective_ids
    from game.missiongenerator.luagenerator import LuaGenerator
    from game.theater.theatergroundobject import SamGroundObject

    source, dependent = packages = [package("Source", 1), package("Follow", 2)]
    provider = flight(source, FlightType.DEAD)
    add(dependent, provider, packages)
    target: Any = object.__new__(SamGroundObject)
    target.name = "Example"
    source.target = target
    units = [
        SimpleNamespace(id=i, unit_type=SimpleNamespace(unit_class=kind), alive=True)
        for i, kind in enumerate(
            (
                UnitClass.TRACK_RADAR,
                UnitClass.SEARCH_TRACK_RADAR,
                UnitClass.SEARCH_RADAR,
            ),
            1,
        )
    ]
    target.groups = [SimpleNamespace(units=units[:1]), SimpleNamespace(units=units[1:])]
    unit_map: Any = SimpleNamespace(
        aircraft={"Demo #1": SimpleNamespace(flight=provider)},
        theater_objects={
            str(u.id): SimpleNamespace(
                theater_unit=u, dcs_unit=SimpleNamespace(id=100 + u.id)
            )
            for u in units
        },
    )
    game: Any = SimpleNamespace(
        coalitions=[SimpleNamespace(ato=SimpleNamespace(packages=packages))]
    )
    mission = Mission(Caucasus())
    generator = LuaGenerator(game, mission, SimpleNamespace(), unit_map)  # type: ignore[arg-type]
    inject(generator)
    path = tmp_path / "outcomes.miz"
    mission.save(str(path))
    with ZipFile(path) as archive:
        rules = lua.loads(archive.read("mission").decode())["mission"][
            "trigrules"
        ].values()
        assert "l10n/DEFAULT/ground-stores.lua" in archive.namelist()
        assert "l10n/DEFAULT/flight-outcomes.lua" in archive.namelist()
    report = next(r for r in rules if r["comment"].startswith("Objective complete"))
    assert {
        c["unit"] for c in report["rules"].values() if c["predicate"] == "c_unit_dead"
    } == {101, 102}
    assert report["actions"][1]["flag"] == outcome_flag(provider.id)
    start = next(r for r in rules if r["comment"] == "Flight outcomes")
    assert str(provider.id) in start["actions"][1]["text"]
    assert "Demo #1" in start["actions"][1]["text"]
    assert objective_ids(target, {1: 101}) is None
    units[0].alive = units[1].alive = False
    assert objective_ids(target, {}) == []
    target.groups = []
    assert objective_ids(target, {}) is None


@pytest.fixture
def outcome_vm() -> Any:
    vm = pytest.importorskip("lupa.lua51").LuaRuntime()
    vm.execute("""
        flags, units = {}, {}
        trigger = {misc={getUserFlag=function(key) return flags[key] or 0 end},
                   action={setUserFlag=function(key,v) flags[key]=v end}}
        world = {event={S_EVENT_SHOT=1,S_EVENT_LAND=2,S_EVENT_UNIT_LOST=3,S_EVENT_AI_ABORT_MISSION=4},
                 addEventHandler=function(h) handler=h end, removeEventHandler=function(h) handler=nil end}
        timer = {getTime=function() return 0 end, scheduleFunction=function(fn) poll=fn end}
        Weapon = {Category={MISSILE=1, BOMB=2, ROCKET=3}, MissileCategory={AAM=1,SAM=2}}
        Unit = {getByName=function(name) return units[name] end}
        function spawn(name)
            units[name] = {isExist=function() return true end, isActive=function() return true end,
                getName=function() return name end, inAir=function() return true end,
                getAmmo=function() return {{count=1,desc={category=2}}} end}
        end
        Group = {getByName=function() return {isExist=function() return true end,
                 getUnits=function() return {units.one,units.two} end} end}
        function advance() poll(nil, 3); poll(nil, 6) end
        function event(name, kind, weapon) handler:onEvent({id=kind,initiator=units[name],weapon=weapon}) end
    """)
    root = Path("resources/plugins")
    for script in ("imac/ground-stores.lua", "base/flight-outcomes.lua"):
        vm.execute((root / script).read_text(encoding="utf-8"))
    vm.execute('EscalationFlightOutcomes.start({x={"one","two"}})')
    return vm


@pytest.mark.parametrize(
    "end",
    [
        "event('two',2)",
        "event('two',3)",
        "event('two',4)",
        "EscalationFlightOutcomes.returning('group')",
        "flags['prerequisite-return-x']=1",
        "units.two.getAmmo=function() return {{count=1,desc={category=1,missileCategory=1}}} end",
    ],
)
def test_flight_ends_only_after_last_member(outcome_vm: Any, end: str) -> None:
    vm = outcome_vm
    vm.execute(
        "advance(); spawn('one'); spawn('two'); advance(); event('one',3); advance()"
    )
    assert vm.eval("flags['scenario-outcome-x']") is None
    vm.execute(end + "; advance()")
    assert vm.eval("flags['scenario-outcome-x']") == 2


@pytest.mark.parametrize("objective_destroyed", [False, True])
def test_last_release_resolves_before_winchester(
    outcome_vm: Any, objective_destroyed: bool
) -> None:
    vm = outcome_vm
    vm.execute("""
        spawn('one'); spawn('two'); advance()
        airborne = true
        event('one',1,{getDesc=function() return {category=2} end, isExist=function() return airborne end})
        units.one.getAmmo=function() return {} end
        event('two',3)
        advance()
    """)
    assert vm.eval("flags['scenario-outcome-x']") is None
    vm.execute("airborne=false; poll(nil,9)")
    if objective_destroyed:
        vm.execute("flags['scenario-outcome-x']=1")
    vm.execute("poll(nil,12)")
    assert vm.eval("flags['scenario-outcome-x']") == (1 if objective_destroyed else 2)


def package(name: str, hour: int) -> Any:
    from game.data.units import UnitClass
    from game.theater.theatergroundobject import SamGroundObject

    target: Any = object.__new__(SamGroundObject)
    target.name = name
    target.groups = [
        SimpleNamespace(
            units=[
                SimpleNamespace(
                    id=1,
                    alive=True,
                    unit_type=SimpleNamespace(unit_class=UnitClass.TRACK_RADAR),
                )
            ]
        )
    ]
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


def test_multiple_external_links_and_cycles() -> None:
    a, b, c = packages = [package(n, h) for h, n in enumerate("ABC", 1)]
    external = flight(a)
    sweep, dead = flight(b, FlightType.SWEEP), flight(b, FlightType.DEAD)
    member = flight(b, FlightType.STRIKE)
    dependent = flight(c)
    add(b, external, packages)
    add(c, sweep, packages)
    add(c, dead, packages)
    add(c, external, packages)
    assert (
        required_by(member) == required_by(sweep) == required_by(dead) == [external.id]
    )
    assert required_by(dependent) == [sweep.id, dead.id, external.id]
    with pytest.raises(ValueError, match="Circular"):
        add(a, dependent, packages)
    assert not a.prerequisite_flights
    with pytest.raises(ValueError, match="already"):
        add(b, external, packages)


def test_package_cannot_require_its_own_sweep_even_with_an_escort() -> None:
    from game.ato.prerequisites import TimingConflict

    current, other = packages = [package("Boulder City", 20) for _ in range(2)]
    other.target = current.target
    current.time_over_target = other.time_over_target = datetime(2000, 1, 1, 20, 50, 15)
    sweep = flight(current, FlightType.SWEEP)
    escort = flight(current, FlightType.ESCORT)
    with pytest.raises(ValueError, match="its own flights"):
        add(current, sweep, packages)
    assert not current.prerequisite_flights
    # The same target in another package is eligible, but a tied TOT needs repair.
    with pytest.raises(TimingConflict) as error:
        add(other, sweep, packages)
    assert error.value.adjustments == {other: datetime(2000, 1, 1, 20, 51)}
    current.prerequisite_flights.append(sweep.id)
    assert not required_by(sweep) and not required_by(escort)
    with pytest.raises(ValueError, match="its own flights"):
        validate(packages)


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


def test_untargeted_sead_cannot_be_selected() -> None:
    a, b = packages = [package("Source", 1), package("Follow", 2)]
    provider = flight(a)
    a.target.groups = []
    with pytest.raises(ValueError, match="assigned objective"):
        add(b, provider, packages)
    assert b.prerequisite_flights == []


def test_repair_previews_offsets_and_dependents_across_midnight() -> None:
    from game.ato.prerequisites import TimingConflict
    from game.ato.flightplans.flightplan import FlightPlan

    a, b, c, independent = packages = [package(n, 23) for n in "ABCD"]
    a.time_over_target = a.time_over_target.replace(minute=59, second=15)
    c.time_over_target = c.time_over_target.replace(minute=59)

    def make_flight(p: Any, offset: int) -> Any:
        f = flight(p, FlightType.SWEEP)

        class Plan:
            package = p
            tot_offset = timedelta(minutes=offset)
            tot = FlightPlan.tot

        f.flight_plan = Plan()
        f.state = SimpleNamespace(is_waiting_for_start=True)
        return f

    provider = make_flight(a, 0)
    early = make_flight(b, -5)
    later = make_flight(b, 2)
    make_flight(c, -1)
    add(c, later, packages)
    b.auto_asap = True
    originals = [p.time_over_target for p in packages]
    with pytest.raises(TimingConflict) as error:
        add(b, provider, packages)
    plan = error.value.adjustments
    assert plan == {b: datetime(2000, 1, 2, 0, 5), c: datetime(2000, 1, 2, 0, 9)}
    assert [p.time_over_target for p in packages] == originals
    assert b.auto_asap and not b.prerequisite_flights
    early.state.is_waiting_for_start = False
    with pytest.raises(ValueError, match="locked"):
        add(b, provider, packages, approved_times=plan)
    assert [p.time_over_target for p in packages] == originals
    early.state.is_waiting_for_start = True
    add(b, provider, packages, approved_times=plan)
    validate(packages)
    assert (b.auto_asap, b.prerequisite_flights) == (False, [provider.id])
    assert early.flight_plan.tot > provider.flight_plan.tot
    assert (
        a.time_over_target == originals[0]
        and independent.time_over_target == originals[3]
    )


def test_sweep_package_at_2050_keeps_the_following_tarcap_after_2050() -> None:
    from game.ato.prerequisites import TimingConflict
    from game.ato.flightplans.sweep import SweepFlightPlan
    from game.ato.flightplans.tarcap import TarCapFlightPlan

    source, follow = packages = [
        package(name, 20) for name in ("Boulder City", "Follow")
    ]
    source.time_over_target = source.time_over_target.replace(minute=50, second=15)
    sweep = flight(source, FlightType.SWEEP)
    tarcap = flight(follow, FlightType.TARCAP)
    # Use the real plans' TOT properties and default offsets without building routes.
    for member, plan_type in ((sweep, SweepFlightPlan), (tarcap, TarCapFlightPlan)):
        plan = object.__new__(plan_type)
        plan.flight = member
        plan.tot_offset = plan.default_tot_offset()
        member.flight_plan = plan
        member.state = SimpleNamespace(is_waiting_for_start=True)
    assert sweep.flight_plan.tot == source.time_over_target.replace(minute=45)
    with pytest.raises(TimingConflict, match="later than 20:52:15") as error:
        add(follow, sweep, packages)
    add(follow, sweep, packages, approved_times=error.value.adjustments)
    assert follow.time_over_target == datetime(2000, 1, 1, 20, 53)
    assert tarcap.flight_plan.tot > source.time_over_target
    validate(packages)


def test_only_the_return_leg_marks_the_attempt_finished() -> None:
    from game.ato.flightwaypointtype import FlightWaypointType as Wpt
    from game.missiongenerator.flightoutcomes import mark_return

    a, b = packages = [package("Source", 1), package("Follow", 2)]
    provider = flight(a)
    provider.coalition = SimpleNamespace(ato=SimpleNamespace(packages=packages))
    # A single-flight package labels both its outbound nav and split as NAV.
    points: Any = [
        (SimpleNamespace(waypoint_type=kind), SimpleNamespace(tasks=[]))
        for kind in (Wpt.NAV, Wpt.LOITER, Wpt.NAV, Wpt.LANDING_POINT)
    ]
    provider.flight_plan.layout = SimpleNamespace(split=points[2][0])
    mark_return(provider, points)
    assert not any(native.tasks for _, native in points)
    add(b, provider, packages)
    mark_return(provider, points)
    assert [len(native.tasks) for _, native in points] == [0, 0, 1, 0]
    command = points[2][1].tasks[0].dict()["params"]["action"]["params"]["command"]
    assert f"prerequisite-return-{provider.id}" in command


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


def test_save_migration_removes_only_own_flights_and_preserves_tot() -> None:
    import pickle
    from game.migrator import Migrator

    db: Database[Any] = Database()
    target: Any = SimpleNamespace(name="Boulder City")
    source, follow = Package(target, db), Package(target, db)
    source.time_over_target = datetime(2000, 1, 1, 20, 45)
    follow.time_over_target = datetime(2000, 1, 1, 20, 50, 15)
    earlier = flight(source, FlightType.SWEEP)
    own = flight(follow, FlightType.SWEEP)
    flight(follow, FlightType.ESCORT)
    follow.prerequisite_flights = [own.id, earlier.id]
    coalition = SimpleNamespace(ato=SimpleNamespace(packages=[source, follow]))
    migrator = object.__new__(Migrator)
    migrator.game = pickle.loads(pickle.dumps(SimpleNamespace(coalitions=[coalition])))
    migrator._update_package_attributes()
    loaded_source, loaded_follow = next(iter(migrator.game.coalitions)).ato.packages
    assert loaded_follow.prerequisite_flights == [earlier.id]
    assert loaded_follow.time_over_target == follow.time_over_target
    validate([loaded_source, loaded_follow])


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


def test_duplicate_excludes_legacy_internal_links_and_keeps_external_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game.ato.flight import Flight

    a, b = packages = [package("First", 1), package("Second", 2)]
    source = flight(a)
    same_package = flight(b)
    flight(b, FlightType.STRIKE)
    add(b, source, packages)
    b.prerequisite_flights.append(same_package.id)
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
    assert clone.prerequisite_flights == [source.id]
    assert all(required_by(f) == [source.id] for f in clone.flights)
    assert b.prerequisite_flights == [source.id, same_package.id]
