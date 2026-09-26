"""Notes belong to a pilot and airframe, independent of a planned sortie."""

from game.ato.flight import Flight


def notes_for_flight(flight: Flight) -> list[tuple[str, str]]:
    aircraft = flight.unit_type.dcs_unit_type.id
    return [
        (member.pilot.name, note)
        for member in flight.iter_members()
        if member.is_player and member.pilot is not None
        if (
            note := getattr(member.pilot, "aircraft_notes", {}).get(aircraft, "")
        ).strip()
    ]
