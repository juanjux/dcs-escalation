"""Shared loan status for squadron lists and details."""

from game.squadrons import Squadron


def squadron_loan_text(squadron: Squadron) -> str:
    """Read the current loan, without storing a second copy of its expiry."""
    game = squadron.coalition.game
    for loan in game.high_command_for(squadron.player).loans:
        if loan.squadron == squadron:
            turns = max(0, loan.until - game.turn)
            unit = "turn" if turns == 1 else "turns"
            return f"On loan · {turns} {unit} remaining"
    return ""
