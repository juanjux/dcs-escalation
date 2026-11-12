from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from .gameupdatecallbacks import GameUpdateCallbacks
from .gameupdateevents import GameUpdateEvents
from .missionsimulation import MissionSimulation

if TYPE_CHECKING:
    from game import Game
    from game.debriefing import Debriefing


class GameLoop:
    """The turn's simulation, which no longer runs a clock.

    Fast forward is gone, so nothing advances time between planning and take-off:
    this puts the flights into their starting states, hands the mission to DCS at
    the time it was planned for, and takes the results back.
    """

    def __init__(self, game: Game, callbacks: GameUpdateCallbacks) -> None:
        self.game = game
        self.callbacks = callbacks
        self.sim = MissionSimulation(self.game)
        self.events = GameUpdateEvents()
        self.last_update_time = datetime.now()
        self.started = False
        self.completed = False

    @property
    def current_time_in_sim(self) -> datetime:
        return self.sim.time

    @property
    def elapsed_time(self) -> timedelta:
        return self.sim.time - self.game.conditions.start_time

    def start(self) -> None:
        if self.started:
            raise RuntimeError("Cannot start game loop because it has already started")
        self.sim.begin_simulation()
        self.started = True

    def generate_miz(self, output: Path) -> None:
        if not self.started:
            self.start()
        self.sim.generate_miz(output)

    def debrief(self, state_path: Path, force_end: bool) -> Debriefing:
        return self.sim.debrief_current_state(state_path, force_end)

    def complete_with_results(self, debriefing: Debriefing) -> None:
        self.sim.process_results(debriefing, self.events)
        self.completed = True
        self.send_update()

    def send_update(self) -> None:
        self.callbacks.on_update(self.events)
        self.events = GameUpdateEvents()
        self.last_update_time = datetime.now()
