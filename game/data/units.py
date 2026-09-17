from __future__ import annotations

from enum import unique, Enum


@unique
class UnitClass(Enum):
    UNKNOWN = "Unknown"
    AAA = "AAA"
    AIRCRAFT_CARRIER = "AircraftCarrier"
    APC = "APC"
    ARTILLERY = "Artillery"
    ATGM = "ATGM"
    BOAT = "Boat"
    COMMAND_POST = "CommandPost"
    CRUISER = "Cruiser"
    DESTROYER = "Destroyer"
    EARLY_WARNING_RADAR = "EarlyWarningRadar"
    # Ground-based radio/navigation jamming. A new member is safe for existing
    # saves; none of them can reference it.
    ELECTRONIC_WARFARE = "ElectronicWarfare"
    FORTIFICATION = "Fortification"
    FRIGATE = "Frigate"
    HELICOPTER = "Helicopter"
    HELICOPTER_CARRIER = "HelicopterCarrier"
    IFV = "IFV"
    INFANTRY = "Infantry"
    LANDING_SHIP = "LandingShip"
    LAUNCHER = "Launcher"
    LOGISTICS = "Logistics"
    MANPAD = "Manpad"
    MISSILE = "Missile"
    ANTISHIP_MISSILE = "AntiShipMissile"
    OPTICAL_TRACKER = "OpticalTracker"
    PLANE = "Plane"
    POWER = "Power"
    RECON = "Recon"
    SEARCH_LIGHT = "SearchLight"
    SEARCH_RADAR = "SearchRadar"
    SEARCH_TRACK_RADAR = "SearchTrackRadar"
    SHORAD = "SHORAD"
    SPECIALIZED_RADAR = "SpecializedRadar"
    SUBMARINE = "Submarine"
    TANK = "Tank"
    TELAR = "TELAR"
    TRACK_RADAR = "TrackRadar"

    @property
    def description(self) -> str:
        """What this kind of unit is, in the words a player would use.

        The unit's own name says the model, not the job: "SAM Patriot ECS" and
        "SAM Patriot LN" are the same three words to anyone who has not read the
        manual. Empty for the classes whose name already is the description.
        """
        return UNIT_CLASS_DESCRIPTIONS.get(self, "")

    @property
    def note(self) -> str:
        """What the unit does for the site around it, for the classes where losing it
        costs more than one gun. Empty where there is nothing to add."""
        return UNIT_CLASS_NOTES.get(self, "")


# All UnitClasses which can have AntiAir capabilities
ANTI_AIR_UNIT_CLASSES = [
    UnitClass.AAA,
    UnitClass.AIRCRAFT_CARRIER,
    UnitClass.CRUISER,
    UnitClass.DESTROYER,
    UnitClass.EARLY_WARNING_RADAR,
    UnitClass.FRIGATE,
    UnitClass.HELICOPTER_CARRIER,
    UnitClass.LAUNCHER,
    UnitClass.MANPAD,
    UnitClass.SEARCH_RADAR,
    UnitClass.SEARCH_TRACK_RADAR,
    UnitClass.SPECIALIZED_RADAR,
    UnitClass.SHORAD,
    UnitClass.SUBMARINE,
    UnitClass.TELAR,
    UnitClass.TRACK_RADAR,
]


#: One short phrase per class, for the unit rows of a location. Kept next to the enum
#: so a new class either gets a description here or reads as nothing, never as a stale
#: one from somewhere else.
UNIT_CLASS_DESCRIPTIONS: dict[UnitClass, str] = {
    UnitClass.AAA: "AAA",
    UnitClass.AIRCRAFT_CARRIER: "carrier",
    UnitClass.APC: "APC",
    UnitClass.ARTILLERY: "artillery",
    UnitClass.ATGM: "anti-tank missiles",
    UnitClass.BOAT: "boat",
    UnitClass.COMMAND_POST: "command post",
    UnitClass.CRUISER: "cruiser",
    UnitClass.DESTROYER: "destroyer",
    UnitClass.EARLY_WARNING_RADAR: "early-warning radar",
    UnitClass.ELECTRONIC_WARFARE: "jammer",
    UnitClass.FORTIFICATION: "fortification",
    UnitClass.FRIGATE: "frigate",
    UnitClass.HELICOPTER: "helicopter",
    UnitClass.HELICOPTER_CARRIER: "helicopter carrier",
    UnitClass.IFV: "IFV",
    UnitClass.INFANTRY: "infantry",
    UnitClass.LANDING_SHIP: "landing ship",
    UnitClass.LAUNCHER: "launcher",
    UnitClass.LOGISTICS: "logistics",
    UnitClass.MANPAD: "MANPADS",
    UnitClass.MISSILE: "missile",
    UnitClass.ANTISHIP_MISSILE: "anti-ship missiles",
    UnitClass.OPTICAL_TRACKER: "optical tracker",
    UnitClass.PLANE: "aircraft",
    UnitClass.POWER: "power",
    UnitClass.RECON: "recon",
    UnitClass.SEARCH_LIGHT: "searchlight",
    UnitClass.SEARCH_RADAR: "search radar",
    UnitClass.SEARCH_TRACK_RADAR: "search & track radar",
    UnitClass.SHORAD: "SHORAD",
    UnitClass.SPECIALIZED_RADAR: "search radar",
    UnitClass.SUBMARINE: "submarine",
    UnitClass.TANK: "tank",
    UnitClass.TELAR: "launcher with its own radar",
    UnitClass.TRACK_RADAR: "tracking radar",
}


#: Only for the classes a site depends on, where the row is the place to say what
#: bombing it costs. Everything else is left without a note.
UNIT_CLASS_NOTES: dict[UnitClass, str] = {
    UnitClass.COMMAND_POST: "directs the site",
    UnitClass.EARLY_WARNING_RADAR: "watches for the whole network",
    UnitClass.ELECTRONIC_WARFARE: "throws GPS-guided weapons off inside its bubble",
    UnitClass.OPTICAL_TRACKER: "aims by sight when the radar is down",
    UnitClass.POWER: "keeps the site up if the grid fails",
    UnitClass.SEARCH_LIGHT: "lights targets for the guns at night",
    UnitClass.SEARCH_RADAR: "finds the targets",
    UnitClass.SEARCH_TRACK_RADAR: "finds the targets and guides the missiles",
    UnitClass.SPECIALIZED_RADAR: "finds the targets",
    UnitClass.TRACK_RADAR: "guides the missiles onto the target",
}


#: Where the class is wrong about one of its units, by DCS id. SpecializedRadar holds
#: the acquisition radars of the S-300s, the Hawk and the Patriot, so it reads as a
#: search radar -- except for the Patriot's antenna mast group, which carries no radar
#: at all and relays the battery's radio traffic.
UNIT_DESCRIPTIONS: dict[str, str] = {
    "Patriot AMG": "comms relay",
}

UNIT_NOTES: dict[str, str] = {
    "Patriot AMG": "carries the radio links between the site and its battery",
}
