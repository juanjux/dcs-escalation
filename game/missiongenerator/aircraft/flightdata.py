from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, TYPE_CHECKING

from dcs.flyingunit import FlyingUnit

from game.ato.savedpoints import SavedPoint
from game.ato.starttype import StartType
from game.callsigns import create_group_callsign_from_unit
from game.squadrons import Squadron

if TYPE_CHECKING:
    from game.ato import FlightType, FlightWaypoint, Package
    from game.dcs.aircrafttype import AircraftType
    from game.radio.radios import RadioFrequency
    from game.runways import RunwayData
    from game.theater.player import Player
    from game.utils import Speed


@dataclass(frozen=True)
class ChannelAssignment:
    radio_id: int
    channel: int


@dataclass
class FlightData:
    """Details of a planned flight."""

    #: The package that the flight belongs to.
    package: Package

    flight_type: FlightType

    aircraft_type: AircraftType

    squadron: Squadron

    #: All units in the flight.
    units: list[FlyingUnit]

    #: Total number of aircraft in the flight.
    size: int

    #: True if this flight belongs to the player's coalition.
    friendly: Player

    #: Number of seconds after mission start the flight is set to depart.
    departure_delay: timedelta

    #: Arrival airport.
    arrival: RunwayData

    #: Departure airport.
    departure: RunwayData

    #: Diver airport.
    divert: Optional[RunwayData]

    #: Waypoints of the flight plan.
    waypoints: list[FlightWaypoint]

    #: Radio frequency for intra-flight communications.
    intra_flight_channel: RadioFrequency

    #: Bingo fuel value in lbs.
    bingo_fuel: Optional[int]

    joker_fuel: Optional[int]

    laser_codes: list[Optional[int]]

    custom_name: Optional[str]

    #: How the flight starts (cold, warm, runway, or in-flight).
    start_type: StartType

    #: Points the player wrote down for this aircraft from the map. They are not part
    #: of the flight plan: they get a kneeboard page of their own.
    saved_points: list[SavedPoint] = field(default_factory=list)

    #: The DCS group's name, which is what the tanker and AEW&C records go by.
    group_name: str = ""

    #: The speed the flight orbits at, when its flight plan has an orbit.
    patrol_speed: Optional[Speed] = None

    callsign: str = field(init=False)

    #: Map of radio frequencies to the radio/channel presets they were assigned
    #: to. A frequency can land on more than one channel -- e.g. on both COMM1
    #: and COMM2 -- so each maps to a list, ordered by assignment (COMM1 first).
    frequency_to_channel_map: dict[RadioFrequency, list[ChannelAssignment]] = field(
        init=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self.callsign = create_group_callsign_from_unit(self.units[0])

    @property
    def client_units(self) -> list[FlyingUnit]:
        """List of playable units in the flight."""
        return [u for u in self.units if u.is_human()]

    def num_radio_channels(self, radio_id: int) -> int:
        """Returns the number of preset channels for the given radio."""
        # Note: pydcs only initializes the radio presets for client slots.
        return self.client_units[0].num_radio_channels(radio_id)

    def channel_for(self, frequency: RadioFrequency) -> Optional[ChannelAssignment]:
        """Returns the first (lowest) channel a frequency was assigned to."""
        channels = self.frequency_to_channel_map.get(frequency)
        return channels[0] if channels else None

    def channels_for(self, frequency: RadioFrequency) -> list[ChannelAssignment]:
        """Returns every channel a frequency was assigned to (COMM1 first)."""
        return self.frequency_to_channel_map.get(frequency, [])

    def assign_channel(
        self, radio_id: int, channel_id: int, frequency: RadioFrequency
    ) -> None:
        """Assigns a preset radio channel to the given frequency."""
        for unit in self.client_units:
            unit.set_radio_channel_preset(radio_id, channel_id, frequency.mhz)

        # A frequency can be bound to several channels (e.g. mirrored onto both
        # COMM1 and COMM2). Record them all, in assignment order.
        self.frequency_to_channel_map.setdefault(frequency, []).append(
            ChannelAssignment(radio_id, channel_id)
        )
