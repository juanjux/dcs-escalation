from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from game.debriefing import Debriefing
from game.commander.coordinatedtot import retime_coordinated_packages
from game.missionarchive import archive_mission
from game.missiongenerator import MissionGenerator
from game.unitmap import UnitMap
from .aircraftsimulation import AircraftSimulation
from .missionresultsprocessor import MissionResultsProcessor
from ..profiling import logged_duration

if TYPE_CHECKING:
    from game import Game
    from .gameupdateevents import GameUpdateEvents


class MissionSimulation:
    def __init__(self, game: Game) -> None:
        self.game = game
        self.unit_map: Optional[UnitMap] = None
        self.aircraft_simulation = AircraftSimulation(self.game)
        self.completed = False
        self.time = self.game.conditions.start_time
        #: Wall-clock time the playable .miz was generated. Any state.json
        #: written after this belongs to the current mission; older files are
        #: stale leftovers and must be ignored by end-of-mission detection.
        self.miz_generated_at: float = 0.0

    def begin_simulation(self) -> None:
        retime_coordinated_packages(self.game)
        self.time = self.game.conditions.start_time
        self.aircraft_simulation.begin_simulation()

    def generate_miz(self, output: Path) -> None:
        with logged_duration("Mission generation"):
            self.unit_map = MissionGenerator(self.game, self.time).generate_miz(output)
        self.miz_generated_at = time.time()
        # Keep a named copy: `output` is a fixed path the next generation overwrites.
        # Best-effort, never raises -- the mission itself is already written.
        archive_mission(self.game, output)

    def debrief_current_state(
        self, state_path: Path, force_end: bool = False
    ) -> Debriefing:
        if self.unit_map is None:
            raise RuntimeError(
                "Simulation has no unit map. Results processing began before a mission "
                "was generated."
            )

        with state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)
        if force_end:
            data["mission_ended"] = True
        debriefing = Debriefing(data, self.game, self.unit_map)
        debriefing.merge_simulation_results(self.aircraft_simulation.results)
        return debriefing

    def process_results(self, debriefing: Debriefing, events: GameUpdateEvents) -> None:
        if self.unit_map is None:
            raise RuntimeError(
                "Simulation has no unit map. Results processing began before a mission "
                "was generated."
            )

        MissionResultsProcessor(self.game).commit(debriefing, events)

    def finish(self) -> None:
        self.unit_map = None
