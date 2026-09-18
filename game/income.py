from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.config import REWARDS
from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game


@dataclass(frozen=True)
class BuildingIncome:
    name: str
    category: str
    number: int
    income_per_building: float
    #: How many buildings the site started with. A site pays for the ones still
    #: standing, so the pair is what says whether it is whole or half bombed.
    total: int = 0

    @property
    def income(self) -> float:
        return self.number * self.income_per_building


class Income:
    def __init__(self, game: Game, player: Player) -> None:
        if player.is_blue:
            self.multiplier = game.settings.player_income_multiplier
        else:
            self.multiplier = game.settings.enemy_income_multiplier
        self.control_points = []
        self.buildings = []

        for cp in game.theater.control_points_for(player):
            if cp.income_per_turn:
                self.control_points.append(cp)

            for tgo in cp.ground_objects:
                if tgo.category not in REWARDS:
                    continue
                statics = list(tgo.statics)
                self.buildings.append(
                    BuildingIncome(
                        tgo.obj_name,
                        tgo.category,
                        sum(1 for b in statics if b.alive),
                        REWARDS[tgo.category],
                        len(statics),
                    )
                )

        self.from_bases = sum(cp.income_per_turn for cp in self.control_points)
        self.total_buildings = sum(b.income for b in self.buildings)
        self.total = (self.total_buildings + self.from_bases) * self.multiplier
