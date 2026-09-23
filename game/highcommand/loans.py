"""Squadrons lent to the player for a few turns: an extra AWACS, an extra tanker, or a
squadron of combat aircraft.

A loan is a new squadron of the player's, at a base the game picks: the rearmost that
can take it for support aircraft, the one nearest the enemy for combat ones. It comes
with its aircraft and pilots, and it is gone again at the end of the turn its loan
runs out, before the next turn is planned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

from game.squadrons.experience import SaveCompatible
from game.theater.controlpoint import ParkingType

if TYPE_CHECKING:
    from game import Game
    from game.ato.flighttype import FlightType
    from game.dcs.aircrafttype import AircraftType
    from game.squadrons.squadron import Squadron
    from game.theater import ControlPoint, Player


@dataclass
class Loan(SaveCompatible):
    """A squadron lent to the player."""

    squadron: Squadron
    #: The first turn it is no longer the player's.
    until: int


def lend(
    game: Game,
    player: Player,
    aircraft: AircraftType,
    count: int,
    turns: int,
    task: FlightType,
    front: bool,
) -> Optional[Loan]:
    """Raise a squadron of ``count`` aircraft for ``turns`` turns, at the rearmost base
    that can take it, or the one nearest the enemy when ``front``. None when no base
    of the player's can."""
    from game.squadrons.squadron import Squadron

    base = loan_base(game, player, aircraft, count, front)
    if base is None:
        return None
    coalition = game.coalition_for(player)
    air_wing = coalition.air_wing
    squadron = Squadron.create_from(
        air_wing.squadron_def_generator.generate_for_aircraft(aircraft),
        task,
        count,
        base,
        coalition,
        game,
    )
    squadron.populate_for_turn_0(squadrons_start_full=True)
    air_wing.add_squadron(squadron)
    return Loan(squadron, game.turn + turns)


def loan_base(
    game: Game, player: Player, aircraft: AircraftType, count: int, front: bool
) -> Optional[ControlPoint]:
    """Where a loan of ``count`` aircraft can go: a base of the player's that can
    operate them and has room for all of them."""
    parking = ParkingType().from_aircraft(
        aircraft, game.settings.ground_start_ai_planes
    )
    bases = [
        cp
        for cp in game.theater.control_points_for(player)
        if cp.can_operate(aircraft) and cp.unclaimed_parking(parking) >= count
    ]
    if not bases:
        return None
    enemies = list(game.theater.control_points_for(player.opponent))

    def distance_to_enemy(cp: ControlPoint) -> float:
        return min(
            (cp.position.distance_to_point(e.position) for e in enemies),
            default=0.0,
        )

    return (min if front else max)(bases, key=distance_to_enemy)


def return_loans(game: Game, loans: list[Loan]) -> Iterable[str]:
    """Take back the squadrons whose loan has run out, and say which."""
    for loan in [loan for loan in loans if game.turn >= loan.until]:
        loans.remove(loan)
        squadron = loan.squadron
        squadron.refund_orders()
        air_wing = squadron.coalition.air_wing
        if squadron in air_wing.squadrons.get(squadron.aircraft, []):
            air_wing.squadrons[squadron.aircraft].remove(squadron)
            if not air_wing.squadrons[squadron.aircraft]:
                del air_wing.squadrons[squadron.aircraft]
        air_wing.unclaim_squadron_def(squadron)
        yield f"{squadron.name} ({squadron.aircraft}) goes back: its loan is over."
