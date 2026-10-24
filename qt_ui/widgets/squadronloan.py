"""Shared loan status for squadron lists and details."""

from game.squadrons import Squadron
from game.highcommand.loans import loan_for


def squadron_loan_text(squadron: Squadron) -> str:
    """Read the current loan, without storing a second copy of its expiry."""
    game = squadron.coalition.game
    if loan := loan_for(squadron):
        turns = max(0, loan.until - game.turn)
        unit = "turn" if turns == 1 else "turns"
        return f"On loan · {turns} {unit} remaining"
    return ""
