"""Build a stripped-down .miz with Escalation own mission generator, for testing.

A campaign mission carries ~750 groups, none of which has anything to do with
whatever you are testing, and that is what makes time acceleration crawl. This
stands up a real game from a campaign, throws away every ground object but the
target, every front line, the plugin Lua and the parked aircraft, and leaves one
package against a target at least MIN_RANGE_NM from its home field. About forty
groups, ~600 KB.

The flights are air started and the package TOT is the earliest the package can
manage, so everything is flying a minute or two after the mission starts instead of
after half an hour of ramp time.

To test something else, edit the knobs below: CAMPAIGN and the two factions,
MIN_RANGE_NM, and ELEMENTS -- one line per flight, as
(aircraft, FlightType, count, tot_offset_minutes). A negative offset asks that flight
to arrive ahead of the package. Squadrons the campaign air wing does not have are
stood up on the spot, and a flight whose aircraft cannot fly the task fails loudly at
generation (the F-15C has no SEAD task in DCS, for instance).

Run it from the repo root with the venv that builds the game:

    .venv/Scripts/python.exe tools/make_test_mission.py
"""

from __future__ import annotations

import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

FORK = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(FORK))

from game import persistency
from game.ato.flight import Flight
from game.ato.flighttype import FlightType
from game.ato.package import Package
from game.ato.starttype import StartType
from game.ato.traveltime import TotEstimator
from game.campaignloader.campaign import Campaign
from game.dcs.aircrafttype import AircraftType
from game.factions import FACTIONS
from game.missiongenerator.missiongenerator import MissionGenerator
from game.settings import Settings
from game.theater.start_generator import GameGenerator, GeneratorSettings, ModSettings
from game.theater.theatergroundobject import IadsGroundObject
from game.utils import meters

logging.basicConfig(level=logging.ERROR)

SAVED_GAMES = str(Path.home() / "Saved Games" / "DCS")
OUT_DIR = Path(SAVED_GAMES) / "Missions"
CAMPAIGN = FORK / "resources" / "campaigns" / "exercise_vegas_nerve.yaml"
MIN_RANGE_NM = 100

# Three different airframes for the three "ahead" roles, so they can be told apart
# on the F10 map at a glance.
ELEMENTS = [
    # The package proper, on the package TOT.
    ("F/A-18C Hornet (Lot 20)", FlightType.DEAD, 4, 0),
    ("F/A-18C Hornet (Lot 20)", FlightType.SEAD, 4, 0),
    # Four roles asked to arrive three minutes early, one airframe each so they can
    # be told apart on the F10 map at a glance.
    ("F-14B Tomcat", FlightType.ESCORT, 2, -3),
    ("F-15C Eagle", FlightType.SWEEP, 2, -3),
    ("F-15E Strike Eagle (Suite 4+)", FlightType.TARCAP, 2, -3),
    ("F-16CM Fighting Falcon (Block 50)", FlightType.BARCAP, 2, -3),
]


def build_game():
    # Same seed every time: the three missions must differ only in the offset.
    random.seed(20260912)
    persistency.setup(SAVED_GAMES, False, 16880)
    payloads = FORK / "resources" / "customized_payloads"
    from game.missiongenerator.aircraft.flightgroupspawner import (  # noqa: F401
        FlightGroupSpawner,
    )
    import dcs.unittype

    dcs.unittype.FlyingType.payload_dirs = [str(payloads)] + list(
        getattr(dcs.unittype.FlyingType, "payload_dirs", [])
    )

    campaign = Campaign.from_file(CAMPAIGN)
    theater = campaign.load_theater(False)
    generator = GameGenerator(
        FACTIONS["USA 2005"],
        FACTIONS["Redfor (China) 2020"],
        theater,
        campaign.load_air_wing_config(theater),
        Settings(supercarrier=False),
        GeneratorSettings(
            start_date=datetime(2024, 6, 1),
            start_time=campaign.recommended_start_time,
            player_budget=2000,
            enemy_budget=2000,
            inverted=False,
            advanced_iads=theater.iads_network.advanced_iads,
            no_carrier=True,
            no_lha=True,
            no_player_navy=True,
            no_enemy_navy=True,
            tgo_config=campaign.load_ground_forces_config(),
            carrier_config=campaign.load_carrier_config(),
            squadrons_start_full=True,
        ),
        ModSettings(),
    )
    game = generator.generate()
    game.begin_turn_0(squadrons_start_full=True)
    return game


def ensure_squadron(game, aircraft: str, task: FlightType, base):
    """Stand up a squadron if the campaign's air wing has none for this job.

    Same path the campaign uses when ferried aircraft arrive somewhere with no
    squadron of their type: a generated squadron def, then Squadron.create_from.
    """
    existing = squadron_for(game, aircraft, task)
    if existing is not None:
        if existing.untasked_aircraft < 4:
            existing.owned_aircraft = max(existing.owned_aircraft, 12)
            existing.untasked_aircraft = 12
        return existing

    from game.squadrons.squadron import Squadron

    wanted = AircraftType.named(aircraft)
    coalition = game.blue
    squadron_def = coalition.air_wing.squadron_def_generator.generate_for_aircraft(
        wanted
    )
    squadron = Squadron.create_from(squadron_def, task, 12, base, coalition, game)
    squadron.owned_aircraft = 12
    squadron.untasked_aircraft = 12
    squadron.populate_for_turn_0(squadrons_start_full=True)
    squadron.set_auto_assignable_mission_types({task})
    coalition.air_wing.add_squadron(squadron)
    return squadron


def strip_theater(game, target) -> None:
    """Leave the theatre with the target and nothing else.

    A full campaign puts ~750 groups on the map. None of them has anything to do
    with the timing under test, and they are what makes time acceleration crawl.
    """
    for cp in game.theater.controlpoints:
        keep = [tgo for tgo in cp.connected_objectives if tgo is target]
        cp.connected_objectives = keep
        cp.front_lines.clear()
    for coalition in game.coalitions:
        if coalition.player.is_red:
            coalition.ato.clear()
    # No scripts either: the plugin Lua is a large chunk of what the mission loads.
    for key in list(game.settings.plugins):
        game.settings.plugins[key] = False
    game.settings.perf_disable_convoys = True
    # Otherwise every squadron's untasked aircraft are parked on the ramp: 174 extra
    # groups, none of them ours.
    game.settings.perf_disable_untasked_blufor_aircraft = True
    game.settings.perf_disable_untasked_opfor_aircraft = True


def squadron_for(game, aircraft: str, task: FlightType):
    wanted = AircraftType.named(aircraft)
    for squadron in game.blue.air_wing.iter_squadrons():
        if squadron.aircraft == wanted and squadron.capable_of(task):
            return squadron
    return None


def pick_target(game, home):
    """The closest enemy air defence at least MIN_RANGE_NM from home."""
    best, best_nm = None, None
    for cp in game.theater.controlpoints:
        # `captured` is a Player, not a bool: every control point is truthy.
        if not cp.captured.is_red:
            continue
        for tgo in cp.ground_objects:
            if not isinstance(tgo, IadsGroundObject) or not tgo.alive_unit_count:
                continue
            nm = meters(home.position.distance_to_point(tgo.position)).nautical_miles
            if nm < MIN_RANGE_NM:
                continue
            if best is None or nm < best_nm:
                best, best_nm = tgo, nm
    return best, best_nm


def home_base(game):
    """The blue field the F-15C flies from; everything is based together so the
    three elements share a departure and the timing is comparable."""
    squadron = squadron_for(game, "F-15C Eagle", FlightType.ESCORT)
    assert squadron is not None, "Bluefor Modern always has an F-15C squadron"
    return squadron.location


def apply_offsets(package: Package) -> None:
    """recreate_flight_plan() resets the offset to the flight type's default, so the
    wanted offsets go on after the last rebuild."""
    wanted = {(a, t): o for a, t, _c, o in ELEMENTS}
    for flight in package.flights:
        offset = wanted.get((str(flight.squadron.aircraft), flight.flight_type))
        if offset is not None:
            flight.flight_plan.tot_offset = timedelta(minutes=offset)


def build_package(game, target, escort_offset_minutes: float) -> Package:
    package = Package(target, game.db.flights, auto_asap=False)
    for aircraft, task, count, _offset in ELEMENTS:
        squadron = ensure_squadron(game, aircraft, task, home_base(game))
        if squadron is None:
            raise SystemExit(f"no squadron for {aircraft} / {task}")
        flight = Flight(
            package, squadron, count, task, StartType.IN_FLIGHT, divert=None
        )
        package.add_flight(flight)
        flight.recreate_flight_plan()

    now = game.conditions.start_time
    apply_offsets(package)
    # The fix under test: the package has to leave room for the flight that is asked
    # to arrive first, or that flight's takeoff falls before the mission starts.
    # As early as the package can manage: every minute of slack is a minute of empty
    # sky to sit through before anything happens.
    package.time_over_target = TotEstimator(package).earliest_tot(now)

    for flight in package.flights:
        flight.recreate_flight_plan()
    apply_offsets(package)
    for flight in package.flights:
        flight.state.reinitialize(now)

    late = [
        (f, f.flight_plan.takeoff_time())
        for f in package.flights
        if f.flight_plan.takeoff_time() < now
    ]
    for flight, when in late:
        print(
            f"    WARNING {flight.flight_type} takes off at {when:%H:%M:%S}, before the"
            f" mission starts at {now:%H:%M:%S}"
        )
    return package


def report(package, label: str) -> None:
    print(f"  {label}: package TOT {package.time_over_target:%H:%M:%S}")
    for flight in package.flights:
        plan = flight.flight_plan
        # A patrol plan (TARCAP/BARCAP) has no join waypoint: it flies to its station.
        join = getattr(plan, "join_time", None)
        join_txt = f"{join:%H:%M:%S}" if join is not None else "   --   "
        print(
            f"    {str(flight.flight_type):12} {str(flight.squadron.aircraft):26}"
            f" offset {int(plan.tot_offset.total_seconds()):+5d}s"
            f"  takeoff {plan.takeoff_time():%H:%M:%S}"
            f"  join {join_txt}"
            f"  TOT {plan.tot:%H:%M:%S}"
        )


def main() -> None:
    variants = [
        (
            0,
            "test_package.miz",
            "4 roles a 3 min DELANTE: F-14 Escort, F-15C Fighter Sweep, F-15E TARCAP, F-16 BARCAP",
        ),
    ]

    for offset, filename, label in variants:
        # A fresh game per variant: generating a mission mutates the game state.
        game = build_game()
        home = home_base(game)
        target, nm = pick_target(game, home)
        if target is None:
            raise SystemExit("no target at least 120 NM out")
        strip_theater(game, target)
        package = build_package(game, target, offset)
        game.blue.ato.add_package(package)
        print(f"{filename}  target {target.name} at {nm:.0f} NM from {home.name}")
        report(package, label)
        out = OUT_DIR / filename
        generator = MissionGenerator(game, game.conditions.start_time)
        generator.generate_miz(out)
        # Name it inside the mission too, so the label shows in DCS and not only in
        # the file browser. Re-save only rewrites the mission table; the kneeboards
        # and every other resource already in the .miz are carried over by pydcs.
        generator.mission.set_sortie_text(f"TOT offset test -- {label}")
        generator.mission.save(out)
        print("  written", out)


if __name__ == "__main__":
    main()
