"""Squadrons lent to the player for a few turns: an extra AWACS, an extra tanker, or a
squadron of combat aircraft.

A loan is a new squadron at a selected eligible base. Without a selection, the game
picks the rearmost base for support aircraft or the nearest to the enemy for combat.
It comes with aircraft and pilots, and leaves when the loan expires, before the
next turn is planned.
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
    base: Optional[ControlPoint] = None,
) -> Optional[Loan]:
    """Raise a loan at the selected base, or choose one when none is supplied.

    Reject a selected base if it is no longer eligible.
    """
    from game.squadrons.squadron import Squadron

    if base is None:
        base = loan_base(game, player, aircraft, count, front)
    elif base not in loan_bases(game, player, aircraft, count):
        return None
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
    # Loans arrive during planning, after the normal turn inventory reset.
    squadron.return_all_pilots_and_aircraft()
    air_wing.add_squadron(squadron)
    return Loan(squadron, game.turn + turns)


def loan_bases(
    game: Game, player: Player, aircraft: AircraftType, count: int
) -> list[ControlPoint]:
    """Friendly bases that can operate and accommodate the complete loan."""
    parking = ParkingType().from_aircraft(
        aircraft, game.settings.ground_start_ai_planes
    )
    return [
        cp
        for cp in game.theater.control_points_for(player)
        if cp.can_operate(aircraft) and cp.unclaimed_parking(parking) >= count
    ]


def loan_base(
    game: Game, player: Player, aircraft: AircraftType, count: int, front: bool
) -> Optional[ControlPoint]:
    """Choose an eligible base by distance to the enemy."""
    bases = loan_bases(game, player, aircraft, count)
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
