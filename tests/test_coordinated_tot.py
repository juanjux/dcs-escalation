"""Suppression windows, independent timing modes and old-save compatibility."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from dcs.mapping import Point
from dcs.terrain import Caucasus

from game.ato.flighttype import FlightType
from game.ato.package import Package
from game.commander import coordinatedtot as timing
from game.db import Database
from game.theater import Player
from game.utils import meters

NOW = datetime(2026, 10, 29, 23, 40)
LENGTH = timedelta(hours=1)
TERRAIN = Caucasus()


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


class Sam:
    name = "SAM site"
    position = Point(0, 0, TERRAIN)
    has_live_radar_sam = True
    friendly = False
    dead = False

    def max_threat_range(self) -> Any:
        return meters(40_000)

    def is_friendly(self, player: Any) -> bool:
        return self.friendly

    @property
    def is_dead(self) -> bool:
        return self.dead


@pytest.fixture
def scenario(monkeypatch: Any) -> Any:
    monkeypatch.setattr(timing, "IadsGroundObject", Sam)
    monkeypatch.setattr(
        timing,
        "TotEstimator",
        lambda package: SimpleNamespace(earliest_tot=lambda now: package.earliest),
    )
    sam = Sam()
    cp = SimpleNamespace(captured=Player.RED, ground_objects=[sam])
    coalition: Any = SimpleNamespace(
        player=Player.BLUE,
        game=SimpleNamespace(theater=SimpleNamespace(controlpoints=[cp])),
        ato=SimpleNamespace(packages=[]),
    )

    def package(task: FlightType, earliest: int, target: Any = None) -> Any:
        p = SimpleNamespace(
            flights=[SimpleNamespace(flight_type=task, coalition=coalition)],
            primary_task=task,
            target=target if target is not None else sam,
            earliest=at(earliest),
            time_over_target=at(earliest),
            auto_asap=False,
            auto_coordinated=True,
            all_flights_waiting_for_start=lambda: True,
        )
        p.set_tot_asap = lambda now: setattr(p, "time_over_target", p.earliest)
        coalition.ato.packages.append(p)
        return p

    target = SimpleNamespace(name="Factory", position=Point(10_000, 0, TERRAIN))
    return SimpleNamespace(
        sam=sam,
        cp=cp,
        coalition=coalition,
        package=package,
        target=target,
        plan=lambda p: timing.plan_coordinated_tot(
            p, coalition.ato.packages, NOW, LENGTH
        ),
    )


def test_waits_for_latest_covering_suppressor_across_midnight(scenario: Any) -> None:
    s = scenario
    s.package(FlightType.SEAD, 15)
    last = s.package(FlightType.DEAD, 25)
    strike = s.package(FlightType.STRIKE, 10, s.target)
    result = s.plan(strike)
    assert result.tot == at(27)
    assert result.behind[-1] is last
    assert result.warnings == []


@pytest.mark.parametrize("arrival,expected", [(10, 22), (25, 25), (30, 30)])
def test_window_opens_after_two_minutes_and_lasts_eight(
    scenario: Any, arrival: int, expected: int
) -> None:
    s = scenario
    s.package(FlightType.SEAD, 20)
    strike = s.package(FlightType.STRIKE, arrival, s.target)
    assert s.plan(strike).tot == at(expected)


@pytest.mark.parametrize("sead,arrival", [(70, 10), (20, 31)])
def test_unreachable_window_falls_back_to_asap_with_warning(
    scenario: Any, sead: int, arrival: int
) -> None:
    s = scenario
    s.package(FlightType.SEAD, sead)
    strike = s.package(FlightType.STRIKE, arrival, s.target)
    result = s.plan(strike)
    assert result.tot == at(arrival)
    assert result.behind == []
    assert "Flying ASAP" in result.warnings[0]


def test_missing_suppression_names_covering_enemy_sam(scenario: Any) -> None:
    s = scenario
    strike = s.package(FlightType.STRIKE, 10, s.target)
    assert "SAM site" in s.plan(strike).warnings[0]


@pytest.mark.parametrize("state", ["neutral", "friendly", "dead", "outside"])
def test_no_warning_for_non_threats(scenario: Any, state: str) -> None:
    s = scenario
    if state == "neutral":
        s.cp.captured = Player.NEUTRAL
    elif state == "outside":
        s.target.position = Point(100_000, 0, TERRAIN)
    else:
        setattr(s.sam, state, True)
    strike = s.package(FlightType.STRIKE, 10, s.target)
    assert s.plan(strike).warnings == []


def test_organic_sead_escort_avoids_missing_suppression_warning(scenario: Any) -> None:
    s = scenario
    strike = s.package(FlightType.CAS, 10, s.target)
    strike.flights.append(SimpleNamespace(flight_type=FlightType.SEAD_ESCORT))
    assert s.plan(strike).warnings == []


def test_other_coalition_and_unplanned_suppression_are_not_providers(
    scenario: Any,
) -> None:
    s = scenario
    other = s.package(FlightType.SEAD, 20)
    other.flights[0].coalition = SimpleNamespace(player=Player.RED)
    unplanned = s.package(FlightType.DEAD, 30)
    unplanned.time_over_target = datetime.min
    strike = s.package(FlightType.STRIKE, 10, s.target)
    assert s.plan(strike).tot == at(10)
    assert s.plan(strike).behind == []


def test_active_packages_are_not_retimed_and_suppression_is_finalized_first(
    scenario: Any,
) -> None:
    s = scenario
    strike = s.package(FlightType.STRIKE, 10, s.target)
    active = s.package(FlightType.STRIKE, 10, s.target)
    active.all_flights_waiting_for_start = lambda: False
    sead = s.package(FlightType.SEAD, 20)
    sead.time_over_target = at(55)
    game: Any = SimpleNamespace(
        blue=s.coalition,
        red=SimpleNamespace(ato=SimpleNamespace(packages=[])),
        conditions=SimpleNamespace(start_time=NOW),
        settings=SimpleNamespace(desired_player_mission_duration=LENGTH),
    )
    timing.retime_coordinated_packages(game)
    assert sead.time_over_target == at(20)
    assert strike.time_over_target == at(22)
    assert active.time_over_target == at(10)


def test_manual_and_asap_modes_are_preserved(scenario: Any) -> None:
    s = scenario
    strike = s.package(FlightType.STRIKE, 10, s.target)
    strike.auto_coordinated = False
    strike.time_over_target = at(40)
    assert timing.apply_tot_mode(strike, [], NOW, LENGTH) is None
    assert strike.time_over_target == at(40)
    strike.auto_asap = True
    timing.apply_tot_mode(strike, [], NOW, LENGTH)
    assert strike.time_over_target == at(10)


def test_old_saves_and_clones_preserve_their_timing_choice() -> None:
    target: Any = SimpleNamespace()
    package: Any = Package(target, Database(), auto_asap=True)
    state = dict(package.__dict__)
    del state["auto_coordinated"]
    old = Package.__new__(Package)
    old.__setstate__(state)
    assert old.auto_asap and not old.auto_coordinated
    package.auto_coordinated = True
    package.auto_asap = False
    clone = Package.clone_package(package)
    assert clone.auto_coordinated and not clone.auto_asap


def test_takeoff_retimes_before_initializing_flight_states(monkeypatch: Any) -> None:
    from game.sim import missionsimulation

    order = []
    monkeypatch.setattr(
        missionsimulation,
        "retime_coordinated_packages",
        lambda game: order.append("tot"),
    )
    simulation = missionsimulation.MissionSimulation.__new__(
        missionsimulation.MissionSimulation
    )
    simulation.game = Mock(conditions=SimpleNamespace(start_time=NOW))
    simulation.aircraft_simulation = Mock()
    simulation.aircraft_simulation.begin_simulation.side_effect = lambda: order.append(
        "states"
    )
    simulation.begin_simulation()
    assert order == ["tot", "states"]
