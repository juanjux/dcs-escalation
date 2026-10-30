"""Aircraft counts used by the squadron list."""

from game.squadrons import Squadron


def aircraft_on_hand(squadron: Squadron) -> int:
    """Exclude sold aircraft immediately and purchases until delivery."""
    return max(0, squadron.owned_aircraft + min(0, squadron.pending_deliveries))
