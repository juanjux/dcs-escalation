from collections.abc import Iterator

from game.commander.tasks.primitive.armedrecon import PlanArmedRecon
from game.commander.tasks.primitive.bai import PlanBai
from game.ato.flighttype import FlightType
from game.commander.tasks.primitive.motorpool import PlanMotorpoolAttack
from game.commander.theaterstate import TheaterState
from game.htn import CompoundTask, Method


class AttackBattlePositions(CompoundTask[TheaterState]):
    def each_valid_method(self, state: TheaterState) -> Iterator[Method[TheaterState]]:
        for battle_positions in state.enemy_battle_positions.values():
            for battle_position in battle_positions.in_priority_order:
                yield [PlanBai(battle_position)]
        for motorpool in state.motorpool_targets:
            # BAI is preferred (parked ground forces); STRIKE is the fallback so a
            # package can still form when no BAI-capable aircraft are available.
            # Applying either effect removes the target from motorpool_targets, so at
            # most one package is planned against a given motorpool per turn.
            yield [PlanMotorpoolAttack(motorpool, FlightType.BAI)]
            yield [PlanMotorpoolAttack(motorpool, FlightType.STRIKE)]
        # Only plan against the 2 most important CPs
        for cp in state.control_point_priority_queue[:2]:
            if not cp.is_fleet:
                yield [PlanArmedRecon(cp)]
